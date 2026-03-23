"""
Signal Bridge - メインパイプライン
polymarket-monitorの急変 → シグナル記録 → (オプション) moomoo発注
"""

from signal_bridge.event_normalizer import normalize_event
from signal_bridge.strategy_engine import evaluate
from signal_bridge.execution_adapter import MoomooExecutor
from signal_bridge.signal_store import save_event, save_result


def process_odds_change(
    market: str,
    direction: str,
    magnitude: float,
    timeframe_minutes: int,
    detected_at: str = None,
    raw_data: dict = None,
    execute: bool = False,
    dry_run: bool = True,
) -> dict:
    """
    オッズ変動を処理するメインエントリーポイント

    Args:
        market: 市場の説明
        direction: "up" or "down"
        magnitude: 変動幅（0.0〜1.0）
        timeframe_minutes: 変動が起きた時間幅（分）
        detected_at: 検知時刻
        raw_data: 元データ
        execute: Trueならmoomooで発注する
        dry_run: executeがTrueのとき、dry_runならログのみ

    Returns:
        処理結果のdict
    """
    # 1. イベントの正規化
    event = normalize_event(
        market=market,
        direction=direction,
        magnitude=magnitude,
        timeframe_minutes=timeframe_minutes,
        detected_at=detected_at,
        raw_data=raw_data,
    )

    # 2. イベントを保存
    event_path = save_event(event)

    # 3. 戦略エンジンで評価
    intents = evaluate(event)

    # 4. 実行
    results = []
    executor = None

    if execute and intents:
        try:
            executor = MoomooExecutor()
            executor.connect()
        except Exception as e:
            print(f"Failed to connect to moomoo: {e}")
            executor = None

    for intent in intents:
        if execute and executor:
            result = executor.execute(intent, dry_run=dry_run)
        else:
            result = {
                "event_id": intent["event_id"],
                "ticker": intent["ticker"],
                "side": intent["side"],
                "size_usd": intent["size_usd"],
                "dry_run": True,
                "status": "recorded_only",
                "order_id": None,
                "error": None,
            }

        result_path = save_result(result)
        results.append(result)

    if executor:
        executor.close()

    return {
        "event": event,
        "event_path": event_path,
        "intents_count": len(intents),
        "results": results,
    }


if __name__ == "__main__":
    # テスト: イラン停戦確率が5分で10%急落
    output = process_odds_change(
        market="Will there be an Iran ceasefire by April 2026?",
        direction="down",
        magnitude=0.10,
        timeframe_minutes=5,
        execute=False,
    )

    print(f"\n=== Signal Bridge Test ===")
    print(f"Event ID: {output['event']['event_id']}")
    print(f"Confidence: {output['event']['confidence']}")
    print(f"Intents: {output['intents_count']}")
    for r in output["results"]:
        print(f"  {r['ticker']} {r['side']} ${r['size_usd']} -> {r['status']}")
