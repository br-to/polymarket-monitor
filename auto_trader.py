#!/usr/bin/env python3
"""
Polymarket → moomoo 自動取引システム

latest_alerts.jsonを監視し、閾値を超えたら自動取引を実行
保有ポジションを監視し、利確/損切り条件を満たしたら自動売却
"""

import json
import os
import sys
import time
import subprocess
from datetime import datetime, timedelta
from moomoo import *

# 設定
ALERTS_FILE = '/home/toikobara_komlock_lab_com/polymarket-monitor/latest_alerts.json'
TRADE_LOG = '/home/toikobara_komlock_lab_com/polymarket-monitor/trade_log.json'
CAPITAL_MANAGEMENT = '/home/toikobara_komlock_lab_com/polymarket-monitor/capital_management.json'
DISCORD_CHANNEL = os.environ.get('DISCORD_CHANNEL', '1476585311164305408')  # #予測市場
DISCORD_ACCOUNT = os.environ.get('DISCORD_ACCOUNT', 'blues')
THRESHOLD_ENTRY = 6.0  # ±6%でエントリー
THRESHOLD_ALL_IN = 10.0  # ±10%で全額投入

# 売却条件
PROFIT_TARGET = 7.0  # +7%で利確
STOP_LOSS = -3.0  # -3%で損切り
MAX_HOLD_DAYS = 3  # 最大ホールド期間（日）

USER_MENTION = os.environ.get('USER_MENTION', '<@USER_ID>')  # 冬威様

# 初期資金
INITIAL_CAPITAL_USD = 63.06  # 実口座残高

# moomoo設定
MOOMOO_HOST = '127.0.0.1'
MOOMOO_PORT = 11111
SECURITY_FIRM = SecurityFirm.FUTUJP  # moomoo Japan
REAL_ACCOUNT_ID = int(os.environ.get('MOOMOO_ACCOUNT_ID', '0'))  # 実口座ID

# 市場 → 銘柄マッピング（$63で買える銘柄のみ）
MARKET_TO_STOCK = {
    'iran': {
        'up': ['AAL'],  # 停戦確率上昇 → 航空株（$15/株）
        'down': ['OXY']  # 戦争激化 → 原油高 → 石油株（$55/株）
    },
    'oil': {
        'up': [],  # 原油価格上昇 → XLE買えず
        'down': ['AAL']  # 原油価格下落 → 航空株上昇（$15/株）
    },
    'bitcoin': {
        'up': [],  # MSTR ($1,500) 買えず
        'down': []
    },
    'ethereum': {
        'up': [],  # MSTR ($1,500) 買えず
        'down': []
    },
    'fed': {
        'up': ['ARKK'],  # 利下げ確率上昇 → グロース株（$50/株）
        'down': []
    },
    'stablecoin': {
        'up': [],
        'down': []
    },
    'bank of japan': {
        'up': [],
        'down': []
    }
}


def load_alerts():
    """最新のアラートを読み込み"""
    if not os.path.exists(ALERTS_FILE):
        return []
    
    with open(ALERTS_FILE, 'r') as f:
        return json.load(f)


def load_trade_log():
    """取引ログを読み込み"""
    if not os.path.exists(TRADE_LOG):
        return []
    
    with open(TRADE_LOG, 'r') as f:
        return json.load(f)


def save_trade_log(log):
    """取引ログを保存"""
    with open(TRADE_LOG, 'w') as f:
        json.dump(log, f, indent=2)


