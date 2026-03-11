#!/usr/bin/env node
/**
 * Polymarket オッズ変動 × 市場価格の相関ログ
 * オッズ急変動時の関連銘柄価格を記録し、24時間後の変動と比較する
 */

const https = require("https");
const fs = require("fs");
const path = require("path");

const DATA_DIR = __dirname;
const LOG_FILE = path.join(DATA_DIR, "correlation_log.json");
const ALERT_FILE = path.join(DATA_DIR, "latest_alerts.json");

const MARKET_ASSET_MAP = {
  Bitcoin: { crypto: ["bitcoin"], stocks: ["MSTR", "COIN"] },
  Ethereum: { crypto: ["ethereum"], stocks: ["COIN"] },
  "Trump tariff": { crypto: [], stocks: ["EWW", "SPY"] },
  "Bank of Japan": { crypto: [], stocks: ["EWJ", "FXY"] },
  "Fed rate": { crypto: ["bitcoin"], stocks: ["QQQ", "TLT"] },
  OpenAI: { crypto: [], stocks: ["MSFT"] },
  Anthropic: { crypto: [], stocks: ["GOOGL"] },
  NVIDIA: { crypto: [], stocks: ["NVDA"] },
  recession: { crypto: ["bitcoin"], stocks: ["SPY", "GLD"] },
  AI: { crypto: [], stocks: ["NVDA", "MSFT", "GOOGL"] },
};

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { "User-Agent": "Mozilla/5.0" } }, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve(null); }
      });
    });
    req.on("error", () => resolve(null));
    req.setTimeout(10000, () => { req.destroy(); resolve(null); });
  });
}

async function getCryptoPrices(ids) {
  if (!ids.length) return {};
  const url = `https://api.coingecko.com/api/v3/simple/price?ids=${ids.join(",")}&vs_currencies=usd`;
  const data = await fetchJSON(url);
  if (!data) return {};
  const prices = {};
  for (const [k, v] of Object.entries(data)) {
    if (v?.usd) prices[k] = v.usd;
  }
  return prices;
}

async function getStockPrices(symbols) {
  if (!symbols.length) return {};
  const prices = {};
  for (const symbol of symbols) {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?range=1d&interval=1d`;
    const data = await fetchJSON(url);
    try {
      prices[symbol] = data.chart.result[0].meta.regularMarketPrice;
    } catch {}
  }
  return prices;
}

function loadLog() {
  try {
    return JSON.parse(fs.readFileSync(LOG_FILE, "utf-8"));
  } catch {
    return { events: [] };
  }
}

function saveLog(log) {
  fs.writeFileSync(LOG_FILE, JSON.stringify(log, null, 2));
}

function recordEvent(alert, cryptoPrices, stockPrices) {
  const mapping = MARKET_ASSET_MAP[alert.query] || { crypto: [], stocks: [] };

  const relatedCrypto = {};
  for (const id of mapping.crypto) {
    if (cryptoPrices[id]) relatedCrypto[id] = cryptoPrices[id];
  }
  const relatedStocks = {};
  for (const s of mapping.stocks) {
    if (stockPrices[s]) relatedStocks[s] = stockPrices[s];
  }

  return {
    timestamp: new Date().toISOString(),
    market: alert.question,
    query: alert.query,
    odds_prev: alert.prev,
    odds_current: alert.current,
    odds_delta: alert.delta,
    direction: alert.direction,
    crypto_prices_at_event: relatedCrypto,
    stock_prices_at_event: relatedStocks,
    check_after_24h: { crypto_ids: mapping.crypto, stock_symbols: mapping.stocks },
    result: null,
  };
}

async function checkPending(log) {
  const now = new Date();
  let updated = false;

  for (const event of log.events) {
    if (event.result) continue;
    const elapsed = (now - new Date(event.timestamp)) / (1000 * 60 * 60);
    if (elapsed < 24) continue;

    const mapping = event.check_after_24h;
    const cryptoNow = await getCryptoPrices(mapping.crypto_ids);
    const stocksNow = await getStockPrices(mapping.stock_symbols);

    const changes = [];
    for (const [asset, priceThen] of Object.entries(event.crypto_prices_at_event || {})) {
      const priceNow = cryptoNow[asset];
      if (priceNow && priceThen) {
        changes.push({
          asset, type: "crypto",
          price_at_event: priceThen,
          price_after_24h: priceNow,
          change_pct: Math.round(((priceNow - priceThen) / priceThen) * 10000) / 100,
        });
      }
    }
    for (const [symbol, priceThen] of Object.entries(event.stock_prices_at_event || {})) {
      const priceNow = stocksNow[symbol];
      if (priceNow && priceThen) {
        changes.push({
          asset: symbol, type: "stock",
          price_at_event: priceThen,
          price_after_24h: priceNow,
          change_pct: Math.round(((priceNow - priceThen) / priceThen) * 10000) / 100,
        });
      }
    }

    event.result = { checked_at: now.toISOString(), changes };
    updated = true;
  }
  return updated;
}

function analyzeCorrelations(log) {
  const completed = log.events.filter((e) => e.result?.changes?.length);

  if (completed.length < 5)
    return `データ蓄積中... (${completed.length}/5件完了、分析には最低5件必要)`;

  const lines = ["## Polymarket オッズ変動 × 市場価格 相関分析", ""];
  lines.push(`分析対象: ${completed.length}件\n`);

  for (const event of completed) {
    lines.push(`**${event.market}**`);
    lines.push(`  オッズ: ${event.odds_prev}% → ${event.odds_current}% (${event.odds_delta > 0 ? "+" : ""}${event.odds_delta.toFixed(1)}%)`);
    for (const c of event.result.changes) {
      const emoji = c.change_pct > 0 ? "📈" : c.change_pct < 0 ? "📉" : "➡️";
      lines.push(`  ${emoji} ${c.asset}: ${c.change_pct > 0 ? "+" : ""}${c.change_pct.toFixed(2)}% (24h後)`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

async function main() {
  const mode = process.argv[2];
  const log = loadLog();

  if (mode === "check") {
    const updated = await checkPending(log);
    if (updated) saveLog(log);
    console.log(analyzeCorrelations(log));
  } else if (mode === "analyze") {
    console.log(analyzeCorrelations(log));
  } else {
    if (!fs.existsSync(ALERT_FILE)) {
      console.log("アラートファイルなし");
      return;
    }
    const alerts = JSON.parse(fs.readFileSync(ALERT_FILE, "utf-8"));
    if (!alerts.length) { console.log("アラートなし"); return; }

    const allCrypto = new Set();
    const allStocks = new Set();
    for (const a of alerts) {
      const m = MARKET_ASSET_MAP[a.query] || { crypto: [], stocks: [] };
      m.crypto.forEach((id) => allCrypto.add(id));
      m.stocks.forEach((s) => allStocks.add(s));
    }

    const cryptoPrices = await getCryptoPrices([...allCrypto]);
    const stockPrices = await getStockPrices([...allStocks]);

    console.log("クリプト価格:", cryptoPrices);
    console.log("株価:", stockPrices);

    for (const alert of alerts) {
      const event = recordEvent(alert, cryptoPrices, stockPrices);
      log.events.push(event);
      console.log(`記録: ${alert.question} (${alert.delta > 0 ? "+" : ""}${alert.delta}%)`);
    }

    await checkPending(log);
    saveLog(log);
    console.log(`\n合計 ${log.events.length} イベント記録済み`);
  }
}

main();
