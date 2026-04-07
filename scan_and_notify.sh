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

  # トレーディングシグナル生成
  if [ -f "$SCRIPT_DIR/latest_alerts.json" ]; then
    echo "trading-signals: generating..."
    TRADING_OUTPUT=$(node "$SCRIPT_DIR/trading_signals.js" 2>&1)
    echo "$TRADING_OUTPUT"
    echo "trading-signals: done"
  fi

  # 通知（デフォルト: #予測市場）
  NOTIFY_CHANNEL="${NOTIFY_CHANNEL:-1476585311164305408}"
  NOTIFY_ACCOUNT="${NOTIFY_ACCOUNT:-blues}"
  
  FULL_MESSAGE="以下のPolymarketオッズ急変動を分析して。変動理由（最新ニュース）と関連する株/クリプト銘柄への影響を教えて。

$ALERT_MSG"

  # トレーディングシグナルがあれば追加
  if [ -f "$SCRIPT_DIR/trading_signals.json" ]; then
    SIGNAL_COUNT=$(cat "$SCRIPT_DIR/trading_signals.json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    if [ "$SIGNAL_COUNT" -gt 0 ]; then
      FULL_MESSAGE="$FULL_MESSAGE

---
📊 **トレーディングシグナル: ${SIGNAL_COUNT}件**
$TRADING_OUTPUT"
    fi
  fi
  
  openclaw message send \
    --channel discord \
    --account "$NOTIFY_ACCOUNT" \
    --target "$NOTIFY_CHANNEL" \
    --message "$FULL_MESSAGE" \
    2>&1
  echo "分析依頼送信完了"

else
  NOTIFY_CHANNEL="${NOTIFY_CHANNEL:-1476585311164305408}"
  NOTIFY_ACCOUNT="${NOTIFY_ACCOUNT:-blues}"
  
  openclaw message send \
    --channel discord \
    --account "$NOTIFY_ACCOUNT" \
    --target "$NOTIFY_CHANNEL" \
    --message "定時スキャン完了 — 変動なし（監視市場数: $(echo "$OUTPUT" | grep -oP '監視市場数: \K[0-9]+')）" \
    2>&1
  echo "変動なし"
fi
echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] scan done"
