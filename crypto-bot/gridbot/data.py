"""Candle data sources: Binance (ccxt), CSV, ya synthetic (testing)."""
from __future__ import annotations

import csv
import math
import random

Candle = tuple[int, float, float, float, float]  # ts_ms, open, high, low, close


def from_binance(symbol: str, timeframe: str = "1h", limit: int = 1000) -> list[Candle]:
    import ccxt

    ex = ccxt.binance({"enableRateLimit": True})
    rows = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
    return [(int(r[0]), r[1], r[2], r[3], r[4]) for r in rows]


def from_csv(path: str) -> list[Candle]:
    """CSV columns: timestamp,open,high,low,close (header row ke saath)."""
    out: list[Candle] = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            out.append((int(float(r["timestamp"])), float(r["open"]), float(r["high"]),
                        float(r["low"]), float(r["close"])))
    return out


def synthetic(n: int = 2000, start: float = 60000.0, vol: float = 0.006, seed: int = 42) -> list[Candle]:
    """Sideways-ish random walk + halka wave: grid strategy ka demo/test data."""
    rng = random.Random(seed)
    price, out = start, []
    for i in range(n):
        o = price
        drift = 0.0008 * math.sin(i / 60) - 0.02 * (price - start) / start * 0.05
        c = o * (1 + drift + rng.gauss(0, vol))
        hi = max(o, c) * (1 + abs(rng.gauss(0, vol / 2)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
        out.append((i * 3_600_000, o, hi, lo, c))
        price = c
    return out
