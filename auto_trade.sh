#!/bin/bash
# 自動取引スクリプト
# Polymarketオッズ変動 → moomoo発注
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/moomoo-venv"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Auto trade starting..."

# 1. Polymarketオッズスキャン + シグナル生成
echo "Step 1: Scanning Polymarket odds..."
bash "$SCRIPT_DIR/scan_and_notify.sh"

# 2. シグナルがあればmoomoo発注
if [ -f "$SCRIPT_DIR/trading_signals.json" ]; then
  SIGNAL_COUNT=$(cat "$SCRIPT_DIR/trading_signals.json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
  
  if [ "$SIGNAL_COUNT" -gt 0 ]; then
    echo "Step 2: Executing moomoo trades (${SIGNAL_COUNT} signals)..."
    source "$VENV/bin/activate"
    python3 "$SCRIPT_DIR/moomoo_trader.py"
    deactivate
  else
    echo "Step 2: No signals to execute"
  fi
else
  echo "Step 2: No trading_signals.json found"
fi

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] Auto trade done"
