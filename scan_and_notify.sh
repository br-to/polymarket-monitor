#!/bin/bash
# Polymarket odds scan → ブルースに分析依頼
set -e
export PATH="/usr/bin:/home/toikobara_komlock_lab_com/.npm-global/bin:$PATH"
export HOME="/home/toikobara_komlock_lab_com"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] scan starting..."
OUTPUT=$(node "$SCRIPT_DIR/odds_scanner.js" 2>&1)
echo "$OUTPUT"

if echo "$OUTPUT" | grep -q "アラートを検知"; then
  ALERT_MSG=$(echo "$OUTPUT" | grep -A 200 "🚨")

  # 関連資産の価格を記録
  echo "correlation_tracker: recording prices..."
  node "$SCRIPT_DIR/correlation_tracker.js" 2>&1
  echo "correlation_tracker: done"

  # ブルースに分析依頼（1回だけ送信）
  openclaw message send \
    --channel discord \
    --account blues \
    --target 1476585311164305408 \
    --message "以下のPolymarketオッズ急変動を分析して。変動理由（最新ニュース）と関連する株/クリプト銘柄への影響を教えて。

$ALERT_MSG" \
    2>&1
  echo "ブルースに分析依頼送信完了"

else
  openclaw message send \
    --channel discord \
    --account blues \
    --target 1476585311164305408 \
    --message "定時スキャン完了 — 変動なし（監視市場数: $(echo "$OUTPUT" | grep -oP '監視市場数: \K[0-9]+')）" \
    2>&1
  echo "変動なし - 通知済み"
fi
echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] scan done"
