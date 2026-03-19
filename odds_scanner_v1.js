#!/usr/bin/env node
/**
 * Polymarket オッズ変動シグナル検知
 * Polymarket CLIを使って市場データを取得し、急変動を検知する
 */

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const DATA_DIR = __dirname;
const HISTORY_FILE = path.join(DATA_DIR, "odds_history.json");
const ALERT_FILE = path.join(DATA_DIR, "latest_alerts.json");
const CLI_PATH = "/usr/local/bin/polymarket";
const ALERT_THRESHOLD = 3.0; // 3%以上の変動でアラート

const WATCH_QUERIES = [
  // クリプト
  "Bitcoin",
  "Ethereum",
  "Solana",
  "crypto",
  "stablecoin",
  // AI
  "OpenAI",
  "Anthropic",
  "NVIDIA",
  "AI",
  // 金融政策
  "Fed rate",
  "Bank of Japan",
  "interest rate",
  "inflation",
  "recession",
  // 地政学
  "Trump tariff",
  "trade war",
  "Iran ceasefire",
  "Iran war",
  "Iran",
  "Taiwan",
  "China",
  "Korea",
  // 産業
  "semiconductor",
  "oil",
  "Japan",
];

function searchMarkets(query, limit = 3) {
  try {
    const stdout = execSync(
      `${CLI_PATH} markets search "${query}" --limit ${limit} -o json`,
      { timeout: 15000, encoding: "utf-8" }
    );
    const data = JSON.parse(stdout);
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function loadHistory() {
  try {
    return JSON.parse(fs.readFileSync(HISTORY_FILE, "utf-8"));
  } catch {
    return {};
  }
}

function saveHistory(history) {
  fs.writeFileSync(HISTORY_FILE, JSON.stringify(history, null, 2));
}

function cleanupExpired(history) {
  const now = new Date();
  const cleaned = {};
  for (const [mid, info] of Object.entries(history)) {
    if (mid === "_meta") {
      cleaned[mid] = info;
      continue;
    }
    const endDate = info.end_date;
    if (endDate) {
      try {
        if (new Date(endDate) < now) continue;
      } catch {}
    }
    cleaned[mid] = info;
  }
  return cleaned;
}

function refreshMarketList(history) {
  const lastRefresh = history._meta?.last_refresh || "";
  const today = new Date().toISOString().slice(0, 10);

  if (lastRefresh) {
    const daysDiff =
      (new Date(today) - new Date(lastRefresh)) / (1000 * 60 * 60 * 24);
    if (daysDiff < 7) return history;
  }

  history = cleanupExpired(history);
  history._meta = { ...history._meta, last_refresh: today };
  console.log("市場リスト更新: 終了済み除外完了");
  saveHistory(history);
  return history;
}

function scanMarkets() {
  const now = new Date().toISOString().replace("T", " ").slice(0, 16) + " UTC";
  let history = loadHistory();
  history = refreshMarketList(history);

  const alerts = [];
  const currentSnapshot = {};
  const seenIds = new Set();

  for (const query of WATCH_QUERIES) {
    const markets = searchMarkets(query);

    for (const m of markets) {
      const mid = m.conditionId || m.id || "";
      if (!mid || seenIds.has(mid)) continue;
      seenIds.add(mid);

      const question = m.question || "?";
      const liq = parseFloat(m.liquidity || 0);

      // 5分市場・低流動性は除外
      if (question.includes("Up or Down") || question.includes("Minutes"))
        continue;
      if (liq < 1000) continue;

      let yesPct;
      try {
        const prices =
          typeof m.outcomePrices === "string"
            ? JSON.parse(m.outcomePrices)
            : m.outcomePrices;
        yesPct = parseFloat(prices[0]) * 100;
      } catch {
        continue;
      }

      currentSnapshot[mid] = {
        question,
        yes_pct: Math.round(yesPct * 10) / 10,
        liquidity: liq,
        timestamp: now,
        query,
        end_date: m.endDate || "",
      };

      // 前回との比較
      if (history[mid]) {
        const prevPct = history[mid].yes_pct ?? yesPct;
        const delta = yesPct - prevPct;

        if (Math.abs(delta) >= ALERT_THRESHOLD) {
          alerts.push({
            question: question.slice(0, 80),
            prev: prevPct,
            current: Math.round(yesPct * 10) / 10,
            delta: Math.round(delta * 10) / 10,
            direction: delta > 0 ? "📈" : "📉",
            liquidity: liq,
            query,
          });
        }
      }
    }
  }

  // 履歴を更新
  Object.assign(history, currentSnapshot);
  saveHistory(history);

  return { alerts, marketCount: Object.keys(currentSnapshot).length };
}

function formatAlerts(alerts) {
  if (!alerts.length) return null;

  const lines = ["**🚨 Polymarket オッズ急変動検知**", ""];

  const sorted = [...alerts].sort(
    (a, b) => Math.abs(b.delta) - Math.abs(a.delta)
  );

  for (const a of sorted) {
    lines.push(`${a.direction} **${a.question}**`);
    lines.push(
      `  ${a.prev.toFixed(1)}% → ${a.current.toFixed(1)}% (${a.delta > 0 ? "+" : ""}${a.delta.toFixed(1)}%)`
    );
    lines.push(`  流動性: $${a.liquidity.toLocaleString()}`);
    lines.push(`  🔍 要因調査キーワード: ${a.query}`);
    lines.push("");
  }

  lines.push(
    "上記の変動について、最新ニュースを検索して理由を分析してください。"
  );
  lines.push("関連する株/クリプト銘柄があれば併せて提示してください。");

  return lines.join("\n");
}

// メイン
const now = new Date().toISOString().slice(11, 16);
console.log(`[${now} UTC] Polymarket odds scanner starting...`);

const { alerts, marketCount } = scanMarkets();
console.log(`監視市場数: ${marketCount}`);

if (alerts.length) {
  const msg = formatAlerts(alerts);
  console.log(msg);
  fs.writeFileSync(ALERT_FILE, JSON.stringify(alerts, null, 2));
  console.log(`\n${alerts.length}件のアラートを検知`);
} else {
  console.log("変動なし");
}