def send_discord_notification(message):
    """
    Discord #予測市場に直接通知を送信
    
    Args:
        message: 通知メッセージ
    """
    try:
        result = subprocess.run(
            [
                '/home/toikobara_komlock_lab_com/.npm-global/bin/openclaw', 'message', 'send',
                '--channel', 'discord',
                '--account', DISCORD_ACCOUNT,
                '--target', DISCORD_CHANNEL,
                '--message', message
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"  → Discord通知送信成功")
        else:
            print(f"  → Discord通知送信失敗: {result.stderr}")
    except Exception as e:
        print(f"  → Discord通知送信エラー: {e}")


def load_capital_management():
    """資金管理データを読み込み"""
    if not os.path.exists(CAPITAL_MANAGEMENT):
        # 初期化
        return {
            'initial_capital_usd': INITIAL_CAPITAL_USD,
            'current_capital_usd': INITIAL_CAPITAL_USD,
            'reserve_capital_usd': 0.0,  # 余剰資金（端数の蓄積）
            'trades_count': 0,
            'wins': 0,
            'losses': 0,
            'total_profit_usd': 0.0,
            'last_updated': datetime.utcnow().isoformat()
        }
    
    with open(CAPITAL_MANAGEMENT, 'r') as f:
        data = json.load(f)
        # 既存データにreserve_capital_usdがない場合は追加
        if 'reserve_capital_usd' not in data:
            data['reserve_capital_usd'] = 0.0
        return data


def save_capital_management(capital_data):
    """資金管理データを保存"""
    capital_data['last_updated'] = datetime.utcnow().isoformat()
    with open(CAPITAL_MANAGEMENT, 'w') as f:
        json.dump(capital_data, f, indent=2)


def get_target_stocks(query, direction, delta, available_capital=None):
    """
    市場変動から取引すべき銘柄を決定（資金額に応じてフィルタリング）
    
    Args:
        query: 市場キーワード（Iran ceasefire, Oil priceなど）
        direction: 方向（📈 or 📉）
        delta: 変動幅（絶対値）
        available_capital: 利用可能資金（USD）
    
    Returns:
        list: 取引すべき銘柄コードのリスト
    """
    # config.jsonから銘柄リストを取得
    try:
        with open('/home/toikobara_komlock_lab_com/polymarket-monitor/config.json', 'r') as f:
            config = json.load(f)
        
        # カテゴリから一致する銘柄を探す
        stocks = []
        for cat in config['categories']:
            if cat['query'].lower() in query.lower():
                # 方向に応じて銘柄を取得
                if direction == '📈':
                    stocks = cat.get('up', cat.get('tickers', []))
                else:  # 📉
                    stocks = cat.get('down', cat.get('tickers', []))
                break
        
        if not stocks:
            # 旧MARKET_TO_STOCKフォールバック
            for keyword, mapping in MARKET_TO_STOCK.items():
                if keyword.lower() in query.lower():
                    if direction == '📈':
                        stocks = mapping['up']
                    else:
                        stocks = mapping['down']
                    break
        
        if not stocks:
            return []
        
        # 資金額に応じてフィルタリング
        if available_capital is not None:
            affordable = []
            for stock in stocks:
                price = estimate_stock_price(stock)
                if available_capital >= price:
                    affordable.append(stock)
            return affordable
        
        return stocks
    
    except Exception as e:
        print(f"銘柄取得失敗: {e}")
        return []


def estimate_stock_price(code):
    """
    銘柄コードから概算株価を返す（相場カードなしの暫定実装）
    
    Args:
        code: 銘柄コード（例: AAPL）
    
    Returns:
        float: 概算株価
    """
    # 銘柄ごとの概算価格（2026年4月時点の想定）
    price_map = {
        # 航空株
        'AAL': 12.0,   # American Airlines
        'LUV': 35.0,   # Southwest Airlines
        'UAL': 50.0,   # United Airlines
        
        # 原油株
        'OXY': 54.0,   # Occidental Petroleum
        'COP': 100.0,  # ConocoPhillips
        'XOM': 105.0,  # Exxon Mobil
        'CVX': 145.0,  # Chevron
        
        # 金融株
        'BAC': 50.0,   # Bank of America
        
        # その他
        'ARKK': 50.0,  # ARK Innovation ETF
        'QQQ': 450.0,
        'XLE': 85.0,
        'LMT': 450.0,
        'NOC': 480.0,
        'RTX': 100.0,
        'MSTR': 1500.0,
        'COIN': 175.0,
        'AAPL': 257.0
    }
    
    return price_map.get(code, 100.0)  # デフォルト $100


def execute_trade(code, available_capital_usd, reason):
    """
    実際の取引を実行（順次投入型: 利用可能資金を全額投入）
    
    Args:
        code: 銘柄コード（例: AAPL）
        available_capital_usd: 利用可能資金（USD）
        reason: 取引理由
    
    Returns:
        dict: 取引結果
    """
    full_code = f'US.{code}'
    
    # 同じ銘柄の売却注文が存在しないかチェック
    try:
        check_ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host=MOOMOO_HOST,
            port=MOOMOO_PORT,
            security_firm=SECURITY_FIRM
        )
        
        ret, orders = check_ctx.order_list_query(
            order_id="",
            status_filter_list=[OrderStatus.SUBMITTED, OrderStatus.FILLED_PART],
            trd_env=TrdEnv.REAL,
            acc_id=REAL_ACCOUNT_ID
        )
        
        check_ctx.close()
        
        if ret == RET_OK:
            for idx, order in orders.iterrows():
                if order['code'] == full_code and order['trd_side'] == TrdSide.SELL:
                    return {
                        'success': False,
                        'error': f'{full_code}の売却注文が存在します（注文ID: {order["order_id"]}）。買い注文をスキップします。'
                    }
    except Exception as e:
        # チェック失敗時もスキップ（安全側に倒す）
        return {
            'success': False,
            'error': f'売却注文チェック失敗: {e}。安全のため買い注文をスキップします。'
        }
    
    # 概算株価を取得
    estimated_price = estimate_stock_price(code)
    
    # 購入可能株数を計算（端数切り捨て）
    qty = int(available_capital_usd / estimated_price)
    
    if qty == 0:
        return {
            'success': False,
            'error': f'資金不足: ${available_capital_usd:.2f}では{code}（概算${estimated_price:.2f}/株）を購入できません'
        }
    
    try:
        trd_ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host=MOOMOO_HOST,
            port=MOOMOO_PORT,
            security_firm=SECURITY_FIRM
        )
        
        # 取引アンロック（必須）
        ret_unlock, data_unlock = trd_ctx.unlock_trade(password='555123')
        if ret_unlock != RET_OK:
            trd_ctx.close()
            return {'success': False, 'error': f'取引アンロック失敗: {data_unlock}'}
        
        # 注文実行（実口座）
        ret, order_data = trd_ctx.place_order(
            price=0,  # 成行
            qty=qty,
            code=full_code,
            trd_side=TrdSide.BUY,
            order_type=OrderType.MARKET,
            trd_env=TrdEnv.REAL,  # 実口座
            acc_id=REAL_ACCOUNT_ID
        )
        
        trd_ctx.close()
        
        if ret == RET_OK:
            # 投資額を計算（概算: 株数 × 概算価格）
            invested_usd = qty * estimated_price
            
            return {
                'success': True,
                'order_id': order_data['order_id'][0],
                'code': full_code,
                'qty': qty,
                'estimated_price': estimated_price,
                'invested_usd': invested_usd,
                'reason': reason,
                'timestamp': datetime.utcnow().isoformat()
            }
        else:
            return {'success': False, 'error': str(order_data)}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}


