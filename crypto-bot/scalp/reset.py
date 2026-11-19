"""Naye test ke liye paper bot ko saaf shuru karna: purani state/trades/equity files archive folder mein jati hain (delete nahi hoti)."""
from __future__ import annotations

import json
import os
import shutil
import time


def archive(state_path: str, trades_path: str, now: float | None = None) -> tuple[str | None, list[str]]:
    """Files ko `archive/<stamp>_<bot>/` mein move karta hai. Return (folder, moved_files). Kuch na ho to (None, [])."""
    now = time.time() if now is None else now
    base = state_path[:-len(".json")] if state_path.endswith(".json") else state_path
    files = [state_path, trades_path, base + "_equity.csv", base + "_commands.jsonl"]
    existing = [f for f in files if os.path.exists(f)]
    if not existing:
        return None, []
    folder = os.path.join(os.path.dirname(os.path.abspath(state_path)), "archive",
                          f"{time.strftime('%Y%m%d_%H%M%S', time.localtime(now))}_{os.path.basename(base)}")
    os.makedirs(folder, exist_ok=True)
    for f in existing:
        shutil.move(f, os.path.join(folder, os.path.basename(f)))
    return folder, [os.path.basename(f) for f in existing]


def open_positions(state_path: str) -> int:
    try:
        with open(state_path) as f:
            return len(json.load(f)["account"]["positions"])
    except (OSError, ValueError, KeyError):
        return 0
