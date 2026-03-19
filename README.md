# polymarket-monitor

Polymarket のオッズ変動を定期監視し、急変動を検知するツール。関連する米国株ティッカーも表示します。

## 構成

| ファイル | 役割 |
|---|---|
| `odds_scanner.js` | Polymarket CLI でマーケットを検索し、前回比で急変動を検知 |
| `setup.js` | 対話的セットアップウィザード |
| `config.default.json` | デフォルト設定（10カテゴリ + 関連銘柄マッピング） |
| `correlation_tracker.js` | アラート検知時に関連資産の価格を記録 |
| `scan_and_notify.sh` | エントリーポイント。スキャン実行 → Discord 通知 |

## 前提

- [Polymarket CLI](https://github.com/Polymarket/polymarket-cli) がインストール済みであること
- Node.js 18+
- [OpenClaw](https://github.com/openclaw/openclaw)（Discord 通知用、オプション）

## セットアップ

```bash
git clone https://github.com/br-to/polymarket-monitor.git
cd polymarket-monitor

# 対話的セットアップ（監視カテゴリ・閾値を選択）
node odds_scanner.js --setup
```

セットアップウィザードで以下を設定できます:

- 監視カテゴリの選択（FRB利下げ、原油価格、イラン情勢など）
- アラート閾値（デフォルト: 3%）
- カスタムカテゴリの追加

設定は `config.json` に保存されます。

## デフォルトカテゴリ

| カテゴリ | 検索キーワード | 関連銘柄 |
|---|---|---|
| FRB利下げ/利上げ | Fed rate | XLF, VNQ, TLT |
| 原油価格 | oil price | XLE, USO, CVX |
| イラン情勢 | Iran | LMT, RTX, XLE |
| 景気後退 | recession | SPY, QQQ, TLT |
| トランプ関税 | Trump tariff | EEM, FXI, SPY |
| 中国情勢 | China | FXI, KWEB, BABA |
| NVIDIA/半導体 | NVIDIA | NVDA, SMH, AMD |
| AI規制 | AI regulation | MSFT, GOOGL, META |
| イスラエル停戦 | Israel ceasefire | LMT, RTX, XLE |
| 日銀政策 | Bank of Japan | EWJ, FXY, DXJ |

## 使い方

### 手動実行

```bash
node odds_scanner.js
```

### crontab で定期実行（例: 3時間ごと）

```cron
0 0,3,6,9,12,15,18,21 * * * cd /path/to/polymarket-monitor && node odds_scanner.js >> /tmp/polymarket-scan.log 2>&1
```

### OpenClaw + Discord 通知付き

```cron
0 0,3,6,9,12,15,18,21 * * * /path/to/scan_and_notify.sh >> /tmp/polymarket-scan.log 2>&1
```

## 環境変数

| 変数 | 説明 | 例 |
|---|---|---|
| `POLYMARKET_CLI_PATH` | Polymarket CLI のパス | `/usr/local/bin/polymarket` |
| `NOTIFY_CHANNEL` | Discord チャンネル ID（通知先） | `1234567890` |
| `NOTIFY_ACCOUNT` | OpenClaw アカウント名（省略可） | `blues` |

## 仕組み

1. `config.json`（または `config.default.json`）からカテゴリを読み込み
2. 各カテゴリで Polymarket CLI を使って市場を検索
3. 前回のオッズ（`odds_history.json`）と比較し、閾値以上の変動をアラート
4. アラートに関連米国株ティッカーを表示
5. `scan_and_notify.sh` 経由で OpenClaw → Discord に通知（オプション）

## アラート出力例

```
🚨 Polymarket オッズ急変動検知

📈 Fed rate cut by July 2026?
  70.0% → 85.0% (+15.0%)
  流動性: $2,056,000 | カテゴリ: FRB利下げ/利上げ
  📊 関連銘柄: XLF, VNQ, TLT
```

## ライセンス

MIT
