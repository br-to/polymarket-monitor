#!/usr/bin/env node
/**
 * polymarket-monitor セットアップウィザード
 * 対話的に監視カテゴリ・閾値・通知設定を行い config.json に保存する
 */

const fs = require("fs");
const path = require("path");
const readline = require("readline");

const CONFIG_DIR = __dirname;
const CONFIG_FILE = path.join(CONFIG_DIR, "config.json");
const DEFAULT_CONFIG = path.join(CONFIG_DIR, "config.default.json");

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

function ask(question) {
  return new Promise((resolve) => rl.question(question, resolve));
}

async function main() {
  console.log("\n🔮 Polymarket Monitor セットアップ\n");

  // デフォルト設定を読み込み
  const defaults = JSON.parse(fs.readFileSync(DEFAULT_CONFIG, "utf-8"));

  // カテゴリ選択
  console.log("監視カテゴリを選んでください（番号をカンマ区切り、allで全選択）:\n");
  defaults.categories.forEach((cat, i) => {
    const tickers = cat.tickers.join(", ");
    console.log(`  ${i + 1}. ${cat.label} (${cat.query}) → ${tickers}`);
  });

  const catInput = await ask("\n選択 (例: 1,2,5 or all): ");

  let selectedCategories;
  if (catInput.trim().toLowerCase() === "all") {
    selectedCategories = defaults.categories;
  } else {
    const indices = catInput
      .split(",")
      .map((s) => parseInt(s.trim()) - 1)
      .filter((i) => i >= 0 && i < defaults.categories.length);
    selectedCategories = indices.map((i) => defaults.categories[i]);
  }

  if (selectedCategories.length === 0) {
    console.log("カテゴリが選択されていません。デフォルトを使用します。");
    selectedCategories = defaults.categories;
  }

  console.log(`\n✅ ${selectedCategories.length}カテゴリ選択\n`);

  // 閾値設定
  const thresholdInput = await ask(
    `アラート閾値（%）[デフォルト: ${defaults.threshold}]: `
  );
  const threshold = parseFloat(thresholdInput) || defaults.threshold;

  // カスタムカテゴリ追加
  const addCustom = await ask("\nカスタムカテゴリを追加しますか？ (y/n) [n]: ");
  if (addCustom.trim().toLowerCase() === "y") {
    let adding = true;
    while (adding) {
      const query = await ask("  検索キーワード: ");
      const label = await ask("  ラベル名: ");
      const tickers = await ask("  関連銘柄（カンマ区切り）: ");

      if (query && label) {
        selectedCategories.push({
          id: query.toLowerCase().replace(/\s+/g, "-"),
          query,
          label,
          tickers: tickers
            .split(",")
            .map((t) => t.trim().toUpperCase())
            .filter(Boolean),
        });
        console.log(`  ✅ "${label}" を追加`);
      }

      const more = await ask("  さらに追加しますか？ (y/n) [n]: ");
      adding = more.trim().toLowerCase() === "y";
    }
  }

  // 設定を保存
  const config = {
    categories: selectedCategories,
    threshold,
    maxResultsPerQuery: defaults.maxResultsPerQuery,
    minLiquidity: defaults.minLiquidity,
    notify: defaults.notify,
    createdAt: new Date().toISOString(),
  };

  fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
  console.log(`\n🎉 設定を保存しました: ${CONFIG_FILE}`);
  console.log(`\n監視カテゴリ: ${selectedCategories.map((c) => c.label).join(", ")}`);
  console.log(`閾値: ${threshold}%`);
  console.log(`\n次のステップ: node odds_scanner.js で監視開始\n`);

  rl.close();
}

main().catch((err) => {
  console.error(err);
  rl.close();
  process.exit(1);
});
