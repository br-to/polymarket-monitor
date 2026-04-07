#!/usr/bin/env node
/**
 * トレーディングシグナル生成
 * Polymarket変動 → 米国株売買シグナル
 */

const fs = require("fs");
const path = require("path");

const DATA_DIR = __dirname;
const CONFIG_FILE = path.join(DATA_DIR, "config.json");
const POSITIONS_FILE = path.join(DATA_DIR, "positions.json");
const ALERTS_FILE = path.join(DATA_DIR, "latest_alerts.json");

// 設定読み込み
function loadConfig() {
  if (!fs.existsSync(CONFIG_FILE)) {
    console.error("config.json not found");
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8"));
}

// ポジション読み込み
function loadPositions() {
  if (!fs.existsSync(POSITIONS_FILE)) {
    return { capital: 10000, positions: [], history: [] };
  }
  return JSON.parse(fs.readFileSync(POSITIONS_FILE, "utf-8"));
}

// ポジション保存
function savePositions(data) {
  fs.writeFileSync(POSITIONS_FILE, JSON.stringify(data, null, 2));
}

// アラート読み込み
function loadAlerts() {
  if (!fs.existsSync(ALERTS_FILE)) {
    return [];
  }
  return JSON.parse(fs.readFileSync(ALERTS_FILE, "utf-8"));
}

// 市場カテゴリ → ティッカーマッピング
function getTickersForCategory(config, categoryLabel) {
  const cat = config.categories.find((c) => c.label === categoryLabel);
  return cat ? cat.tickers : [];
}

// シグナル生成
function generateSignals(alerts, config, positions) {
  const signals = [];
  const tradingConfig = config.trading;

  // ポジション数チェック
  if (positions.positions.length >= tradingConfig.maxPositions) {
    return {
      signals: [],
      message: `ポジション上限（${tradingConfig.maxPositions}）到達。新規エントリー不可。`,
    };
  }

  for (const alert of alerts) {
    const delta = alert.delta;
    const absDelta = Math.abs(delta);

    // 閾値チェック
    if (absDelta < config.threshold) continue;

    // ティッカー取得
    const tickers = getTickersForCategory(config, alert.query);
    if (!tickers.length) continue;

    // シグナル強度
    let strength = "NORMAL";
    if (absDelta >= config.strongThreshold) {
      strength = "STRONG";
    }

    // アクション決定
    let action = "BUY";
    let reasoning = "";

    if (delta > 0) {
      // 上昇
      if (alert.query.includes("停戦") || alert.question.includes("ceasefire")) {
        // 停戦確率上昇 → 航空株買い
        action = "BUY";
        reasoning = "停戦期待上昇 → 原油下落 → 航空株買い";
      } else if (
        alert.query.includes("地上侵攻") ||
        alert.question.includes("forces enter")
      ) {
        // 地上侵攻確率上昇 → 防衛株買い
        action = "BUY";
        reasoning = "地上侵攻期待上昇 → 防衛株買い";
      } else if (alert.query.includes("Fed rate") || alert.query.includes("利下げ")) {
        // 利下げ期待上昇 → グロース株買い
        action = "BUY";
        reasoning = "利下げ期待上昇 → グロース株（QQQ）買い";
      } else if (alert.query.includes("Bitcoin") || alert.query.includes("Ethereum")) {
        // クリプト価格上昇期待 → クリプト関連株買い
        action = "BUY";
        reasoning = "クリプト価格上昇期待 → MSTR/COIN買い";
      } else if (alert.query.includes("oil") || alert.query.includes("原油")) {
        // 原油価格上昇期待 → エネルギー株買い
        action = "BUY";
        reasoning = "原油価格上昇期待 → エネルギー株買い";
      }
    } else {
      // 下落
      if (alert.query.includes("停戦") || alert.question.includes("ceasefire")) {
        // 停戦期待下落 → 防衛株買い
        action = "BUY";
        reasoning = "停戦期待下落 → 戦争長期化 → 防衛株買い";
      }
    }

    // シグナル作成
    for (const ticker of tickers) {
      signals.push({
        ticker,
        action,
        strength,
        reasoning,
        amount: positions.capital, // 全額
        polymarketEvent: alert.question,
        delta: alert.delta,
        timestamp: new Date().toISOString(),
      });
    }
  }

  return { signals, message: `${signals.length}件のシグナル生成` };
}

// メイン
function main() {
  const config = loadConfig();
  const positions = loadPositions();
  const alerts = loadAlerts();

  if (!alerts.length) {
    console.log("アラートなし");
    return;
  }

  const result = generateSignals(alerts, config, positions);

  console.log(result.message);

  if (result.signals.length) {
    console.log("\n📊 トレーディングシグナル:");
    for (const sig of result.signals) {
      console.log(`\n[${sig.strength}] ${sig.action} ${sig.ticker}`);
      console.log(`  金額: ¥${sig.amount.toLocaleString()}`);
      console.log(`  根拠: ${sig.reasoning}`);
      console.log(`  Polymarket: ${sig.polymarketEvent} (${sig.delta > 0 ? "+" : ""}${sig.delta}%)`);
    }

    // シグナルをファイル保存
    fs.writeFileSync(
      path.join(DATA_DIR, "trading_signals.json"),
      JSON.stringify(result.signals, null, 2)
    );
    console.log("\n✅ シグナル保存: trading_signals.json");
  }
}

if (require.main === module) {
  main();
}

module.exports = { generateSignals, loadConfig, loadPositions };
