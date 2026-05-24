import os
REAL_ACCOUNT_ID = int(os.environ.get("MOOMOO_ACCOUNT_ID", "0"))
#!/usr/bin/env python3
"""
売却完了後にOXY全額購入
13:35 UTCに実行（開場5分後、売却完了確認）
"""
import sys
sys.path.insert(0, '/home/toikobara_komlock_lab_com/polymarket-monitor/moomoo-venv/lib/python3.11/site-packages')
from moomoo import OpenQuoteContext, OpenSecTradeContext, TrdMarket, TrdSide, OrderType, TrdEnv, SecurityFirm, Currency
import time

def main():
    trd_ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host='127.0.0.1',
        security_firm=SecurityFirm.FUTUJP
    )
    
    # 現金確認
    ret_acc, data_acc = trd_ctx.accinfo_query(
        trd_env=TrdEnv.REAL,
        acc_id=REAL_ACCOUNT_ID,
        currency=Currency.USD
    )
    
    if ret_acc != 0:
        print("❌ 口座情報取得失敗")
        trd_ctx.close()
        return
    
    cash = data_acc.iloc[0]['cash']
    print(f"現金: ${cash:.2f}")
    
    if cash < 10:
        print("❌ 資金不足（最低$10必要）")
        trd_ctx.close()
        return
    
    # OXY価格取得
    quote_ctx = OpenQuoteContext(host='127.0.0.1')
    ret, data = quote_ctx.get_market_snapshot(['US.OXY'])
    if ret != 0:
        print("❌ OXY価格取得失敗")
        quote_ctx.close()
        trd_ctx.close()
        return
    
    price = data.iloc[0]['last_price']
    qty = int(cash / price)
    quote_ctx.close()
    
    if qty == 0:
        print(f"❌ 資金不足: OXY ${price:.2f}、現金 ${cash:.2f}")
        trd_ctx.close()
        return
    
    print(f"OXY購入: {qty}株 @ ${price:.2f}")
    
    # 成行購入
    ret, data = trd_ctx.place_order(
        price=0,
        qty=qty,
        code='US.OXY',
        trd_side=TrdSide.BUY,
        order_type=OrderType.MARKET,
        trd_env=TrdEnv.REAL,
        acc_id=REAL_ACCOUNT_ID
    )
    
    if ret == 0:
        order_id = data['order_id'].iloc[0]
        print(f"✅ OXY購入成功: {order_id}")
        print(f"銘柄: OXY {qty}株")
        
        # Discord通知
        import requests
        webhook_url = "YOUR_DISCORD_WEBHOOK"  # 後で設定
        # requests.post(webhook_url, json={"content": f"✅ OXY購入: {qty}株 @ ${price:.2f}"})
    else:
        print(f"❌ OXY購入失敗: {data}")
    
    trd_ctx.close()

if __name__ == "__main__":
    main()
