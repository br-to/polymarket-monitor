#!/usr/bin/env python3
"""
1日の取引結果サマリーをpending_notifications.jsonに書き出す
"""

import json
import os
from datetime import datetime, timedelta

# 設定
TRADE_LOG = '/home/toikobara_komlock_lab_com/polymarket-monitor/trade_log.json'
PENDING_NOTIFICATIONS = '/home/toikobara_komlock_lab_com/polymarket-monitor/pending_notifications.json'
USER_MENTION = os.environ.get('USER_MENTION', '<@USER_ID>')  # 冬威様


def load_trade_log():
    """取引ログを読み込み"""
    if not os.path.exists(TRADE_LOG):
        return []
    
    with open(TRADE_LOG, 'r') as f:
        return json.load(f)


def load_pending_notifications():
    """保留中の通知を読み込み"""
    if not os.path.exists(PENDING_NOTIFICATIONS):
        return []
    
    with open(PENDING_NOTIFICATIONS, 'r') as f:
        return json.load(f)


def save_pending_notifications(notifications):
    """保留中の通知を保存"""
    with open(PENDING_NOTIFICATIONS, 'w') as f:
        json.dump(notifications, f, indent=2)


def main():
    """1日のサマリーを作成してキューに追加"""
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    
    # 取引ログ読み込み
    trade_log = load_trade_log()
    
    # 昨日の取引を抽出
    yesterday_trades = [
        t for t in trade_log
        if t['timestamp'][:10] == yesterday.isoformat()
    ]
    
    if not yesterday_trades:
        print(f"{yesterday}: 取引なし。通知スキップ。")
        return
    
    # サマリー作成（メンションなし）
    summary = f"📊 **取引サマリー: {yesterday.strftime('%Y年%m月%d日')}**\n\n"
    summary += f"**取引数:** {len(yesterday_trades)}件\n\n"
    
    for i, trade in enumerate(yesterday_trades, 1):
        summary += f"**{i}. {trade['code']}**\n"
        summary += f"   数量: {trade['qty']}株\n"
        summary += f"   理由: {trade['reason']}\n"
        summary += f"   注文ID: {trade['order_id']}\n"
        summary += f"   時刻: {trade['timestamp'][11:16]} UTC\n\n"
    
    summary += "---\n"
    summary += f"目標: 1週間で1.5倍（$67 → $100.5）達成まで残り{(datetime(2026, 4, 16) - datetime.utcnow()).days}日"
    
    # pending_notifications.jsonに追加
    notifications = load_pending_notifications()
    notifications.append({
        'message': summary,
        'timestamp': datetime.utcnow().isoformat()
    })
    save_pending_notifications(notifications)
    
    print(f"{yesterday}: サマリーを通知キューに追加しました。")


if __name__ == '__main__':
    main()
