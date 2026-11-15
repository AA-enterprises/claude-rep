"""Har coin ke liye long/short score. 4 gates: trend, momentum, breakout, volume."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import indicators as ind
from .config import ScalpConfig

MIN_CANDLES = 210


@dataclass
class Signal:
    symbol: str
    side: str            # "LONG" | "SHORT"
    score: int           # kitne gates agree
    gates: list[str] = field(default_factory=list)
    vol_ratio: float = 0.0
    atr_pct: float = 0.0
    price: float = 0.0


def evaluate(symbol: str, candles: list[tuple], cfg: ScalpConfig) -> Signal | None:
    if len(candles) < MIN_CANDLES:
        return None
    w = candles[-250:]
    h = [x[2] for x in w]
    lo = [x[3] for x in w]
    c = [x[4] for x in w]
    v = [x[5] for x in w]
    price = c[-1]
    a = ind.atr(h, lo, c)
    if not a or price <= 0 or a / price < cfg.min_atr_pct:
        return None
    avg_v = sum(v[-21:-1]) / 20
    vol_ratio = v[-1] / avg_v if avg_v > 0 else 0.0
    e20, e50, e200 = ind.ema(c, 20)[-1], ind.ema(c, 50)[-1], ind.ema(c, 200)[-1]
    r = ind.rsi(c)
    hist, prev = ind.macd_hist(c)
    hh, ll = max(h[-21:-1]), min(lo[-21:-1])

    long_g = {
        "trend (EMA20>EMA50, price>EMA200)": e20 > e50 and price > e200,
        "momentum (RSI 50-75, MACD rising)": r is not None and 50 < r < 75 and hist > 0 and hist > prev,
        "breakout (20-bar high)": price > hh,
        "volume spike (>1.5x)": vol_ratio > 1.5,
    }
    short_g = {
        "trend (EMA20<EMA50, price<EMA200)": e20 < e50 and price < e200,
        "momentum (RSI 25-50, MACD falling)": r is not None and 25 < r < 50 and hist < 0 and hist < prev,
        "breakdown (20-bar low)": price < ll,
        "volume spike (>1.5x)": vol_ratio > 1.5,
    }
    ls, ss = sum(long_g.values()), sum(short_g.values())
    if max(ls, ss) < cfg.min_gates or ls == ss:
        return None
    side, gates, score = ("LONG", long_g, ls) if ls > ss else ("SHORT", short_g, ss)
    return Signal(symbol, side, score, [k for k, ok in gates.items() if ok], vol_ratio, a / price, price)
