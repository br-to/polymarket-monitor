# polymarket-monitor

Polymarket のオッズ変動を定期監視し、急変動を検知するツール。関連する米国株ティッカーも表示し、**トレーディングシグナルを自動生成**します。

## 特徴

- 📊 Polymarket オッズ変動の自動監視
- 🎯 米国株トレーディングシグナル自動生成
- 💹 超短期トレード向け設定（閾値 6%/10%）
- 🔔 Discord リアルタイム通知
- 📈 関連銘柄の自動マッピング

## 構成

| ファイル | 役割 |
|---|---|
| `odds_scanner.js` | Polymarket CLI でマーケットを検索し、前回比で急変動を検知 |
| `trading_signals.js` | **オッズ変動 → 米国株売買シグナル自動生成** |
| `moomoo_trader.py` | **moomoo証券API取引実行** |
| `test_moomoo.py` | moomoo接続テスト |
| `test_paper_trade.py` | シミュレーション発注テスト |
| `auto_trade.sh` | 自動取引スクリプト（スキャン → シグナル → 発注） |
| `setup.js` | 対話的セットアップウィザード |
| `config.json` | トレーディング設定（閾値・資金管理） |
| `config.default.json` | デフォルト設定テンプレート |
| `correlation_tracker.js` | アラート検知時に関連資産の価格を記録 |
| `scan_and_notify.sh` | エントリーポイント。スキャン実行 → シグナル生成 → Discord 通知 |

## 前提

