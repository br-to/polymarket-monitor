import os
REAL_ACCOUNT_ID = int(os.environ.get("MOOMOO_ACCOUNT_ID", "0"))
#!/usr/bin/env python3
"""
BAC売却完了後、自動でOXY全額購入
プレマーケット開場（09:30 UTC）以降に実行
"""

import sys
sys.path.insert(0, '/home/toikobara_komlock_lab_com/polymarket-monitor/moomoo-venv/lib/python3.11/site-packages')
from moomoo import *
import json
from datetime import datetime
import time

def main():
    print(f'[{datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC] BAC売却→OXY購入チェック開始')
    
    trd_ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host='127.0.0.1',
        security_firm=SecurityFirm.FUTUJP
    )
    
    # BAC保有確認
    ret_pos, data_pos = trd_ctx.position_list_query(
        trd_env=TrdEnv.REAL,
        acc_id=REAL_ACCOUNT_ID
    )
    
    has_bac = False
    if ret_pos == 0 and len(data_pos) > 0:
        for _, pos in data_pos.iterrows():
            if pos['code'] == 'US.BAC' and int(pos['qty']) > 0:
                has_bac = True
                break
    
    if has_bac:
        print('BAC保有中。売却完了待ち。')
        trd_ctx.close()
        return
    
    print('✅ BAC売却完了確認')
    
    # 口座残高確認
    ret_acc, data_acc = trd_ctx.accinfo_query(
        trd_env=TrdEnv.REAL,
        acc_id=REAL_ACCOUNT_ID,
        currency=Currency.USD
    )
    
    if ret_acc != 0:
        print('❌ 口座情報取得エラー')
        trd_ctx.close()
        return
    
    cash = data_acc.iloc[0]['cash']
    print(f'現金: ${cash:.2f}')
    
    # OXY価格取得
    quote_ctx = OpenQuoteContext(host='127.0.0.1')
    ret, data = quote_ctx.get_market_snapshot(['US.OXY'])
    
    if ret != 0:
        print('❌ OXY価格取得エラー')
        quote_ctx.close()
        trd_ctx.close()
        return
    
    price = data.iloc[0]['last_price']
    qty = int(cash / price)
    
    print(f'OXY: ${price:.2f}')
    print(f'購入予定: {qty}株')
    
    if qty == 0:
        print('購入可能数0株（資金不足）')
        quote_ctx.close()
        trd_ctx.close()
        return
    
    # 指値注文（1.5%上）
    limit_price = round(price * 1.015, 2)
    
    ret, order_data = trd_ctx.place_order(
        price=limit_price,
        qty=qty,
        code='US.OXY',
        trd_side=TrdSide.BUY,
        order_type=OrderType.NORMAL,
        trd_env=TrdEnv.REAL,
        acc_id=REAL_ACCOUNT_ID
    )
    
    if ret == 0:
        order_id = order_data['order_id'][0]
        print(f'\n✅ OXY購入注文成功')
        print(f'注文ID: {order_id}')
        
        # capital_management更新
        with open('/home/toikobara_komlock_lab_com/polymarket-monitor/capital_management.json', 'r+') as f:
            cap = json.load(f)
            cap['cash'] = round(cash - (price * qty), 2)
            f.seek(0)
            json.dump(cap, f, indent=2)
            f.truncate()
        
        # trade_log更新
        with open('/home/toikobara_komlock_lab_com/polymarket-monitor/trade_log.json', 'r+') as f:
            log = json.load(f)
            log.append({
                'code': 'US.OXY',
                'qty': qty,
                'buy_price': price,
                'buy_timestamp': datetime.utcnow().isoformat(),
                'order_id': order_id,
                'reason': '原油全額投資（Polymarket 5月$110到達78.5%、冬威様指示）',
                'sold': False
            })
            f.seek(0)
            json.dump(log, f, indent=2)
            f.truncate()
        
        print('✅ 全処理完了')
        
        # Discord通知
        try:
            import subprocess
            subprocess.run([
                'openclaw', 'message', 'send', 
                '--channel', 'discord',
                '--target', '1476585311164305408',
                '--message', f'@Kobara Toi\n\n✅ **OXY購入完了**\n\nBAC売却後、OXY {qty}株 @ ${price:.2f} 購入\n注文ID: {order_id}\n\n時刻: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}'
            ], check=False)
        except:
            pass
    else:
        print(f'❌ 購入エラー: {order_data}')
    
    quote_ctx.close()
    trd_ctx.close()

if __name__ == '__main__':
    main()
