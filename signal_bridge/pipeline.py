"""
Signal Bridge - メインパイプライン
polymarket-monitorの急変 → シグナル記録 → (オプション) moomoo発注
"""

from signal_bridge.event_normalizer import normalize_event
from signal_bridge.strategy_engine import evaluate
from signal_bridge.execution_adapter import MoomooExecutor
from signal_bridge.signal_store import save_event, save_result
from signal_bridge.performance_tracker import get_price


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
        # エントリー時の株価を記録（Yahoo Finance経由、無料）
        entry_price = get_price(intent["ticker"])

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

        # エントリー価格とシグナル情報を付与
        result["entry_price"] = entry_price
        result["confidence"] = intent["confidence"]
        result["reason"] = intent["reason"]
        result["theme"] = intent["theme"]
        result["recorded_at"] = intent["created_at"]

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


def process_alerts_file(alerts_path: str, execute: bool = False, dry_run: bool = True) -> list:
    """
    odds_scanner.jsが出力するlatest_alerts.jsonを読み込んで処理する

    Args:
        alerts_path: latest_alerts.jsonのパス
        execute: moomooで発注するか
        dry_run: 発注のdry_run

    Returns:
        各アラートの処理結果リスト
    """
    import json

    with open(alerts_path) as f:
        alerts = json.load(f)

    all_results = []
    for alert in alerts:
        direction = "up" if alert.get("delta", 0) > 0 else "down"
        magnitude = abs(alert.get("delta", 0)) / 100  # %→小数

        output = process_odds_change(
            market=alert.get("question", ""),
            direction=direction,
            magnitude=magnitude,
            timeframe_minutes=30,  # スキャン間隔がデフォルト30分
            raw_data=alert,
            execute=execute,
            dry_run=dry_run,
        )
        all_results.append(output)

    return all_results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Signal Bridge")
    parser.add_argument("--alerts-file", help="Path to latest_alerts.json from odds_scanner")
    parser.add_argument("--market", help="Market description")
    parser.add_argument("--direction", choices=["up", "down"], help="Direction")
    parser.add_argument("--magnitude", type=float, help="Magnitude (0.0-1.0)")
    parser.add_argument("--timeframe", type=int, default=30, help="Timeframe in minutes")
    parser.add_argument("--execute", action="store_true", help="Execute on moomoo")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run mode")
    parser.add_argument("--live", action="store_true", help="Actually place orders (disables dry-run)")

    args = parser.parse_args()

    if args.live:
        args.dry_run = False

    if args.alerts_file:
        # odds_scanner.jsのアラートファイルから処理
        results = process_alerts_file(args.alerts_file, execute=args.execute, dry_run=args.dry_run)
        print(f"\n=== Signal Bridge: {len(results)} alerts processed ===")
        for r in results:
            print(f"  Event: {r['event']['market'][:60]}")
            print(f"  Intents: {r['intents_count']}")
            for res in r["results"]:
                print(f"    {res['ticker']} {res['side']} ${res['size_usd']} -> {res['status']}")

    elif args.market and args.direction and args.magnitude:
        # 手動入力
        output = process_odds_change(
            market=args.market,
            direction=args.direction,
            magnitude=args.magnitude,
            timeframe_minutes=args.timeframe,
            execute=args.execute,
            dry_run=args.dry_run,
        )
        print(f"\n=== Signal Bridge ===")
        print(f"Event ID: {output['event']['event_id']}")
        print(f"Confidence: {output['event']['confidence']}")
        print(f"Intents: {output['intents_count']}")
        for r in output["results"]:
            print(f"  {r['ticker']} {r['side']} ${r['size_usd']} -> {r['status']}")

    else:
        # デモ
        output = process_odds_change(
            market="Will there be an Iran ceasefire by April 2026?",
            direction="down",
            magnitude=0.10,
            timeframe_minutes=5,
            execute=False,
        )
        print(f"\n=== Signal Bridge Demo ===")
        print(f"Event ID: {output['event']['event_id']}")
        print(f"Confidence: {output['event']['confidence']}")
        print(f"Intents: {output['intents_count']}")
        for r in output["results"]:
            print(f"  {r['ticker']} {r['side']} ${r['size_usd']} -> {r['status']}")
