"""
Signal Store
シグナルと実行結果をJSONファイルに記録する
"""

import json
import os
from datetime import datetime, timezone

SIGNALS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "signals")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "results")


def _ensure_dirs():
    os.makedirs(SIGNALS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)


def save_event(event: dict):
    """正規化されたイベントを保存"""
    _ensure_dirs()
    filename = f"{event['detected_at'][:10]}_{event['event_id']}.json"
    filepath = os.path.join(SIGNALS_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(event, f, indent=2, default=str)
    return filepath


def save_result(result: dict):
    """実行結果を保存"""
    _ensure_dirs()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    filename = f"{timestamp}_{result['event_id']}_{result['ticker'].replace('.', '_')}.json"
    filepath = os.path.join(RESULTS_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(result, f, indent=2, default=str)
    return filepath


def load_all_signals() -> list:
    """全シグナルを読み込む"""
    _ensure_dirs()
    signals = []
    for filename in sorted(os.listdir(SIGNALS_DIR)):
        if filename.endswith(".json"):
            with open(os.path.join(SIGNALS_DIR, filename)) as f:
                signals.append(json.load(f))
    return signals


def load_all_results() -> list:
    """全実行結果を読み込む"""
    _ensure_dirs()
    results = []
    for filename in sorted(os.listdir(RESULTS_DIR)):
        if filename.endswith(".json"):
            with open(os.path.join(RESULTS_DIR, filename)) as f:
                results.append(json.load(f))
    return results