def execute_sell(code, qty, reason, original_trade):
    """
    売り注文を実行
    
    Args:
        code: 銘柄コード（US.XXX形式）
        qty: 数量
        reason: 売却理由
        original_trade: 元の買い取引情報
    
    Returns:
        dict: 売却結果
    """
    try:
        trd_ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host=MOOMOO_HOST,
            port=MOOMOO_PORT,
            security_firm=SECURITY_FIRM
        )
        
        # 取引アンロック（必須）
        ret_unlock, data_unlock = trd_ctx.unlock_trade(password='555123')
        if ret_unlock != RET_OK:
            trd_ctx.close()
            return {'success': False, 'error': f'取引アンロック失敗: {data_unlock}'}
        
        # 売り注文実行（実口座）
        ret, order_data = trd_ctx.place_order(
            price=0,  # 成行
            qty=qty,
            code=code,
            trd_side=TrdSide.SELL,
            order_type=OrderType.MARKET,
            trd_env=TrdEnv.REAL,
            acc_id=REAL_ACCOUNT_ID
        )
        
        trd_ctx.close()
        
        if ret == RET_OK:
            return {
                'success': True,
                'order_id': order_data['order_id'][0],
                'code': code,
                'qty': qty,
                'reason': reason,
                'original_trade': original_trade,
                'timestamp': datetime.utcnow().isoformat()
            }
        else:
            return {'success': False, 'error': str(order_data)}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_current_positions():
    """
    保有ポジションを取得
    
    Returns:
        list: 保有ポジション一覧（code, qty, cost等）
    """
    try:
        trd_ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host=MOOMOO_HOST,
            port=MOOMOO_PORT,
            security_firm=SECURITY_FIRM
        )
        
        ret, positions = trd_ctx.position_list_query(
            trd_env=TrdEnv.REAL,
            acc_id=REAL_ACCOUNT_ID
        )
        
        trd_ctx.close()
        
        if ret == RET_OK and len(positions) > 0:
            return positions.to_dict('records')
        else:
            return []
    
    except Exception as e:
        print(f"ポジション取得エラー: {e}")
        return []


def check_and_sell_positions():
    """
    保有ポジションをチェックし、売却条件を満たしたら売却
    """
    print("\n=== 保有ポジションチェック ===")
    
    # 実際の保有ポジションを取得
    positions = get_current_positions()
    
    if not positions:
        print("保有ポジションなし")
        return
    
    # 取引ログから買い注文を取得（売却済みでないもの）
    trade_log = load_trade_log()
    capital_data = load_capital_management()
    
    for pos in positions:
        code = pos['code']
        qty = int(pos['qty'])
        
        # 0株のポジションはスキップ
        if qty == 0:
            continue
        
        cost = float(pos['cost_price'])  # 取得単価
        current_price = float(pos['pl_val']) / qty + cost  # 現在価格（概算）
        pl_ratio = float(pos['pl_ratio'])  # 損益率（%）
        
        print(f"\n銘柄: {code}")
        print(f"  数量: {qty}株")
        print(f"  取得単価: ${cost:.2f}")
        print(f"  現在価格: ${current_price:.2f}")
        print(f"  損益率: {pl_ratio:+.2f}%")
        
        # 対応する買い注文を探す
        original_trade = None
        for trade in trade_log:
            if trade['code'] == code and not trade.get('sold', False):
                original_trade = trade
                break
        
        if not original_trade:
            print("  → 対応する買い注文が見つかりません。スキップ。")
            continue
        
        # 取得日時（buy_timestampまたはtimestampをフォールバック）
        timestamp_key = 'buy_timestamp' if 'buy_timestamp' in original_trade else 'timestamp'
        buy_time = datetime.fromisoformat(original_trade[timestamp_key])
        hold_days = (datetime.utcnow() - buy_time).days
        
        print(f"  保有期間: {hold_days}日")
        
        # 売却判定
        should_sell = False
        reason = ""
        
        if pl_ratio >= PROFIT_TARGET:
            should_sell = True
            reason = f"利確: {pl_ratio:+.2f}%（目標+{PROFIT_TARGET}%達成）"
        elif pl_ratio <= STOP_LOSS:
            should_sell = True
            reason = f"損切り: {pl_ratio:+.2f}%（ストップロス{STOP_LOSS}%）"
        elif hold_days >= MAX_HOLD_DAYS:
            should_sell = True
            reason = f"期間満了: {hold_days}日保有（最大{MAX_HOLD_DAYS}日）"
        
        if should_sell:
            print(f"  → 売却条件満了: {reason}")
            
            # 売却実行
            result = execute_sell(code, qty, reason, original_trade)
            
            if result['success']:
                print(f"    ✅ 売却成功: 注文ID {result['order_id']}")
                
                # 売却額を資金に戻す（実際の取得単価で計算）
                actual_invested = qty * cost  # 実際の投資額
                proceeds = qty * current_price
                profit = proceeds - actual_invested
                
                capital_data['current_capital_usd'] += proceeds
                capital_data['total_profit_usd'] += profit
                
                if profit > 0:
                    capital_data['wins'] += 1
                else:
                    capital_data['losses'] += 1
                
                save_capital_management(capital_data)
                
                # 買い注文を「売却済み」にマーク
                original_trade['sold'] = True
                original_trade['sell_order_id'] = result['order_id']
                original_trade['sell_timestamp'] = result['timestamp']
                original_trade['sell_reason'] = reason
                original_trade['proceeds_usd'] = proceeds
                original_trade['profit_usd'] = profit
                save_trade_log(trade_log)
                
                # 通知
                notification = (
                    f"{USER_MENTION}\n\n"
                    f"💰 **自動売却実行**\n\n"
                    f"**銘柄:** {code}\n"
                    f"**数量:** {qty}株\n"
                    f"**取得単価:** ${cost:.2f}/株\n"
                    f"**売却価格:** ${current_price:.2f}/株（概算）\n"
                    f"**損益率:** {pl_ratio:+.2f}%\n"
                    f"**利益:** ${profit:+.2f}\n"
                    f"**理由:** {reason}\n"
                    f"**注文ID:** {result['order_id']}\n"
                    f"**残資金:** ${capital_data['current_capital_usd']:.2f}\n"
                    f"**時刻:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
                )
                send_discord_notification(notification)
            else:
                print(f"    ❌ 売却失敗: {result['error']}")
        else:
            print(f"  → 保有継続")


