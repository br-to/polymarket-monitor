"""
Performance Tracker
シグナル発生後の株価を追跡し、成績を集計する

株価取得にはyfinance（Yahoo Finance）を使用。
moomooのNasdaq Basic権限不要で米国株の価格を取得できる。
"""

import json
import os
from datetime import datetime, timezone, timedelta

try:
    import yfinance as yf
except ImportError:
    yf = None

from signal_bridge.signal_store import load_all_results, RESULTS_DIR

TRACKER_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "tracker")

# 追跡する時間枠（シグナル発生からの経過時間）
TRACK_INTERVALS = {
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
}


def _ensure_dirs():
    os.makedirs(TRACKER_DIR, exist_ok=True)


def _ticker_to_yahoo(ticker: str) -> str:
    """moomoo形式(US.COIN)をyfinance形式(COIN)に変換"""
    if ticker.startswith("US."):
        return ticker[3:]
    return ticker


def get_price(ticker: str) -> float | None:
    """
    現在の株価を取得する（Yahoo Finance経由）

    Args:
        ticker: moomoo形式 (US.COIN) またはyfinance形式 (COIN)

    Returns:
        現在の株価。取得失敗時はNone
    """
    if yf is None:
        return None

    symbol = _ticker_to_yahoo(ticker)
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        price = info.get("lastPrice") or info.get("last_price")
        return float(price) if price else None
    except Exception:
        return None


def get_historical_price(ticker: str, target_time: datetime) -> float | None:
    """
    指定時刻付近の株価を取得する

    Args:
        ticker: 銘柄コード
        target_time: 取得したい時刻 (UTC)

    Returns:
        指定時刻付近の株価。取得失敗時はNone
    """
    if yf is None:
        return None

    symbol = _ticker_to_yahoo(ticker)
    try:
        start = target_time - timedelta(hours=1)
        end = target_time + timedelta(hours=1)

        t = yf.Ticker(symbol)
        hist = t.history(start=start, end=end, interval="1h")

        if hist.empty:
            # 1時間足がなければ日足で近似
            hist = t.history(start=target_time - timedelta(days=1),
                           end=target_time + timedelta(days=1),
                           interval="1d")

        if not hist.empty:
            # target_timeに最も近い行を取得
            idx = hist.index.get_indexer([target_time], method="nearest")[0]
            return float(hist.iloc[idx]["Close"])

        return None
    except Exception:
        return None


def track_signal(result: dict) -> dict:
    """
    1つのシグナル結果に対して現在の株価を取得し、パフォーマンスを記録する

    Args:
        result: signal_storeのresult dict

    Returns:
        パフォーマンス記録dict
    """
    ticker = result["ticker"]
    current_price = get_price(ticker)

    if current_price is None:
        return {
            "event_id": result["event_id"],
            "ticker": ticker,
            "side": result["side"],
            "error": "price_unavailable",
            "tracked_at": datetime.now(timezone.utc).isoformat(),
        }

    record = {
        "event_id": result["event_id"],
        "ticker": ticker,
        "side": result["side"],
        "size_usd": result.get("size_usd", 0),
        "current_price": current_price,
        "tracked_at": datetime.now(timezone.utc).isoformat(),
        "status": result.get("status", "unknown"),
    }

    return record


def calculate_performance(result: dict, entry_price: float, current_price: float) -> dict:
    """
    エントリー価格と現在価格からパフォーマンスを計算する

    Args:
        result: signal_storeのresult dict
        entry_price: エントリー時の株価
        current_price: 現在の株価

    Returns:
        パフォーマンスdict
    """
    if entry_price == 0:
        return {"error": "entry_price_zero"}

    price_change_pct = (current_price - entry_price) / entry_price

    # BUYなら株価上昇が利益、SELLなら株価下落が利益
    if result["side"] == "BUY":
        pnl_pct = price_change_pct
    else:
        pnl_pct = -price_change_pct

    # シグナルの方向と実際の株価変動が一致したか
    correct = pnl_pct > 0

    return {
        "entry_price": entry_price,
        "current_price": current_price,
        "price_change_pct": round(price_change_pct, 6),
        "pnl_pct": round(pnl_pct, 6),
        "correct": correct,
    }


def generate_report() -> dict:
    """
    全シグナルの成績レポートを生成する

    Returns:
        集計レポートdict
    """
    results = load_all_results()

    if not results:
        return {
            "total_signals": 0,
            "message": "No signals recorded yet",
        }

    total = 0
    with_entry = 0
    correct = 0
    incorrect = 0
    total_pnl_pct = 0.0
    signals = []

    for r in results:
        total += 1
        ticker = r.get("ticker")
        entry_price = r.get("entry_price")
        side = r.get("side")

        signal_info = {
            "event_id": r.get("event_id"),
            "ticker": ticker,
            "side": side,
            "status": r.get("status", "unknown"),
            "entry_price": entry_price,
            "theme": r.get("theme"),
            "reason": r.get("reason"),
            "recorded_at": r.get("recorded_at"),
        }

        # エントリー価格があれば現在価格と比較
        if entry_price and yf is not None:
            current = get_price(ticker)
            if current is not None:
                perf = calculate_performance(r, entry_price, current)
                signal_info.update(perf)
                with_entry += 1
                total_pnl_pct += perf["pnl_pct"]
                if perf["correct"]:
                    correct += 1
                else:
                    incorrect += 1

        signals.append(signal_info)

    win_rate = (correct / with_entry * 100) if with_entry > 0 else 0
    avg_pnl = (total_pnl_pct / with_entry * 100) if with_entry > 0 else 0

    report = {
        "total_signals": total,
        "tracked": with_entry,
        "correct": correct,
        "incorrect": incorrect,
        "win_rate_pct": round(win_rate, 1),
        "avg_pnl_pct": round(avg_pnl, 2),
        "signals": signals,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return report


def save_report(report: dict) -> str:
    """レポートをファイルに保存"""
    _ensure_dirs()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    filepath = os.path.join(TRACKER_DIR, f"report_{timestamp}.json")
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return filepath


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--report":
        report = generate_report()
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Usage: python -m signal_bridge.performance_tracker --report")
