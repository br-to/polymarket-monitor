# Signal Bridge

Polymarketのオッズ急変を米国株の売買シグナルに変換し、moomoo OpenAPIでペーパートレードを実行する検証基盤。

## セットアップ

```bash
pip install moomoo-api pandas
```

moomoo OpenDが起動している必要があります（localhost:11111）。

## 使い方

```python
from signal_bridge.pipeline import process_odds_change

# シグナル記録のみ（発注なし）
output = process_odds_change(
    market="Will there be an Iran ceasefire by April 2026?",
    direction="down",
    magnitude=0.10,
    timeframe_minutes=5,
)

# ペーパートレードで発注
output = process_odds_change(
    market="Will there be an Iran ceasefire by April 2026?",
    direction="down",
    magnitude=0.10,
    timeframe_minutes=5,
    execute=True,
    dry_run=False,
)
```

## アーキテクチャ

```
odds_scanner.js（急変検知）
  ↓
event_normalizer（統一フォーマットに変換）
  ↓
strategy_engine（テーマ特定 → 関連銘柄マッピング）
  ↓
execution_adapter（moomoo OpenAPIでペーパートレード発注）
```

## テーママッピング

| テーマ | 関連銘柄 |
|--------|----------|
| oil | XLE, USO, OXY |
| semiconductor | NVDA, SOXX, TSM |
| iran_conflict | XLE, USO, OXY, LMT, RTX |
| japan_geopolitical | EWJ |
| china_trade | FXI, KWEB, BABA |
| crypto | COIN, MSTR, MARA |

## 安全装置

- 冪等性（同一イベントの二重発注防止）
- クールダウン（同テーマ60分間隔）
- 固定ポジションサイズ（$1,000/トレード）
- 損切り（3%逆行）
