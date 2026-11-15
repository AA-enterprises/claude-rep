"""Synthetic multi-coin candles (testing/demo). Trending regimes + volume spikes."""
from __future__ import annotations

import random

from .config import ScalpConfig


def coin(n: int, start: float, seed: int, tf_ms: int, t0: int = 1_700_000_000_000) -> list[tuple]:
    rng = random.Random(seed)
    price, drift, out = start, 0.0, []
    for i in range(n):
        if i % 40 == 0:
            drift = rng.choice([-0.0025, -0.001, 0.0, 0.001, 0.0025])
        o = price
        c = o * (1 + drift + rng.gauss(0, 0.006))
        hi = max(o, c) * (1 + abs(rng.gauss(0, 0.002)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, 0.002)))
        vol = 1000 * (1 + abs(c / o - 1) * 80) * rng.uniform(0.6, 1.4)
        out.append((t0 + i * tf_ms, o, hi, lo, c, vol))
        price = c
    return out


def market(cfg: ScalpConfig, coins: int = 12, n: int = 700, seed: int = 1) -> dict[str, list[tuple]]:
    return {f"COIN{i}/USDT:USDT": coin(n, 10 * (i + 1), seed * 100 + i, cfg.tf_ms) for i in range(coins)}
