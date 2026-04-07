#!/usr/bin/env python3
"""
moomoo接続テスト
"""
import sys
from futu import OpenQuoteContext, OpenUSTradeContext, TrdEnv

HOST = "127.0.0.1"
PORT = 11111

def test_connection():
    print("=== moomoo接続テスト ===\n")
    
    # クォートAPI接続
    print("1. Quote API接続テスト...")
    try:
        quote_ctx = OpenQuoteContext(host=HOST, port=PORT)
        print("✅ Quote API接続成功")
        
        # テスト: QQQの価格取得
        ret, data = quote_ctx.get_market_snapshot(["US.QQQ"])
        if ret == 0:
            price = data['last_price'][0]
            print(f"✅ QQQ現在価格: ${price:.2f}")
        else:
            print(f"⚠️ 価格取得失敗: {data}")
        
        quote_ctx.close()
    except Exception as e:
        print(f"❌ Quote API接続失敗: {e}")
        return False
    
    # トレードAPI接続
    print("\n2. Trade API接続テスト...")
    try:
        trd_ctx = OpenUSTradeContext(host=HOST, port=PORT)
        print("✅ Trade API接続成功")
        
        # テスト: アカウント情報取得
        ret, data = trd_ctx.accinfo_query(trd_env=TrdEnv.SIMULATE)
        if ret == 0:
            print(f"✅ シミュレーション口座確認")
            print(f"  総資産: {data}")
        else:
            print(f"⚠️ アカウント情報取得失敗: {data}")
        
        trd_ctx.close()
    except Exception as e:
        print(f"❌ Trade API接続失敗: {e}")
        return False
    
    print("\n=== 接続テスト完了 ===")
    return True

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
