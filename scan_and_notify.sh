#!/bin/bash
# Polymarket odds scan → Discord通知
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

  # アラート検知直後に自動取引チェック実行
  echo "auto_trader: checking for trades..."
  cd "$SCRIPT_DIR" && source moomoo-venv/bin/activate && python3 auto_trader.py 2>&1
  echo "auto_trader: done"

  # 通知（デフォルト: #予測市場）
  NOTIFY_CHANNEL="${NOTIFY_CHANNEL:-1476585311164305408}"
  NOTIFY_ACCOUNT="${NOTIFY_ACCOUNT:-blues}"
  
  FULL_MESSAGE="$ALERT_MSG"
  
  openclaw message send \
    --channel discord \
    --account "$NOTIFY_ACCOUNT" \
    --target "$NOTIFY_CHANNEL" \
    --message "$FULL_MESSAGE" \
    2>&1
  echo "分析依頼送信完了"

else
  echo "変動なし"
fi
echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] scan done"
