#!/usr/bin/env node
/**
 * Polymarket オッズ変動シグナル検知 v2
 * config.jsonベースでカスタマイズ可能
 * --setup でセットアップウィザード起動
 */

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

// --setup フラグ
if (process.argv.includes("--setup")) {
  require("./setup.js");
  return;
}

const DATA_DIR = __dirname;
const CONFIG_FILE = path.join(DATA_DIR, "config.json");
const DEFAULT_CONFIG = path.join(DATA_DIR, "config.default.json");
const HISTORY_FILE = path.join(DATA_DIR, "odds_history.json");
const ALERT_FILE = path.join(DATA_DIR, "latest_alerts.json");
const CLI_PATH = process.env.POLYMARKET_CLI_PATH || "/usr/local/bin/polymarket";

// 設定読み込み
function loadConfig() {
  if (fs.existsSync(CONFIG_FILE)) {
    return JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8"));
  }
  if (fs.existsSync(DEFAULT_CONFIG)) {
    console.log("config.json が見つかりません。デフォルト設定を使用します。");
    console.log("カスタマイズするには: node odds_scanner.js --setup\n");
    return JSON.parse(fs.readFileSync(DEFAULT_CONFIG, "utf-8"));
  }
  console.error("設定ファイルが見つかりません。--setup で初期設定してください。");
  process.exit(1);
}

const config = loadConfig();
const ALERT_THRESHOLD = config.threshold || 3.0;
const MAX_RESULTS = config.maxResultsPerQuery || 3;
const MIN_LIQUIDITY = config.minLiquidity || 1000;

function searchMarkets(query, limit = MAX_RESULTS) {
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

  for (const category of config.categories) {
    const query = category.query;
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
      if (liq < MIN_LIQUIDITY) continue;

      // 30日以上先の市場は除外
      const endDate = m.endDate || "";
      if (endDate) {
        try {
          const daysUntilEnd = (new Date(endDate) - new Date()) / (1000 * 60 * 60 * 24);
          if (daysUntilEnd > 30) {
            continue;
          }
        } catch {}
      }

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
        category: category.id,
        query,
        up: category.up || category.tickers || [],
        down: category.down || category.tickers || [],
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
            direction: delta > 0 ? "\u{1F4C8}" : "\u{1F4C9}",
            liquidity: liq,
            category: category.label,
            query,
            up: category.up || category.tickers || [],
            down: category.down || category.tickers || [],
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

  const lines = ["**\u{1F6A8} Polymarket \u30AA\u30C3\u30BA\u6025\u5909\u52D5\u691C\u77E5**", ""];

  const sorted = [...alerts].sort(
    (a, b) => Math.abs(b.delta) - Math.abs(a.delta)
  );

  for (const a of sorted) {
    lines.push(`${a.direction} **${a.question}**`);
    lines.push(
      `  ${a.prev.toFixed(1)}% \u2192 ${a.current.toFixed(1)}% (${a.delta > 0 ? "+" : ""}${a.delta.toFixed(1)}%)`
    );
    lines.push(`  \u6D41\u52D5\u6027: $${a.liquidity.toLocaleString()} | \u30AB\u30C6\u30B4\u30EA: ${a.category}`);
    
    // 方向に応じて銘柄を表示
    if (a.delta > 0 && a.up && a.up.length) {
      lines.push(`  \u{1F4CA} \u4e0a\u6607\u2192${a.up.join(", ")}`);
    } else if (a.delta < 0 && a.down && a.down.length) {
      lines.push(`  \u{1F4CA} \u4e0b\u843d\u2192${a.down.join(", ")}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

// メイン
const now = new Date().toISOString().slice(11, 16);
console.log(`[${now} UTC] Polymarket odds scanner v2 starting...`);
console.log(`\u30AB\u30C6\u30B4\u30EA: ${config.categories.map((c) => c.label).join(", ")}`);
console.log(`\u95BE\u5024: ${ALERT_THRESHOLD}%\n`);

const { alerts, marketCount } = scanMarkets();
console.log(`\u76E3\u8996\u5E02\u5834\u6570: ${marketCount}`);

if (alerts.length) {
  const msg = formatAlerts(alerts);
  console.log(msg);
  fs.writeFileSync(ALERT_FILE, JSON.stringify(alerts, null, 2));
  console.log(`\n${alerts.length}\u4EF6\u306E\u30A2\u30E9\u30FC\u30C8\u3092\u691C\u77E5`);
  
  // Discord通知送信
  try {
    execSync(
      `/home/toikobara_komlock_lab_com/.npm-global/bin/openclaw message send --channel discord --account blues --target 1476585311164305408 --message "${msg.replace(/"/g, '\\"')}"`,
      { timeout: 30000, encoding: 'utf-8' }
    );
    console.log("Discord通知送信成功");
  } catch (err) {
    console.error("Discord通知送信失敗:", err.message);
  }
} else {
  console.log("\u5909\u52D5\u306A\u3057");
}
