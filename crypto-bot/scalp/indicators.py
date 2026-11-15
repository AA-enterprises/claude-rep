"""Pure-python indicators (candle: ts, open, high, low, close, volume)."""
from __future__ import annotations


def ema(v: list[float], n: int) -> list[float]:
    k = 2 / (n + 1)
    out = [v[0]]
    for x in v[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def rsi(c: list[float], n: int = 14) -> float | None:
    if len(c) < n + 1:
        return None
    gains = [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    losses = [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def atr(h: list[float], l: list[float], c: list[float], n: int = 14) -> float | None:
    if len(c) < n + 1:
        return None
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    a = sum(tr[:n]) / n
    for x in tr[n:]:
        a = (a * (n - 1) + x) / n
    return a


def macd_hist(c: list[float]) -> tuple[float, float]:
    """(hist[-1], hist[-2])"""
    e12, e26 = ema(c, 12), ema(c, 26)
    m = [a - b for a, b in zip(e12, e26)]
    s = ema(m, 9)
    return m[-1] - s[-1], m[-2] - s[-2]
