"""
Backtest - Polymarket CLOB APIの過去データ + Yahoo Financeで戦略を検証

使い方:
  python3 -m signal_bridge.backtest --days 14 --threshold 0.03

処理フロー:
  1. odds_history.jsonから監視中の市場一覧を取得
  2. gamma-apiでclobTokenIdsを取得
  3. CLOB APIで価格履歴を取得
  4. 閾値以上の変動を検出
  5. 変動時点の米国株価をYahoo Financeで取得
  6. 複数の評価窓(1h/4h/当日引け/翌営業日)で比較
  7. 結果をCSVで出力
"""

import json
import os
import time
import csv
from datetime import datetime, timezone, timedelta
from io import StringIO

import requests

# Yahoo Finance
try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed. Run: pip install yfinance")
    exit(1)

# ── 設定 ──
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
ODDS_HISTORY = os.path.join(os.path.dirname(__file__), "..", "odds_history.json")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "backtest")

# テーマ → 銘柄マッピング（strategy_engineと同じ）
MARKET_TICKER_MAP = {
    "oil": {
        "tickers": ["XLE", "USO", "OXY"],
        "keywords": ["oil", "crude", "petroleum", "opec"],
    },
    "iran_conflict": {
        "tickers": ["XLE", "USO", "OXY", "LMT", "RTX"],
        "keywords": ["iran", "ceasefire", "strike", "attack", "military"],
    },
    "china_trade": {
        "tickers": ["FXI", "KWEB", "BABA"],
        "keywords": ["china", "trade war", "tariff", "beijing"],
    },
    "crypto": {
        "tickers": ["COIN", "MSTR"],
        "keywords": ["bitcoin", "crypto", "btc", "ethereum"],
    },
    "semiconductor": {
        "tickers": ["NVDA", "SOXX", "TSM"],
        "keywords": ["semiconductor", "chip", "nvidia", "tsmc", "taiwan"],
    },
    "fed_rate": {
        "tickers": ["XLF", "VNQ", "TLT"],
        "keywords": ["fed", "federal funds", "interest rate", "fomc"],
    },
}


def load_monitored_markets():
    """odds_history.jsonから監視中の市場を読み込む"""
    with open(ODDS_HISTORY) as f:
        data = json.load(f)
    markets = []
    for k, v in data.items():
        if k == "_meta":
            continue
        markets.append({
            "condition_id": k,
            "question": v.get("question", ""),
            "category": v.get("category", ""),
            "tickers": v.get("tickers", []),
            "yes_pct": v.get("yes_pct", 0),
            "liquidity": v.get("liquidity", 0),
            "end_date": v.get("end_date", ""),
        })
    return markets


