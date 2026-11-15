"""Ek hi pass mein saare candles ke signal features (backtest ke liye tez, live ke liye wahi logic)."""
from __future__ import annotations

from array import array
from collections import deque, namedtuple

from . import indicators as ind

MIN_CANDLES = 210
FLOOR_SCORE = 2        # isse kam score wale candles store hi nahi hote (memory)
FLOOR_ATR = 0.002
Feat = namedtuple("Feat", "price atr_pct vol_ratio ls ss lmask smask")


class Series:
    """Compact candle storage: ts, high, low, close, volume."""
    __slots__ = ("ts", "h", "l", "c", "v")

    def __init__(self, ts, h, l, c, v):
        self.ts, self.h, self.l, self.c, self.v = ts, h, l, c, v

    @classmethod
    def from_candles(cls, candles: list[tuple]) -> "Series":
        return cls(array("q", [x[0] for x in candles]), array("d", [x[2] for x in candles]),
                   array("d", [x[3] for x in candles]), array("d", [x[4] for x in candles]),
                   array("d", [x[5] for x in candles]))


def rsi_series(c, n: int = 14) -> list:
    out = [None] * len(c)
    if len(c) <= n:
        return out
    ag = sum(max(c[i] - c[i - 1], 0) for i in range(1, n + 1)) / n
    al = sum(max(c[i - 1] - c[i], 0) for i in range(1, n + 1)) / n
    for i in range(n, len(c)):
        if i > n:
            d = c[i] - c[i - 1]
            ag, al = (ag * (n - 1) + max(d, 0)) / n, (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr_series(h, l, c, n: int = 14) -> list:
    out = [None] * len(c)
    if len(c) <= n:
        return out
    tr = [0.0] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    a = sum(tr[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(c)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def regime_series(c) -> list:
    """BTC trend: +1 up (EMA50>EMA200), -1 down, 0 abhi data kam."""
    if len(c) < 200:
        return [0] * len(c)
    e50, e200 = ind.ema(c, 50), ind.ema(c, 200)
    return [0] * 199 + [1 if e50[i] > e200[i] else -1 for i in range(199, len(c))]


def compute(h, l, c, v) -> dict[int, Feat]:
    n = len(c)
    if n < MIN_CANDLES:
        return {}
    e20, e50, e200 = ind.ema(c, 20), ind.ema(c, 50), ind.ema(c, 200)
    e12, e26 = ind.ema(c, 12), ind.ema(c, 26)
    m = [a - b for a, b in zip(e12, e26)]
    sg = ind.ema(m, 9)
    hist = [a - b for a, b in zip(m, sg)]
    rs, at = rsi_series(c), atr_series(h, l, c)
    pv = [0.0]
    for x in v:
        pv.append(pv[-1] + x)
    dh: deque = deque()
    dl: deque = deque()
    out: dict[int, Feat] = {}
    for i in range(n):
        if i > 0:                        # window = pichli 20 candles (current nahi)
            while dh and h[dh[-1]] <= h[i - 1]:
                dh.pop()
            dh.append(i - 1)
            while dl and l[dl[-1]] >= l[i - 1]:
                dl.pop()
            dl.append(i - 1)
            while dh[0] < i - 20:
                dh.popleft()
            while dl[0] < i - 20:
                dl.popleft()
        if i < MIN_CANDLES - 1:
            continue
        price, a, r = c[i], at[i], rs[i]
        if a is None or price <= 0 or a / price < FLOOR_ATR:
            continue
        avg_v = (pv[i] - pv[i - 20]) / 20
        vr = v[i] / avg_v if avg_v > 0 else 0.0
        vol = vr > 1.5
        lm = (e20[i] > e50[i] and price > e200[i], r is not None and 50 < r < 75 and hist[i] > 0 and hist[i] > hist[i - 1],
              price > h[dh[0]], vol)
        sm = (e20[i] < e50[i] and price < e200[i], r is not None and 25 < r < 50 and hist[i] < 0 and hist[i] < hist[i - 1],
              price < l[dl[0]], vol)
        ls, ss = sum(lm), sum(sm)
        if max(ls, ss) < FLOOR_SCORE or ls == ss:
            continue
        out[i] = Feat(price, a / price, vr, ls, ss, lm, sm)
    return out
