#!/usr/bin/env python3
"""
シミュレーション取引テスト
相場権限なしでも発注可能かテスト
"""
import sys
from futu import OpenUSTradeContext, TrdEnv, TrdSide, OrderType

HOST = "127.0.0.1"
PORT = 11111

def test_paper_trade():
    print("=== シミュレーション取引テスト ===\n")
    
    try:
        trd_ctx = OpenUSTradeContext(host=HOST, port=PORT)
        print("✅ Trade API接続成功")
        
        # 成行注文テスト（AAPL 1株）
        stock_code = "US.AAPL"
        qty = 1
        
        print(f"\n発注テスト: BUY {stock_code} x{qty}株（シミュレーション）")
        
        ret, data = trd_ctx.place_order(
            price=0,  # 成行
            qty=qty,
            code=stock_code,
            trd_side=TrdSide.BUY,
            order_type=OrderType.MARKET,
            trd_env=TrdEnv.SIMULATE
        )
        
        if ret == 0:
            print(f"✅ 発注成功！")
            print(f"Order ID: {data['order_id'][0]}")
            print(f"Detail:\n{data}")
        else:
            print(f"❌ 発注失敗: {data}")
        
        trd_ctx.close()
        return ret == 0
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

if __name__ == "__main__":
    success = test_paper_trade()
    sys.exit(0 if success else 1)
