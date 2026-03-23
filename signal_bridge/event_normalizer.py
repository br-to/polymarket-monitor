"""
Event Normalizer
polymarket-monitorの急変検知をシグナルの統一フォーマットに変換する
"""

import json
import hashlib
from datetime import datetime, timezone


def generate_event_id(market: str, direction: str, detected_at: str) -> str:
    """イベントIDを生成（冪等性チェック用）"""
    raw = f"{market}:{direction}:{detected_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def normalize_event(
    market: str,
    direction: str,
    magnitude: float,
    timeframe_minutes: int,
    detected_at: str = None,
    raw_data: dict = None,
) -> dict:
    """
    急変イベントを統一フォーマットに変換する

    Args:
        market: 市場の説明（例: "Iran ceasefire"）
        direction: "up" or "down"
        magnitude: 変動幅（0.0〜1.0）
        timeframe_minutes: 変動が起きた時間幅（分）
        detected_at: 検知時刻（ISO 8601）。省略時は現在時刻
        raw_data: 元データ（保存用）

    Returns:
        正規化されたイベントdict
    """
    if detected_at is None:
        detected_at = datetime.now(timezone.utc).isoformat()

    # confidence: 変動の大きさと速度で判定
    speed = magnitude / max(timeframe_minutes, 1)
    if magnitude >= 0.10 or speed > 0.02:  # 10%以上 or 1分あたり2%以上
        confidence = 0.9
    elif magnitude >= 0.05 or speed > 0.005:  # 5%以上 or 1分あたり0.5%以上
        confidence = 0.7
    elif magnitude >= 0.03:  # 3%以上
        confidence = 0.5
    else:
        confidence = 0.3

    event_id = generate_event_id(market, direction, detected_at)

    return {
        "event_id": event_id,
        "event_type": "odds_change",
        "market": market,
        "direction": direction,
        "magnitude": magnitude,
        "timeframe_minutes": timeframe_minutes,
        "confidence": confidence,
        "detected_at": detected_at,
        "raw_data": raw_data,
    }