- [Polymarket CLI](https://github.com/Polymarket/polymarket-cli) がインストール済みであること
- Node.js 18+
- Python 3.8+ (moomoo API用)
- [OpenClaw](https://github.com/openclaw/openclaw)（Discord 通知用、オプション）
- moomoo証券アカウント + OpenD（取引実行用、オプション）

## セットアップ

```bash
git clone https://github.com/br-to/polymarket-monitor.git
cd polymarket-monitor

# 対話的セットアップ（監視カテゴリ・閾値を選択）
node odds_scanner.js --setup
```

セットアップウィザードで以下を設定できます:

- 監視カテゴリの選択（FRB利下げ、原油価格、イラン情勢など）
- アラート閾値（デフォルト: **6%** - 超短期トレード向け）
- カスタムカテゴリの追加

設定は `config.json` に保存されます。

## トレーディング設定

`config.json` の `trading` セクション：

```json
{
  "trading": {
    "enabled": true,
    "initialCapital": 10000,        // 初期資金（円）
    "takeProfitPartial": 3.0,       // 部分利確: +3%
    "takeProfitFull": 5.0,          // 全利確: +5%
    "stopLoss": -3.0,               // 損切り: -3%
    "maxHoldDays": 3,               // 最長保有: 3日
    "maxPositions": 1               // 同時保有: 1銘柄（全額集中）
  }
}
```

## 監視カテゴリ（超短期トレード向け）

| カテゴリ | 検索キーワード | 関連銘柄 | 戦略 |
|---|---|---|---|
| FRB利下げ/利上げ | Fed rate | QQQ, TLT, JPM | 利下げ期待↑→グロース株買い |
| 原油価格 | oil | XOM, CVX, AAL | 原油高↑→エネルギー株買い |
| イラン情勢 | Iran | LMT, RTX, AAL | 地上侵攻↑→防衛株 / 停戦↑→航空株 |
| BTC価格 | Bitcoin | MSTR, COIN | BTC上昇期待↑→クリプト関連株買い |
| ETH価格 | Ethereum | MSTR, COIN | ETH上昇期待↑→クリプト関連株買い |

## 使い方

### 手動実行

```bash
# オッズスキャン + トレーディングシグナル生成
bash scan_and_notify.sh
```

### crontab で定期実行（例: 毎時）

```cron
0 */1 * * * /path/to/scan_and_notify.sh >> /tmp/polymarket-scan.log 2>&1
```

## 環境変数

| 変数 | 説明 | 例 |
|---|---|---|
| `POLYMARKET_CLI_PATH` | Polymarket CLI のパス | `/usr/local/bin/polymarket` |
| `NOTIFY_CHANNEL` | Discord チャンネル ID（通知先） | `1476585311164305408` |
| `NOTIFY_ACCOUNT` | OpenClaw アカウント名 | `blues` |

## 仕組み

1. `config.json` からカテゴリ・閾値を読み込み
2. 各カテゴリで Polymarket CLI を使って市場を検索
3. 前回のオッズ（`odds_history.json`）と比較し、**閾値 6% 以上**の変動をアラート
4. **`trading_signals.js`** がアラートから売買シグナルを自動生成
5. `scan_and_notify.sh` 経由で OpenClaw → Discord に通知

## アラート + トレーディングシグナル出力例

```
🚨 Polymarket オッズ急変動検知

📈 Fed rate cut by September 2026?
  70.0% → 78.0% (+8.0%)
  流動性: $2,056,000 | カテゴリ: FRB利下げ/利上げ
  📊 関連銘柄: QQQ, TLT, JPM

---
📊 トレーディングシグナル: 3件

[NORMAL] BUY QQQ
  金額: ¥10,000
  根拠: 利下げ期待上昇 → グロース株（QQQ）買い
  Polymarket: Fed rate cut by September 2026? (+8%)
```

## 超短期トレード戦略

### 基本ルール
- **即座にエントリー**（変動検知から 30 分以内）
- **+3% で半分利確**
- **+5% で全利確**
- **-3% で損切り**（絶対）
- **最長保有 3 日**（動かなければ撤退）

### 複利運用
- 1 回目: ¥10,000 → +5% = ¥10,500
- 2 回目: ¥10,500 → +5% = ¥11,025
- 3 回目: ¥11,025 → +5% = ¥11,576
- **5 回成功で ¥12,000 到達**

### リスク管理
- 同時保有: 最大 1 銘柄（全額集中型）
- 連敗時: 3 連敗で一時休止
- 資金管理: 元手を下回ったら停止

## moomoo証券API連携

### 前提条件

- moomoo証券アカウント
- OpenD（moomoo API サーバー）のインストール

### OpenDセットアップ

1. **OpenDダウンロード**
   - [moomoo公式サイト](https://www.moomoo.com/download/OpenAPI)からダウンロード
   - Linux版を選択（Ubuntu/CentOS）

2. **解凍とインストール**
   ```bash
   tar -xzf moomoo_OpenD_*.tar.gz
   cd moomoo_OpenD_*/
   ```

3. **OpenD.xml編集**
   ```xml
   <login_account>あなたのアカウントID</login_account>
   <login_pwd>あなたのパスワード</login_pwd>
   <api_port>11111</api_port>
   ```

4. **OpenD起動**
   ```bash
   ./OpenD &
   ```

5. **ポート確認**
   ```bash
   netstat -an | grep 11111
   # 127.0.0.1:11111 が表示されればOK
   ```

### Python環境セットアップ

```bash
cd polymarket-monitor
python3 -m venv moomoo-venv
source moomoo-venv/bin/activate
pip install futu-api
```

### 接続テスト

```bash
source moomoo-venv/bin/activate
python3 test_moomoo.py
```

成功すると以下が表示されます：
```
✅ Quote API接続成功
✅ Trade API接続成功
✅ シミュレーション口座確認
```

### 取引実行

```bash
# トレーディングシグナルがある場合
source moomoo-venv/bin/activate
python3 moomoo_trader.py
```

実行時の選択肢：
- `yes` - 実際に発注（シミュレーション環境）
- `dry` - ドライラン（発注しない）
- `no` - スキップ

### 注意事項

- デフォルトは**シミュレーション環境**（Paper Trading）
- 本番環境への切り替えは `TrdEnv.REAL` に変更
- 相場権限がなくても成行注文は実行可能
- 概算価格$50で株数を計算（実際の約定価格は異なる）

## ファイル構成

```
polymarket-monitor/
├── odds_scanner.js          # オッズスキャン（v2）
├── trading_signals.js       # トレーディングシグナル生成
├── moomoo_trader.py         # moomoo証券API取引実行
├── test_moomoo.py           # moomoo接続テスト
├── test_paper_trade.py      # シミュレーション発注テスト
├── auto_trade.sh            # 自動取引スクリプト
├── scan_and_notify.sh       # エントリーポイント
├── config.json              # 設定（gitignore）
├── config.default.json      # デフォルト設定
├── positions.json           # ポジション管理（gitignore）
├── odds_history.json        # オッズ履歴（gitignore）
├── trading_signals.json     # 最新シグナル（gitignore）
└── correlation_tracker.js   # 関連資産価格記録
```

## ライセンス

MIT
