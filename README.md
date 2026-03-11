# polymarket-monitor

Polymarket のオッズ変動を定期監視し、急変動を検知するツール。

## 構成

| ファイル | 役割 |
|---|---|
| `odds_scanner.js` | Polymarket CLI でマーケットを検索し、前回比で急変動を検知 |
| `correlation_tracker.js` | アラート検知時に関連資産（暗号資産・株）の価格を記録 |
| `scan_and_notify.sh` | エントリーポイント。スキャン実行 → Discord 通知 |

## 前提

- [Polymarket CLI](https://github.com/Polymarket/polymarket-cli) がインストール済みであること
- [OpenClaw](https://github.com/openclaw/openclaw) が稼働中であること（Discord 通知用）

## セットアップ

```bash
git clone https://github.com/br-to/polymarket-monitor.git
cd polymarket-monitor
```

`odds_scanner.js` 内の `CLI_PATH` を自分の環境に合わせて変更:

```js
const CLI_PATH = "/usr/local/bin/polymarket";
```

## 環境変数

| 変数 | 説明 | 例 |
|---|---|---|
| `NOTIFY_CHANNEL` | Discord チャンネル ID（通知先） | `1234567890` |
| `NOTIFY_ACCOUNT` | OpenClaw アカウント名（省略可） | `blues` |

## 使い方

### 手動実行

```bash
node odds_scanner.js
```

### crontab で定期実行（例: 3時間ごと）

```cron
0 0,3,6,9,12,15,18,21 * * * /path/to/scan_and_notify.sh >> /tmp/polymarket-scan.log 2>&1
```

## 仕組み

1. `odds_scanner.js` が 24 カテゴリ（BTC, ETH, AI, 地政学, 金融政策など）のマーケットを検索
2. 前回のオッズと比較し、閾値（デフォルト 3%）以上の変動をアラートとして出力
3. `scan_and_notify.sh` がアラートを検知した場合、OpenClaw 経由で Discord に通知
4. `correlation_tracker.js` がアラート時の関連資産価格を記録（CoinGecko + Yahoo Finance）

## 監視カテゴリ

暗号資産 / AI / 金融政策 / 地政学 / 産業 — 計 24 キーワード

## ライセンス

MIT