def check_strong_signal_swap():
    """
    ±10%以上の強いシグナルがあれば、現在のポジションを即売却して乗り換える
    ±15%以上: 即座に実行
    ±10-15%: 2回連続確認（20分待機）
    """
    print("\n=== 強いシグナルチェック（±10%以上） ===")
    
    # 保有ポジション確認
    positions = get_current_positions()
    if not positions:
        print("保有ポジションなし。スキップ。")
        return
    
    # アラート確認
    alerts = load_alerts()
    if not alerts:
        print("アラートなし。スキップ。")
        return
    
    # config.json読み込み（immediateThreshold取得）
    config_file = '/home/toikobara_komlock_lab_com/polymarket-monitor/config.json'
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        immediate_threshold = config.get('immediateThreshold', 15.0)
        confirmation_required = config.get('confirmationRequired', True)
    except:
        immediate_threshold = 15.0
        confirmation_required = True
    
    # ±10%以上の強いシグナルを探す
    strong_alert = None
    for alert in alerts:
        delta = abs(alert['delta'])
        if delta >= THRESHOLD_ALL_IN:  # 10%以上
            # 取引可能な銘柄があるか確認
            target_stocks = get_target_stocks(alert['query'], alert['direction'], delta)
            if target_stocks:
                strong_alert = alert
                strong_alert['target_stocks'] = target_stocks
                strong_alert['delta_abs'] = delta
                break
    
    if not strong_alert:
        print("±10%以上の強いシグナルなし。スキップ。")
        return
    
    # ±10-15%の場合、2回連続確認が必要
    if confirmation_required and strong_alert['delta_abs'] < immediate_threshold:
        signal_history_file = '/home/toikobara_komlock_lab_com/polymarket-monitor/signal_history.json'
        
        # 過去のシグナル履歴を読み込み
        if os.path.exists(signal_history_file):
            with open(signal_history_file, 'r') as f:
                signal_history = json.load(f)
        else:
            signal_history = []
        
        # 20分以上前のシグナルを削除（クリーンアップ）
        now = datetime.utcnow()
        signal_history = [
            sig for sig in signal_history
            if (now - datetime.fromisoformat(sig['timestamp'])).total_seconds() < 1200
        ]
        
        # 現在のシグナルを記録
        current_signal = {
            'timestamp': datetime.utcnow().isoformat(),
            'market': strong_alert['query'],
            'direction': strong_alert['direction'],
            'delta': strong_alert['delta'],
            'target_stocks': strong_alert['target_stocks']
        }
        
        # 同じ市場の逆方向シグナルがあれば削除（方向転換）
        signal_history = [
            sig for sig in signal_history
            if not (sig['market'] == current_signal['market'] and sig['direction'] != current_signal['direction'])
        ]
        
        # 過去20分以内の同じシグナルを探す
        now = datetime.utcnow()
        recent_signals = []
        for sig in signal_history:
            sig_time = datetime.fromisoformat(sig['timestamp'])
            if (now - sig_time).total_seconds() < 1200:  # 20分以内
                if (sig['market'] == current_signal['market'] and 
                    sig['direction'] == current_signal['direction']):
                    recent_signals.append(sig)
        
        # 2回目のシグナルかチェック
        if len(recent_signals) == 0:
            # 初回シグナル → 記録して待機
            print(f"\n⚠️  ±{strong_alert['delta_abs']:.1f}%シグナル（初回）: {strong_alert['question']}")
            print(f"  → 2回連続確認が必要です。次回のスキャン（10分後）で再確認します。")
            signal_history.append(current_signal)
            with open(signal_history_file, 'w') as f:
                json.dump(signal_history, f, indent=2)
            return
        else:
            # 2回目以降 → 実行
            print(f"\n🚨 ±{strong_alert['delta_abs']:.1f}%シグナル（2回目確認）: {strong_alert['question']}")
            print(f"  → 乗り換えを実行します")
            # 履歴をクリア（該当市場の全シグナルを削除）
            signal_history = [s for s in signal_history if s['market'] != current_signal['market']]
            with open(signal_history_file, 'w') as f:
                json.dump(signal_history, f, indent=2)
    else:
        # ±15%以上 → 即座に実行
        print(f"\n🚨🚨 緊急シグナル（±{strong_alert['delta_abs']:.1f}%）: {strong_alert['question']}")
        print(f"  → 即座に乗り換えを実行します")
        
        # 緊急シグナルの場合も履歴をクリア
        signal_history_file = '/home/toikobara_komlock_lab_com/polymarket-monitor/signal_history.json'
        if os.path.exists(signal_history_file):
            with open(signal_history_file, 'r') as f:
                signal_history = json.load(f)
            # 該当市場の全シグナルを削除
            signal_history = [s for s in signal_history if s['market'] != strong_alert['query']]
            with open(signal_history_file, 'w') as f:
                json.dump(signal_history, f, indent=2)
    
    
    # 損切り後24時間クールダウンチェック（次の銘柄）
    trade_log = load_trade_log()
    target_stocks_ok = []
    for stock in strong_alert['target_stocks']:
        code = f'US.{stock}'
        cooldown_ok = True
        for log in trade_log:
            if log['code'] == code and log.get('sold', False):
                sell_reason = log.get('sell_reason', '')
                if '損切り' in sell_reason or 'stop loss' in sell_reason.lower():
                    sell_time = datetime.fromisoformat(log['sell_timestamp'])
                    hours_since_loss = (datetime.utcnow() - sell_time).total_seconds() / 3600
                    if hours_since_loss < 24:
                        print(f"次の銘柄{stock}: 最近損切り({hours_since_loss:.1f}h前)。あと{24-hours_since_loss:.1f}h待機。")
                        cooldown_ok = False
                        break
        if cooldown_ok:
            target_stocks_ok.append(stock)
    
    if not target_stocks_ok:
        print("全ての次銘柄がクールダウン中。乗り換えスキップ。")
        return
    
    strong_alert['target_stocks'] = target_stocks_ok
    
    # 乗り換え実行
    # trade_logは上で既に読み込み済み
    capital_data = load_capital_management()
    
    for pos in positions:
        code = pos['code']
        qty = int(pos['qty'])
        cost = float(pos['cost_price'])
        pl_ratio = float(pos['pl_ratio'])
        
        # 現在の銘柄（US.XXX → XXX）
        current_stock = code.replace('US.', '')
        
        # 次の銘柄と同じ場合はスキップ
        if current_stock in strong_alert['target_stocks']:
            print(f"\n  銘柄: {code}")
            print(f"  → 次の銘柄も{current_stock}のため、乗り換えスキップ")
            continue
        
        # 手数料を考慮した最低利益チェック
        TRADING_FEE = 0.26  # 売却+購入の往復手数料（0.132% × 2）
        MIN_PROFIT_FOR_SWITCH = 3.0  # 最低利益率（手数料+マージン）
        MAX_PROFIT_FOR_SWITCH = 5.0  # 利確優先：この値以上は乗り換えしない
        
        if pl_ratio < MIN_PROFIT_FOR_SWITCH:
            print(f"\n  銘柄: {code}")
            print(f"  現在損益率: {pl_ratio:+.2f}%")
            print(f"  → 利益率が最低利益{MIN_PROFIT_FOR_SWITCH}%未満。手数料考慮で乗り換えスキップ")
            continue
        
        if pl_ratio >= MAX_PROFIT_FOR_SWITCH:
            print(f"\n  銘柄: {code}")
            print(f"  現在損益率: {pl_ratio:+.2f}%")
            print(f"  → 利益率が{MAX_PROFIT_FOR_SWITCH}%以上。利確優先で乗り換えスキップ")
            continue
        
        # 対応する買い注文を探す
        original_trade = None
        for trade in trade_log:
            if trade['code'] == code and not trade.get('sold', False):
                original_trade = trade
                break
        
        if not original_trade:
            continue
        
        print(f"\n  銘柄: {code}")
        print(f"  現在損益率: {pl_ratio:+.2f}%")
        print(f"  → 即座に売却します")
        
        # 売却実行
        reason = f"強いシグナル乗り換え: {strong_alert['question']} ({strong_alert['delta']:+.1f}%)"
        result = execute_sell(code, qty, reason, original_trade)
        
        if result['success']:
            current_price = cost * (1 + pl_ratio / 100)
            actual_invested = qty * cost  # 実際の投資額
            proceeds = qty * current_price
            profit = proceeds - actual_invested
            
            capital_data['current_capital_usd'] += proceeds
            capital_data['total_profit_usd'] += profit
            
            if profit > 0:
                capital_data['wins'] += 1
            else:
                capital_data['losses'] += 1
            
            save_capital_management(capital_data)
            
            # 買い注文を「売却済み」にマーク
            original_trade['sold'] = True
            original_trade['sell_order_id'] = result['order_id']
            original_trade['sell_timestamp'] = result['timestamp']
            original_trade['sell_reason'] = reason
            original_trade['proceeds_usd'] = proceeds
            original_trade['profit_usd'] = profit
            save_trade_log(trade_log)
            
            # 通知
            notification = (
                f"{USER_MENTION}\n\n"
                f"🔄 **ポジション乗り換え売却**\n\n"
                f"**売却銘柄:** {code}\n"
                f"**数量:** {qty}株\n"
                f"**取得単価:** ${cost:.2f}/株\n"
                f"**売却価格:** ${current_price:.2f}/株（概算）\n"
                f"**損益率:** {pl_ratio:+.2f}%\n"
                f"**利益:** ${profit:+.2f}\n"
                f"**理由:** {reason}\n"
                f"**注文ID:** {result['order_id']}\n"
                f"**残資金:** ${capital_data['current_capital_usd']:.2f}\n"
                f"**時刻:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                f"次の銘柄: {', '.join(strong_alert['target_stocks'])}"
            )
            send_discord_notification(notification)
            print(f"    ✅ 売却成功: 注文ID {result['order_id']}")
        else:
            print(f"    ❌ 売却失敗: {result['error']}")


