#!/usr/bin/env python3
"""
moomoo証券API連携
trading_signals.json → moomoo発注
"""
import json
import sys
import os
from pathlib import Path

try:
    from futu import OpenQuoteContext, OpenUSTradeContext, TrdEnv, TrdSide, OrderType
except ImportError:
    print("❌ futu-api not installed. Run: pip install futu-api")
    sys.exit(1)

# 設定
HOST = os.getenv("MOOMOO_HOST", "127.0.0.1")
PORT = int(os.getenv("MOOMOO_PORT", "11111"))
USD_JPY_RATE = float(os.getenv("USD_JPY_RATE", "150"))  # 為替レート

DATA_DIR = Path(__file__).parent
SIGNALS_FILE = DATA_DIR / "trading_signals.json"
POSITIONS_FILE = DATA_DIR / "positions.json"

def load_signals():
    """シグナル読み込み"""
    if not SIGNALS_FILE.exists():
        print("trading_signals.json not found")
        return []
    
    with open(SIGNALS_FILE) as f:
        return json.load(f)

def load_positions():
    """ポジション読み込み"""
    if not POSITIONS_FILE.exists():
        return {
            "capital": 10000,
            "positions": [],
            "history": []
        }
    
    with open(POSITIONS_FILE) as f:
        return json.load(f)

def save_positions(data):
    """ポジション保存"""
    with open(POSITIONS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_current_price(quote_ctx, ticker):
    """現在価格取得"""
    stock_code = f"US.{ticker}"
    ret, data = quote_ctx.get_market_snapshot([stock_code])
    
    if ret != 0:
        print(f"❌ 価格取得失敗: {data}")
        return None
    
    return data['last_price'][0]

def calculate_quantity(amount_jpy, price_usd):
    """株数計算"""
    amount_usd = amount_jpy / USD_JPY_RATE
    qty = int(amount_usd / price_usd)
    return qty

def place_order(trd_ctx, ticker, action, qty, dry_run=True):
    """
    発注
    dry_run=True: シミュレーションのみ
    dry_run=False: 実際に発注
    """
    stock_code = f"US.{ticker}"
    
    if dry_run:
        print(f"🔵 [DRY RUN] {action} {stock_code} x{qty}株")
        return True, None
    
    # 成行注文
    trd_side = TrdSide.BUY if action == "BUY" else TrdSide.SELL
    
    ret, data = trd_ctx.place_order(
        price=0,  # 成行
        qty=qty,
        code=stock_code,
        trd_side=trd_side,
        order_type=OrderType.MARKET,
        trd_env=TrdEnv.SIMULATE  # シミュレーション環境（本番はTrdEnv.REAL）
    )
    
    if ret == 0:
        print(f"✅ 発注成功: {action} {stock_code} x{qty}株")
        return True, data
    else:
        print(f"❌ 発注失敗: {data}")
        return False, data

def main():
    """メイン処理"""
    signals = load_signals()
    
    if not signals:
        print("シグナルなし")
        return
    
    positions = load_positions()
    
    print(f"現在資金: ¥{positions['capital']:,}")
    print(f"ポジション数: {len(positions['positions'])}")
    print(f"\n📊 トレーディングシグナル: {len(signals)}件\n")
    
    # 接続
    quote_ctx = OpenQuoteContext(host=HOST, port=PORT)
    trd_ctx = OpenUSTradeContext(host=HOST, port=PORT)
    
    for sig in signals:
        print(f"[{sig['strength']}] {sig['action']} {sig['ticker']}")
        print(f"  金額: ¥{sig['amount']:,}")
        print(f"  根拠: {sig['reasoning']}")
        print(f"  Polymarket: {sig['polymarketEvent']} ({sig['delta']:+.1f}%)")
        
        # 株数計算（成行なので概算）
        # 平均的な株価を$50と仮定（相場権限不要）
        estimated_price = 50.0
        qty = calculate_quantity(sig['amount'], estimated_price)
        if qty == 0:
            # 最低1株は買えるようにする
            qty = 1
        
        print(f"  購入株数（概算）: {qty}株")
        
        # 確認プロンプト
        confirm = input("\n  実行しますか？ (yes/no/dry): ")
        
        if confirm.lower() == "yes":
            success, order_data = place_order(trd_ctx, sig['ticker'], sig['action'], qty, dry_run=False)
        elif confirm.lower() == "dry":
            success, order_data = place_order(trd_ctx, sig['ticker'], sig['action'], qty, dry_run=True)
        else:
            print("  スキップ\n")
            continue
        
        if success:
            # ポジション記録
            positions['positions'].append({
                "ticker": sig['ticker'],
                "action": sig['action'],
                "qty": qty,
                "entry_price": estimated_price,  # 概算価格
                "amount": sig['amount'],
                "polymarket_event": sig['polymarketEvent'],
                "timestamp": sig['timestamp']
            })
            
            # 資金更新
            if sig['action'] == "BUY":
                positions['capital'] -= sig['amount']
            
            save_positions(positions)
            print(f"  残り資金: ¥{positions['capital']:,}\n")
    
    quote_ctx.close()
    trd_ctx.close()

if __name__ == "__main__":
    main()
