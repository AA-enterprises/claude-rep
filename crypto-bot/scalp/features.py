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


def compute(h, l, c, v, min_score: int = FLOOR_SCORE, min_atr: float = FLOOR_ATR, allow_tie: bool = False) -> dict[int, Feat]:
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
        if a is None or price <= 0 or a / price < min_atr:
            continue
        avg_v = (pv[i] - pv[i - 20]) / 20
        vr = v[i] / avg_v if avg_v > 0 else 0.0
        vol = vr > 1.5
        lm = (e20[i] > e50[i] and price > e200[i], r is not None and 50 < r < 75 and hist[i] > 0 and hist[i] > hist[i - 1],
              price > h[dh[0]], vol)
        sm = (e20[i] < e50[i] and price < e200[i], r is not None and 25 < r < 50 and hist[i] < 0 and hist[i] < hist[i - 1],
              price < l[dl[0]], vol)
        ls, ss = sum(lm), sum(sm)
        if max(ls, ss) < min_score or (ls == ss and not allow_tie):
            continue
        out[i] = Feat(price, a / price, vr, ls, ss, lm, sm)
    return out


def rsi_states(c, n: int = 14):
    """Wilder avg gain/loss har bar ke baad (RSI ko incremental update karne ke liye)."""
    ag_l, al_l = [None] * len(c), [None] * len(c)
    if len(c) <= n:
        return ag_l, al_l
    ag = sum(max(c[i] - c[i - 1], 0) for i in range(1, n + 1)) / n
    al = sum(max(c[i - 1] - c[i], 0) for i in range(1, n + 1)) / n
    ag_l[n], al_l[n] = ag, al
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        ag, al = (ag * (n - 1) + max(d, 0)) / n, (al * (n - 1) + max(-d, 0)) / n
        ag_l[i], al_l[i] = ag, al
    return ag_l, al_l


def group_bars(s: Series, base_ms: int, new_ms: int):
    """15m -> 4h bars (sirf poore 16 sub-bars wale). Returns (bars Series, har bar ka pehla 15m index)."""
    ts, h, l, c, v = array("q"), array("d"), array("d"), array("d"), array("d")
    starts: list[int] = []
    k = new_ms // base_ms
    cur, cnt, start, H, L, C, V = None, 0, 0, 0.0, 0.0, 0.0, 0.0
    for i in range(len(s.ts)):
        b = s.ts[i] - s.ts[i] % new_ms
        if b != cur:
            if cur is not None and cnt == k:
                ts.append(cur); h.append(H); l.append(L); c.append(C); v.append(V); starts.append(start)
            cur, cnt, start, H, L, V = b, 0, i, s.h[i], s.l[i], 0.0
        H, L, C, V, cnt = max(H, s.h[i]), min(L, s.l[i]), s.c[i], V + s.v[i], cnt + 1
    if cur is not None and cnt == k:
        ts.append(cur); h.append(H); l.append(L); c.append(C); v.append(V); starts.append(start)
    return Series(ts, h, l, c, v), starts


def intrabar_events(s15: Series, base_ms: int, new_ms: int) -> dict[int, Feat]:
    """Har 15m sub-bar ke band hone par: poori band hui pichli bars + abhi tak ki ADHOORI badi candle se features.
    Key = us 15m candle ka open ts (backtest/live dono mein 'is candle ke close par decision')."""
    bars, starts = group_bars(s15, base_ms, new_ms)
    n, k = len(bars.ts), new_ms // base_ms
    if n < MIN_CANDLES + 1:
        return {}
    c, h, l, v = bars.c, bars.h, bars.l, bars.v
    e20, e50, e200 = ind.ema(c, 20), ind.ema(c, 50), ind.ema(c, 200)
    e12, e26 = ind.ema(c, 12), ind.ema(c, 26)
    m = [a - b for a, b in zip(e12, e26)]
    sg = ind.ema(m, 9)
    hist = [a - b for a, b in zip(m, sg)]
    ag_l, al_l = rsi_states(c)
    at = atr_series(h, l, c)
    pv = [0.0]
    for x in v:
        pv.append(pv[-1] + x)
    k20, k50, k200, k12, k26, k9 = (2 / (x + 1) for x in (20, 50, 200, 12, 26, 9))
    out: dict[int, Feat] = {}
    for i in range(MIN_CANDLES - 1, n):
        pc = c[i - 1]
        hh, ll = max(h[i - 20:i]), min(l[i - 20:i])
        avg_v = (pv[i] - pv[i - 20]) / 20
        ag0, al0, a0 = ag_l[i - 1], al_l[i - 1], at[i - 1]
        if ag0 is None or a0 is None:
            continue
        st = starts[i]
        H, L, V = -1e300, 1e300, 0.0
        for j in range(k):
            idx = st + j
            H, L, V, C = max(H, s15.h[idx]), min(L, s15.l[idx]), V + s15.v[idx], s15.c[idx]
            if C <= 0:
                continue
            a = (a0 * 13 + max(H - L, abs(H - pc), abs(L - pc))) / 14
            if a / C < FLOOR_ATR:
                continue
            d = C - pc
            ag, al = (ag0 * 13 + max(d, 0)) / 14, (al0 * 13 + max(-d, 0)) / 14
            r = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
            ep20, ep50, ep200 = C * k20 + e20[i - 1] * (1 - k20), C * k50 + e50[i - 1] * (1 - k50), C * k200 + e200[i - 1] * (1 - k200)
            mp = (C * k12 + e12[i - 1] * (1 - k12)) - (C * k26 + e26[i - 1] * (1 - k26))
            hp = mp - (mp * k9 + sg[i - 1] * (1 - k9))
            vr = V / avg_v if avg_v > 0 else 0.0
            vol = vr > 1.5
            lm = (ep20 > ep50 and C > ep200, 50 < r < 75 and hp > 0 and hp > hist[i - 1], C > hh, vol)
            sm = (ep20 < ep50 and C < ep200, 25 < r < 50 and hp < 0 and hp < hist[i - 1], C < ll, vol)
            ls, ss = sum(lm), sum(sm)
            if max(ls, ss) < FLOOR_SCORE or ls == ss:
                continue
            out[s15.ts[idx]] = Feat(C, a / C, vr, ls, ss, lm, sm)
    return out