def auto_reinvest_surplus():
    """
    余剰資金の自動追加投資
    
    条件:
    - 現金 > $20
    - 既存ポジションあり
    - そのポジションが上昇トレンド（損益 > +1%）
    """
    print("\n=== 余剰資金の自動追加投資チェック ===")
    
    capital_data = load_capital_management()
    cash = capital_data['current_capital_usd']
    
    if cash < 20:
        print(f"現金${cash:.2f} < $20。追加投資スキップ。")
        return
    
    positions = get_current_positions()
    if not positions:
        print("保有ポジションなし。追加投資スキップ。")
        return
    
    # 上昇トレンドのポジションを探す
    best_position = None
    best_pl = -999
    
    for pos in positions:
        pl_ratio = float(pos['pl_ratio'])
        if pl_ratio > 1.0 and pl_ratio > best_pl:  # +1%以上かつ最大
            best_position = pos
            best_pl = pl_ratio
    
    if not best_position:
        print("上昇トレンド（+1%以上）のポジションなし。追加投資スキップ。")
        return
    
    code = best_position['code']
    current_price = best_position['market_val'] / best_position['qty']
    qty = int(cash / current_price)
    
    if qty < 1:
        print(f"購入可能株数{qty}株 < 1株。追加投資スキップ。")
        return
    
    # 損切り後24時間クールダウンチェック
    trade_log = load_trade_log()
    for log in trade_log:
        if log['code'] == code and log.get('sold', False):
            sell_reason = log.get('sell_reason', '')
            if '損切り' in sell_reason or 'stop loss' in sell_reason.lower():
                sell_time = datetime.fromisoformat(log['sell_timestamp'])
                hours_since_loss = (datetime.utcnow() - sell_time).total_seconds() / 3600
                if hours_since_loss < 24:
                    print(f"→ {code}: 最近損切り({hours_since_loss:.1f}h前)。あと{24-hours_since_loss:.1f}h待機。")
                    return
    
    print(f"\n💰 余剰資金${cash:.2f}で{code}を追加購入します")
    print(f"  現在損益: {best_pl:+.2f}%（上昇トレンド）")
    print(f"  購入数量: {qty}株 @ ${current_price:.2f}")
    
    result = execute_buy(
        code=code,
        qty=qty,
        reason=f"余剰資金の自動追加投資（現在{best_pl:+.2f}%）",
        market="Auto-reinvest"
    )
    
    if result['success']:
        print(f"✅ 追加購入成功: {result['order_id']}")
    else:
        print(f"❌ 追加購入失敗: {result.get('error', 'Unknown')}")


