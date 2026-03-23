"""
Strategy Engine
正規化されたイベントから、何を買うか・売るかを判断する
"""

import json
import os
from datetime import datetime, timezone

# 市場テーマ → 関連銘柄の固定マッピング
MARKET_TICKER_MAP = {
    "oil": {
        "tickers": ["US.XLE", "US.USO", "US.OXY"],
        "keywords": ["oil", "crude", "petroleum", "opec", "iran", "saudi"],
    },
    "semiconductor": {
        "tickers": ["US.NVDA", "US.SOXX", "US.TSM"],
        "keywords": ["semiconductor", "chip", "nvidia", "tsmc", "taiwan"],
    },
    "japan_geopolitical": {
        "tickers": ["US.EWJ"],
        "keywords": ["japan", "tariff", "yen", "nikkei"],
    },
    "iran_conflict": {
        "tickers": ["US.XLE", "US.USO", "US.OXY", "US.LMT", "US.RTX"],
        "keywords": ["iran", "ceasefire", "strike", "attack", "military"],
    },
    "china_trade": {
        "tickers": ["US.FXI", "US.KWEB", "US.BABA"],
        "keywords": ["china", "trade war", "tariff", "beijing"],
    },
    "crypto": {
        "tickers": ["US.COIN", "US.MSTR", "US.MARA"],
        "keywords": ["bitcoin", "crypto", "btc", "ethereum"],
    },
}

# 安全装置の設定
SAFETY_CONFIG = {
    "cooldown_minutes": 60,      # 同テーマで再発注しない時間
    "position_size_usd": 1000,   # 1トレードあたりの金額
    "max_hold_minutes": 240,     # 最大保有時間
    "stop_loss_pct": 0.03,       # 3%逆行で損切り
    "min_confidence": 0.5,       # この信頼度以下はスキップ
}

# クールダウン管理（テーマ → 最後の発注時刻）
_cooldown_state = {}

# 処理済みイベントID
_processed_events = set()


def _match_theme(market: str) -> list:
    """市場の説明からテーマを特定する"""
    market_lower = market.lower()
    matched = []
    for theme, config in MARKET_TICKER_MAP.items():
        for keyword in config["keywords"]:
            if keyword in market_lower:
                matched.append(theme)
                break
    return matched


def _check_cooldown(theme: str) -> bool:
    """クールダウン中かチェック"""
    if theme not in _cooldown_state:
        return False
    last_time = _cooldown_state[theme]
    now = datetime.now(timezone.utc)
    elapsed = (now - last_time).total_seconds() / 60
    return elapsed < SAFETY_CONFIG["cooldown_minutes"]


def _record_cooldown(theme: str):
    """クールダウンを記録"""
    _cooldown_state[theme] = datetime.now(timezone.utc)


def evaluate(event: dict) -> list:
    """
    イベントを評価して、売買シグナルのリストを返す

    Args:
        event: event_normalizerで正規化されたイベント

    Returns:
        order_intentのリスト。空リストなら「何もしない」
    """
    # 冪等性チェック
    if event["event_id"] in _processed_events:
        return []
    _processed_events.add(event["event_id"])

    # 信頼度チェック
    if event["confidence"] < SAFETY_CONFIG["min_confidence"]:
        return []

    # テーマ特定
    themes = _match_theme(event["market"])
    if not themes:
        return []

    order_intents = []

    for theme in themes:
        # クールダウンチェック
        if _check_cooldown(theme):
            continue

        tickers = MARKET_TICKER_MAP[theme]["tickers"]

        # 方向の決定
        # オッズが下がった（bad event確率上昇）→ 関連銘柄を売り方向
        # オッズが上がった（good event確率上昇）→ 関連銘柄を買い方向
        # ただしiranの停戦確率が下がった → 石油は上がる（買い）
        # これはテーマごとに反転するかどうかを設定する必要がある
        # 最初はシンプルに: down → BUY（リスクオン系はdown=bad=hedge買い）
        if event["direction"] == "down":
            side = "BUY"
        else:
            side = "SELL"

        for ticker in tickers:
            intent = {
                "event_id": event["event_id"],
                "theme": theme,
                "ticker": ticker,
                "side": side,
                "size_usd": SAFETY_CONFIG["position_size_usd"],
                "confidence": event["confidence"],
                "reason": f"{event['market']} {event['direction']} {event['magnitude']:.1%} in {event['timeframe_minutes']}min",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "max_hold_minutes": SAFETY_CONFIG["max_hold_minutes"],
                "stop_loss_pct": SAFETY_CONFIG["stop_loss_pct"],
            }
            order_intents.append(intent)

        _record_cooldown(theme)

    # 重複排除（同じティッカーは1回だけ）
    seen_tickers = set()
    deduped = []
    for intent in order_intents:
        if intent["ticker"] not in seen_tickers:
            seen_tickers.add(intent["ticker"])
            deduped.append(intent)

    return deduped
