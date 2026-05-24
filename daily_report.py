#!/usr/bin/env python3
"""
市場閉場時（20:00 UTC）に1日の結果を報告
"""

import json
import subprocess
from datetime import datetime
from moomoo import *

DISCORD_CHANNEL = '1476585311164305408'
DISCORD_ACCOUNT = 'blues'
USER_MENTION = os.environ.get('USER_MENTION', '<@USER_ID>')
REAL_ACCOUNT_ID = int(os.environ.get('MOOMOO_ACCOUNT_ID', '0'))

def get_account_status():
    """口座状況を取得"""
    try:
        trd_ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host='127.0.0.1',
            security_firm=SecurityFirm.FUTUJP
        )
        
        ret_acc, data_acc = trd_ctx.accinfo_query(
            trd_env=TrdEnv.REAL,
            acc_id=REAL_ACCOUNT_ID,
            currency=Currency.USD
        )
        
        if ret_acc != 0:
            trd_ctx.close()
            return None
        
        cash = float(data_acc['cash'][0])
        total = float(data_acc['total_assets'][0])
        market_val = float(data_acc['market_val'][0])
        
        # ポジション取得
        ret_pos, data_pos = trd_ctx.position_list_query(
            trd_env=TrdEnv.REAL,
            acc_id=REAL_ACCOUNT_ID
        )
        
        positions = []
        if ret_pos == 0 and len(data_pos) > 0:
            for _, pos in data_pos.iterrows():
                qty = int(pos['qty'])
                if qty > 0:
                    positions.append({
                        'code': pos['code'],
                        'qty': qty,
                        'cost': float(pos['cost_price']),
                        'current': float(pos['market_val']) / qty,
                        'pl_ratio': float(pos['pl_ratio'])
                    })
        
        trd_ctx.close()
        
        return {
            'cash': cash,
            'total': total,
            'market_val': market_val,
            'positions': positions
        }
    
    except Exception as e:
        print(f"口座情報取得失敗: {e}")
        return None


def get_today_trades():
    """今日の取引を取得"""
    try:
        with open('/home/toikobara_komlock_lab_com/polymarket-monitor/trade_log.json', 'r') as f:
            trade_log = json.load(f)
        
        today = datetime.utcnow().strftime('%Y-%m-%d')
        today_trades = [t for t in trade_log if t['timestamp'][:10] == today]
        
        return today_trades
    except:
        return []


def send_daily_report():
    """1日の結果を報告"""
    
    account = get_account_status()
    if not account:
        print("口座情報取得失敗")
        return
    
    today_trades = get_today_trades()
    
    # 初期資金
    initial_capital = 63.06
    profit = account['total'] - initial_capital
    profit_pct = (profit / initial_capital) * 100
    
    target = 94.59
    remaining = target - account['total']
    remaining_pct = (remaining / account['total']) * 100
    
    # 今日の取引履歴
    trades_summary = ""
    if today_trades:
        trades_summary = "\n\n**今日の取引:**\n"
        for trade in today_trades:
            if trade.get('sold', False):
                sell_reason = trade.get('sell_reason', '売却')
                profit_usd = trade.get('profit_usd', 0)
                trades_summary += f"- {trade['code']}: {sell_reason} (${profit_usd:+.2f})\n"
            else:
                trades_summary += f"- {trade['code']}: 購入 {trade['qty']}株 @ ${trade.get('estimated_price', 0):.2f}\n"
    else:
        trades_summary = "\n\n**今日の取引:** なし"
    
    # ポジション
    positions_summary = ""
    if account['positions']:
        positions_summary = "\n\n**保有ポジション:**\n"
        for pos in account['positions']:
            target_profit = pos['cost'] * 1.07
            positions_summary += f"- {pos['code']}: {pos['qty']}株 @ ${pos['current']:.2f} ({pos['pl_ratio']:+.2f}%)\n"
            positions_summary += f"  利確: ${target_profit:.2f} (+7%)\n"
    else:
        positions_summary = "\n\n**保有ポジション:** なし"
    
    # 報告メッセージ
    message = (
        f"{USER_MENTION}\n\n"
        f"📊 **市場閉場 - 本日の結果**\n\n"
        f"**口座状況:**\n"
        f"- 総資産: ${account['total']:.2f}\n"
        f"- 現金: ${account['cash']:.2f}\n"
        f"- 株式: ${account['market_val']:.2f}\n"
        f"- 累計損益: ${profit:+.2f} ({profit_pct:+.2f}%)\n"
        f"- 目標まで: ${remaining:.2f} ({remaining_pct:+.2f}%)"
        f"{trades_summary}"
        f"{positions_summary}\n\n"
        f"**時刻:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"**目標期日:** 2026-04-23 (残り {(datetime(2026, 4, 23) - datetime.utcnow()).days}日)"
    )
    
    # Discord送信
    subprocess.run([
        '/home/toikobara_komlock_lab_com/.npm-global/bin/openclaw', 'msg', 'send',
        '--channel', 'discord',
        '--account', DISCORD_ACCOUNT,
        '--target', DISCORD_CHANNEL,
        '--message', message
    ])
    
    print("日次レポート送信完了")


if __name__ == '__main__':
    send_daily_report()