def sync_capital_management():
    """
    口座残高を確認し、capital_management.jsonと同期する
    """
    try:
        trd_ctx = OpenSecTradeContext(
            filter_trdmarket=TrdMarket.US,
            host=MOOMOO_HOST,
            port=MOOMOO_PORT,
            security_firm=SECURITY_FIRM
        )
        
        # 実口座残高取得
        ret, acc_data = trd_ctx.accinfo_query(
            trd_env=TrdEnv.REAL,
            acc_id=REAL_ACCOUNT_ID,
            currency=Currency.USD
        )
        
        if ret != RET_OK or len(acc_data) == 0:
            trd_ctx.close()
            print(f"  警告: 口座残高取得失敗: {acc_data}")
            return
        
        actual_cash = float(acc_data['cash'][0])
        
        # ポジション情報取得
        ret_pos, data_pos = trd_ctx.position_list_query(
            trd_env=TrdEnv.REAL,
            acc_id=REAL_ACCOUNT_ID
        )
        
        trd_ctx.close()
        
        # capital_management.json読み込み
        capital_data = load_capital_management()
        recorded_cash = capital_data['current_capital_usd']
        
        # 差分チェック（$1以上の差分を検出）
        diff = abs(actual_cash - recorded_cash)
        
        if diff >= 1.0:
            print(f"\n=== 口座残高同期 ===")
            print(f"記録残高: ${recorded_cash:.2f}")
            print(f"実際残高: ${actual_cash:.2f}")
            print(f"差分: ${diff:.2f}")
            
            # 実口座に合わせて修正
            profit_diff = actual_cash - capital_data['initial_capital_usd']
            capital_data['current_capital_usd'] = actual_cash
            capital_data['total_profit_usd'] = profit_diff
            capital_data['last_updated'] = datetime.utcnow().isoformat()
            
            save_capital_management(capital_data)
            print(f"✅ capital_management.jsonを実口座に同期しました")
        else:
            print(f"\n口座残高: ${actual_cash:.2f}（記録と一致）")
        
        # ポジション同期
        if ret_pos == RET_OK and len(data_pos) > 0:
            trade_log = load_trade_log()
            
            for _, pos in data_pos.iterrows():
                code = pos['code']
                actual_qty = int(pos['qty'])
                actual_cost = float(pos['cost_price'])
                
                if actual_qty == 0:
                    continue
                
                # trade_logで未売却の記録を探す
                found = False
                for trade in trade_log:
                    if trade['code'] == code and not trade.get('sold', False):
                        # 数量・コストが一致しているか確認
                        recorded_avg_cost = trade.get('invested_usd', 0) / trade['qty'] if trade['qty'] > 0 else 0
                        if trade['qty'] != actual_qty or abs(recorded_avg_cost - actual_cost) > 0.5:
                            print(f"\n⚠️ {code}の記録が実口座と不一致")
                            print(f"  記録: {trade['qty']}株 @ ${recorded_avg_cost:.2f}")
                            print(f"  実際: {actual_qty}株 @ ${actual_cost:.2f}")
                            print(f"  → 記録を実口座に同期します")
                            trade['qty'] = actual_qty
                            trade['invested_usd'] = actual_qty * actual_cost
                            save_trade_log(trade_log)
                        found = True
                        break
                
                if not found:
                    print(f"\n⚠️ {code}の記録がtrade_logにありません")
                    print(f"  実際: {actual_qty}株 @ ${actual_cost:.2f}")
                    print(f"  → 手動購入として記録します")
                    trade_log.append({
                        'market': 'Manual',
                        'code': code,
                        'qty': actual_qty,
                        'estimated_price': actual_cost,
                        'invested_usd': actual_qty * actual_cost,
                        'reason': '手動購入（自動同期）',
                        'order_id': 'MANUAL_' + datetime.utcnow().strftime('%Y%m%d%H%M%S'),
                        'timestamp': datetime.utcnow().isoformat(),
                        'sold': False
                    })
                    save_trade_log(trade_log)
    
    except Exception as e:
        print(f"  警告: 口座残高同期失敗: {e}")


