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

  # signal-bridge: シグナル記録（moomoo発注はオプション）
  if [ -f "$SCRIPT_DIR/latest_alerts.json" ]; then
    echo "signal-bridge: processing alerts..."
    VENV_PYTHON="${SIGNAL_BRIDGE_PYTHON:-/home/toikobara_komlock_lab_com/moomoo-bridge/venv/bin/python3}"
    if [ -x "$VENV_PYTHON" ]; then
      $VENV_PYTHON -m signal_bridge.pipeline \
        --alerts-file "$SCRIPT_DIR/latest_alerts.json" \
        ${SIGNAL_BRIDGE_EXECUTE:+--execute} \
        2>&1
      echo "signal-bridge: done"
    else
      echo "signal-bridge: Python venv not found at $VENV_PYTHON, skipping"
    fi
  fi

  # 通知（環境変数で設定）
  if [ -n "$NOTIFY_CHANNEL" ]; then
    openclaw message send \
      --channel discord \
      ${NOTIFY_ACCOUNT:+--account "$NOTIFY_ACCOUNT"} \
      --target "$NOTIFY_CHANNEL" \
      --message "以下のPolymarketオッズ急変動を分析して。変動理由（最新ニュース）と関連する株/クリプト銘柄への影響を教えて。

$ALERT_MSG" \
      2>&1
    echo "分析依頼送信完了"
  fi

else
  if [ -n "$NOTIFY_CHANNEL" ]; then
    openclaw message send \
      --channel discord \
      ${NOTIFY_ACCOUNT:+--account "$NOTIFY_ACCOUNT"} \
      --target "$NOTIFY_CHANNEL" \
      --message "定時スキャン完了 — 変動なし（監視市場数: $(echo "$OUTPUT" | grep -oP '監視市場数: \K[0-9]+')）" \
      2>&1
  fi
  echo "変動なし"
fi
echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] scan done"