def get_clob_token_id(question: str) -> str | None:
    """polymarket CLI → slug → gamma-api → clobTokenIdを取得"""
    import subprocess
    try:
        # 1. polymarket CLIでslugを取得
        result = subprocess.run(
            ["/usr/local/bin/polymarket", "markets", "search", question, "--limit", "5", "-o", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        cli_markets = json.loads(result.stdout)

        # question完全一致でslugを取得
        slug = None
        q_lower = question.lower().strip()
        for m in cli_markets:
            if m.get("question", "").lower().strip() == q_lower:
                slug = m.get("slug")
                break

        if not slug:
            # 部分一致
            for m in cli_markets:
                if q_lower[:30] in m.get("question", "").lower():
                    slug = m.get("slug")
                    break

        if not slug:
            return None

        # 2. gamma-apiでslug → clobTokenIds
        resp = requests.get(f"{GAMMA_API}/markets", params={"slug": slug}, timeout=10)
        if resp.status_code != 200:
            return None
        markets = resp.json()
        if not markets:
            return None

        tokens = markets[0].get("clobTokenIds", "")
        if isinstance(tokens, str):
            tokens = json.loads(tokens) if tokens else []
        return tokens[0] if tokens else None

    except Exception as e:
        print(f"  Error getting token: {e}")
        return None


def get_price_history(token_id: str, days: int = 14, fidelity: int = 60) -> list:
    """CLOB APIから価格履歴を取得"""
    try:
        now = int(datetime.now(timezone.utc).timestamp())
        start = now - (days * 86400)
        resp = requests.get(
            f"{CLOB_API}/prices-history",
            params={
                "market": token_id,
                "startTs": start,
                "endTs": now,
                "fidelity": fidelity,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("history", [])
    except Exception as e:
        print(f"  Error getting price history: {e}")
        return []


def detect_moves(history: list, threshold: float = 0.03) -> list:
    """価格履歴から閾値以上の変動を検出"""
    if len(history) < 2:
        return []

    moves = []
    for i in range(1, len(history)):
        prev_price = history[i - 1]["p"]
        curr_price = history[i]["p"]

        if prev_price == 0:
            continue

        delta = curr_price - prev_price
        # 絶対変動が閾値以上
        if abs(delta) >= threshold:
            dt = datetime.fromtimestamp(history[i]["t"], tz=timezone.utc)
            # 米国市場営業時間チェック (UTC 12:30-20:00, weekday)
            if dt.weekday() >= 5:
                continue
            hour_min = dt.hour * 60 + dt.minute
            if not (750 <= hour_min <= 1200):
                continue

            moves.append({
                "timestamp": dt,
                "unix_ts": history[i]["t"],
                "prev_price": prev_price,
                "curr_price": curr_price,
                "delta": delta,
                "direction": "up" if delta > 0 else "down",
            })
    return moves


def match_theme(question: str) -> list:
    """質問からテーマを特定"""
    q_lower = question.lower()
    matched = []
    for theme, config in MARKET_TICKER_MAP.items():
        for keyword in config["keywords"]:
            if keyword in q_lower:
                matched.append(theme)
                break
    return matched


def get_stock_prices_at(tickers: list, dt: datetime, windows_hours: list = [1, 4]) -> dict:
    """指定時刻付近の株価と、N時間後の株価を取得
    
    yfinanceの制約: intraday dataは直近60日程度しか取れない
    1分足は直近7日、5分足は直近60日
    """
    results = {}
    # 対象期間を広めに取得
    start_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = (dt + timedelta(days=3)).strftime("%Y-%m-%d")

    for ticker in tickers:
        try:
            data = yf.download(
                ticker, start=start_date, end=end_date,
                interval="1h", progress=False, auto_adjust=True
            )
            if data.empty:
                continue

            # dt に最も近い行を取得
            # pandas Timestamp に変換
            target_ts = dt.replace(tzinfo=None)
            data.index = data.index.tz_localize(None) if data.index.tz else data.index

            # 最も近いインデックスを探す
            diffs = abs(data.index - target_ts)
            nearest_idx = diffs.argmin()
            entry_price = float(data.iloc[nearest_idx]["Close"].iloc[0]) if hasattr(data.iloc[nearest_idx]["Close"], 'iloc') else float(data.iloc[nearest_idx]["Close"])
            entry_time = data.index[nearest_idx]

            ticker_result = {
                "entry_price": entry_price,
                "entry_time": str(entry_time),
            }

            # 各評価窓の価格
            for hours in windows_hours:
                target_exit = target_ts + timedelta(hours=hours)
                future_data = data[data.index >= target_exit]
                if not future_data.empty:
                    exit_price = float(future_data.iloc[0]["Close"].iloc[0]) if hasattr(future_data.iloc[0]["Close"], 'iloc') else float(future_data.iloc[0]["Close"])
                    exit_time = future_data.index[0]
                    pnl_pct = (exit_price - entry_price) / entry_price
                    ticker_result[f"exit_{hours}h_price"] = exit_price
                    ticker_result[f"exit_{hours}h_time"] = str(exit_time)
                    ticker_result[f"exit_{hours}h_pnl"] = pnl_pct
                else:
                    ticker_result[f"exit_{hours}h_price"] = None
                    ticker_result[f"exit_{hours}h_pnl"] = None

            results[ticker] = ticker_result

        except Exception as e:
            print(f"    Error getting {ticker}: {e}")
            continue

    return results


def run_backtest(days: int = 14, threshold: float = 0.03, max_markets: int = 50):
    """メインバックテスト実行"""
    print(f"=== Backtest: {days}d, threshold={threshold:.0%}, max_markets={max_markets} ===")
    print()

    # 1. 監視市場を読み込み
    markets = load_monitored_markets()
    print(f"Monitored markets: {len(markets)}")

    # テーマに一致する市場だけ
    relevant = []
    for m in markets:
        themes = match_theme(m["question"])
        if themes:
            m["themes"] = themes
            relevant.append(m)
    print(f"Theme-matched markets: {len(relevant)}")
    relevant = relevant[:max_markets]
    print(f"Processing: {len(relevant)}")
    print()

    # 2-6. 市場ごとに処理
    all_signals = []
    token_cache = {}

    for i, market in enumerate(relevant):
        q = market["question"][:60]
        print(f"[{i+1}/{len(relevant)}] {q}...")

        # gamma-apiでclobTokenId取得
        token_id = get_clob_token_id(market["question"])
        if not token_id:
            print(f"  -> No token ID found, skip")
            continue
        print(f"  -> Token: {token_id[:20]}...")

        # CLOB APIで価格履歴取得
        history = get_price_history(token_id, days=days)
        if not history:
            print(f"  -> No price history, skip")
            time.sleep(0.3)
            continue
        print(f"  -> {len(history)} data points")

        # 変動検出
        moves = detect_moves(history, threshold=threshold)
        if not moves:
            print(f"  -> No significant moves")
            time.sleep(0.3)
            continue
        print(f"  -> {len(moves)} moves detected")

        # テーマから銘柄取得
        themes = market["themes"]
        tickers = set()
        for t in themes:
            if t in MARKET_TICKER_MAP:
                tickers.update(MARKET_TICKER_MAP[t]["tickers"])
        tickers = list(tickers)

        # 各変動について株価を取得
        for move in moves:
            direction = move["direction"]
            # down → BUY (現在のロジック)
            side = "BUY" if direction == "down" else "SELL"

            stock_data = get_stock_prices_at(tickers, move["timestamp"])
            if not stock_data:
                continue

            for ticker, prices in stock_data.items():
                signal = {
                    "market_question": market["question"],
                    "category": market["category"],
                    "themes": ",".join(themes),
                    "odds_timestamp": move["timestamp"].isoformat(),
                    "odds_prev": move["prev_price"],
                    "odds_curr": move["curr_price"],
                    "odds_delta": move["delta"],
                    "direction": direction,
                    "side": side,
                    "ticker": ticker,
                    "entry_price": prices["entry_price"],
                    "entry_time": prices["entry_time"],
                    "liquidity": market.get("liquidity", 0),
                    "end_date": market.get("end_date", ""),
                }

                # 各評価窓
                for hours in [1, 4]:
                    exit_pnl = prices.get(f"exit_{hours}h_pnl")
                    exit_price = prices.get(f"exit_{hours}h_price")
                    if exit_pnl is not None:
                        # SELL の場合は PnL を反転
                        adj_pnl = -exit_pnl if side == "SELL" else exit_pnl
                        signal[f"pnl_{hours}h"] = round(adj_pnl * 100, 4)
                        signal[f"exit_{hours}h_price"] = exit_price
                        signal[f"win_{hours}h"] = 1 if adj_pnl > 0 else 0
                    else:
                        signal[f"pnl_{hours}h"] = None
                        signal[f"exit_{hours}h_price"] = None
                        signal[f"win_{hours}h"] = None

                all_signals.append(signal)

        time.sleep(0.5)  # API rate limit

    # 7. 結果をCSV出力
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(OUTPUT_DIR, f"backtest_{timestamp}.csv")

    if all_signals:
        keys = all_signals[0].keys()
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(all_signals)
        print(f"\n=== Results saved to {csv_path} ===")
    else:
        print("\nNo signals generated.")
        return

    # サマリー
    print(f"\nTotal signals: {len(all_signals)}")

    for hours in [1, 4]:
        valid = [s for s in all_signals if s.get(f"win_{hours}h") is not None]
        if valid:
            wins = sum(1 for s in valid if s[f"win_{hours}h"] == 1)
            avg_pnl = sum(s[f"pnl_{hours}h"] for s in valid) / len(valid)
            print(f"\n--- {hours}h window ---")
            print(f"  Signals: {len(valid)}")
            print(f"  Win rate: {wins}/{len(valid)} = {wins/len(valid)*100:.1f}%")
            print(f"  Avg PnL: {avg_pnl:+.3f}%")

            # テーマ別
            theme_stats = {}
            for s in valid:
                for t in s["themes"].split(","):
                    if t not in theme_stats:
                        theme_stats[t] = {"wins": 0, "total": 0, "pnl_sum": 0}
                    theme_stats[t]["total"] += 1
                    theme_stats[t]["wins"] += s[f"win_{hours}h"]
                    theme_stats[t]["pnl_sum"] += s[f"pnl_{hours}h"]
            print(f"\n  By theme:")
            for t, st in sorted(theme_stats.items(), key=lambda x: -x[1]["total"]):
                wr = st["wins"] / st["total"] * 100 if st["total"] > 0 else 0
                avg = st["pnl_sum"] / st["total"] if st["total"] > 0 else 0
                print(f"    {t:20s} {st['wins']}/{st['total']} ({wr:.0f}%) avg:{avg:+.3f}%")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Signal Bridge Backtest")
    parser.add_argument("--days", type=int, default=14, help="Days of history")
    parser.add_argument("--threshold", type=float, default=0.03, help="Move threshold (0.03 = 3%%)")
    parser.add_argument("--max-markets", type=int, default=50, help="Max markets to process")
    parser.add_argument("--fidelity", type=int, default=60, help="Price history fidelity in minutes")

    args = parser.parse_args()
    run_backtest(days=args.days, threshold=args.threshold, max_markets=args.max_markets)