def main():
    """メイン処理"""
    print(f"[{datetime.utcnow().isoformat()}] Polymarket自動取引チェック開始")
    
    # 0. 米国市場開場時間チェック
    now = datetime.utcnow()
    weekday = now.weekday()  # 0=月曜, 6=日曜
    hour = now.hour
    minute = now.minute
    
    # 市場開場時間: 月-金 13:30-20:00 UTC
    is_trading_day = weekday < 5  # 月-金
    is_trading_hours = (13 < hour < 20) or (hour == 13 and minute >= 30)
    is_market_open = is_trading_day and is_trading_hours
    
    # 市場閉場中は全ての売買を停止
    if not is_market_open:
        day_name = ['月','火','水','木','金','土','日'][weekday]
        print(f"\n⚠️ 米国市場閉場中（{day_name}曜 {hour:02d}:{minute:02d} UTC）")
        print("全ての売買を停止します。口座残高同期のみ実行。")
        sync_capital_management()
        print("\n市場閉場中のため売買を停止。終了。")
        return
    
    # 市場開場中のみ以下を実行
    
    # 0. 口座残高同期
    sync_capital_management()
    
    # 1. 保有ポジションの売却チェック
    check_and_sell_positions()
    
    # 2. 強いシグナル（±10%以上）で乗り換えチェック
    check_strong_signal_swap()
    
    # 2.5. 余剰資金の自動追加投資
    auto_reinvest_surplus()
    
    # 3. 新規買い注文チェック
    # 資金管理データ読み込み
    capital_data = load_capital_management()
    available_capital = capital_data['current_capital_usd'] + capital_data.get('reserve_capital_usd', 0.0)
    
    print(f"利用可能資金: ${available_capital:.2f}")
    print(f"  内訳: 現金 ${capital_data['current_capital_usd']:.2f} + 余剰蓄積 ${capital_data.get('reserve_capital_usd', 0.0):.2f}")
    
    # 資金が$10未満の場合は取引停止
    if available_capital < 10.0:
        print("資金不足。取引停止。")
        return
    
    # アラート読み込み
    alerts = load_alerts()
    if not alerts:
        print("アラートなし。終了。")
        return
    
    # Iran市場の短期優先処理
    # 複数のIran市場がある場合、最も近い期限のものだけを残す
    iran_alerts = [a for a in alerts if 'iran' in a['query'].lower() and 'ceasefire' in a['query'].lower()]
    other_alerts = [a for a in alerts if a not in iran_alerts]
    
    if len(iran_alerts) > 1:
        print(f"\n=== 複数Iran市場検知 ({len(iran_alerts)}件) ===")
        # 質問文から期限を抽出してソート（例: "April 22", "April 30"）
        import re
        for a in iran_alerts:
            # "April 22", "May 31" などを抽出
            match = re.search(r'(\w+ \d+)', a['question'])
            if match:
                a['_deadline'] = match.group(1)
                print(f"  {a['_deadline']}: {a['delta']:+.1f}%")
            else:
                a['_deadline'] = 'ZZZ'  # 期限不明は最後尾
        
        # 期限でソート（昇順）
        iran_alerts.sort(key=lambda x: x.get('_deadline', 'ZZZ'))
        selected_iran = iran_alerts[0]
        print(f"  → 短期市場優先: {selected_iran['_deadline']} ({selected_iran['delta']:+.1f}%)")
        
        # 最も近い期限のものだけを残す
        alerts = [selected_iran] + other_alerts
    
    # 取引ログ読み込み
    trade_log = load_trade_log()
    
    # 各アラートを処理
    for alert in alerts:
        delta = abs(alert['delta'])
        direction = alert['direction']
        query = alert['query']
        
        print(f"\n市場: {alert['question']}")
        print(f"変動: {alert['delta']:+.1f}% ({direction})")
        
        # 閾値チェック
        if delta < THRESHOLD_ENTRY:
            print(f"  → 変動{delta:.1f}%は閾値{THRESHOLD_ENTRY}%未満。スキップ。")
            continue
        
        # 取引すべき銘柄を決定（資金額に応じてフィルタリング）
        target_stocks = get_target_stocks(query, direction, delta, capital_data['current_capital_usd'])
        if not target_stocks:
            print(f"  → 対応銘柄なし。スキップ。")
            continue
        
        print(f"  → 対応銘柄: {', '.join(target_stocks)}")
        
        # 取引理由
        if delta >= THRESHOLD_ALL_IN:
            reason = f"±10%超変動: {alert['delta']:+.1f}%"
        else:
            reason = f"±6%超変動: {alert['delta']:+.1f}%"
        
        # 各銘柄に注文（資金がある限り）
        for stock in target_stocks:
            # 資金チェック
            if capital_data['current_capital_usd'] < 10.0:
                print(f"  → 資金不足。これ以上の取引をスキップ。")
                break
            
            # 損切り後24時間クールダウンチェック
            code = f'US.{stock}'
            cooldown_ok = True
            for log in trade_log:
                if log['code'] == code and log.get('sold', False):
                    sell_reason = log.get('sell_reason', '')
                    if '損切り' in sell_reason or 'stop loss' in sell_reason.lower():
                        sell_time = datetime.fromisoformat(log['sell_timestamp'])
                        hours_since_loss = (datetime.utcnow() - sell_time).total_seconds() / 3600
                        if hours_since_loss < 24:
                            print(f"  → {stock}: 最近損切り({hours_since_loss:.1f}h前)。あと{24-hours_since_loss:.1f}h待機。")
                            cooldown_ok = False
                            break
            
            if not cooldown_ok:
                continue
            
            # 重複チェック（同じ市場・同じ銘柄で既に取引済みか）
            already_traded = any(
                log.get('code') == f'US.{stock}' and 
                log.get('market') == query and
                log.get('timestamp', '')[:10] == datetime.utcnow().isoformat()[:10]  # 同日
                for log in trade_log
            )
            
            if already_traded:
                print(f"  → {stock}: 本日既に取引済み。スキップ。")
                continue
            
            # 取引実行前に確認通知を送る（メンションなし）
            pre_notification = (
                f"⚠️ **取引実行確認**\n\n"
                f"以下の取引を実行します：\n\n"
                f"**市場:** {alert['question']}\n"
                f"**変動:** {alert['delta']:+.1f}% ({direction})\n"
                f"**銘柄:** {stock}\n"
                f"**数量:** 概算 {int(capital_data['current_capital_usd'] / estimate_stock_price(stock))}株\n"
                f"**投資額:** ${capital_data['current_capital_usd']:.2f}\n"
                f"**理由:** {reason}\n"
                f"**時刻:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                f"10秒後に自動実行されます。"
            )
            send_discord_notification(pre_notification)
            
            # 10秒待機（確認の猶予）
            print(f"  → 取引実行前確認通知を送信しました。10秒待機...")
            time.sleep(10)
            
            # 取引実行（全額投入）
            print(f"  → {stock} 全額投入（${capital_data['current_capital_usd']:.2f}）...")
            result = execute_trade(stock, capital_data['current_capital_usd'], reason)
            
            if result['success']:
                print(f"    ✅ 成功: 注文ID {result['order_id']}")
                print(f"       数量: {result['qty']}株 @ ${result['estimated_price']:.2f}")
                print(f"       投資額: ${result['invested_usd']:.2f}")
                
                # 余剰資金を計算（端数を蓄積）
                # 利用可能資金全体 (current + reserve) から投資額を引く
                total_available = capital_data['current_capital_usd'] + capital_data['reserve_capital_usd']
                surplus = total_available - result['invested_usd']
                
                # 余剰をreserveに蓄積、currentは0に（全額投入）
                capital_data['reserve_capital_usd'] = surplus
                capital_data['current_capital_usd'] = 0.0
                capital_data['trades_count'] += 1
                
                print(f"       余剰資金: ${surplus:.2f} → 蓄積合計: ${capital_data['reserve_capital_usd']:.2f}")
                
                save_capital_management(capital_data)
                
                # ログ記録
                trade_log.append({
                    'market': query,
                    'code': result['code'],
                    'qty': result['qty'],
                    'estimated_price': result['estimated_price'],
                    'invested_usd': result['invested_usd'],
                    'reason': reason,
                    'order_id': result['order_id'],
                    'timestamp': result['timestamp'],
                    'sold': False  # 売却フラグ
                })
                save_trade_log(trade_log)
                
                # 通知を保留キューに追加
                notification = (
                    f"{USER_MENTION}\n\n"
                    f"🤖 **自動取引実行**\n\n"
                    f"**市場:** {alert['question']}\n"
                    f"**変動:** {alert['delta']:+.1f}% ({direction})\n"
                    f"**銘柄:** {stock} ({result['code']})\n"
                    f"**数量:** {result['qty']}株\n"
                    f"**概算価格:** ${result['estimated_price']:.2f}/株\n"
                    f"**投資額:** ${result['invested_usd']:.2f}\n"
                    f"**理由:** {reason}\n"
                    f"**注文ID:** {result['order_id']}\n"
                    f"**余剰蓄積:** ${capital_data['reserve_capital_usd']:.2f}\n"
                    f"**残資金:** ${capital_data['current_capital_usd']:.2f}\n"
                    f"**時刻:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
                )
                send_discord_notification(notification)
            else:
                print(f"    ❌ 失敗: {result['error']}")
                
                # 失敗通知を追加
                failure_notification = (
                    f"{USER_MENTION}\n\n"
                    f"⚠️ **自動取引失敗**\n\n"
                    f"**市場:** {alert['question']}\n"
                    f"**変動:** {alert['delta']:+.1f}% ({direction})\n"
                    f"**銘柄:** {stock}\n"
                    f"**理由:** {reason}\n"
                    f"**エラー:** {result['error']}\n"
                    f"**時刻:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
                )
                send_discord_notification(failure_notification)
    
    print(f"\n[{datetime.utcnow().isoformat()}] 自動取引チェック完了")
    print(f"最終残資金: ${capital_data['current_capital_usd']:.2f}")


if __name__ == '__main__':
    main()
