"""Binance history download (pagination) + local CSV cache. Dobara chalane par sirf naya data aata hai."""
from __future__ import annotations

import csv
import glob
import os
import time
from array import array

from .features import Series

CHUNK = 1000   # Binance weight 5 per call


def cache_path(cache_dir: str, sym: str, tf: str) -> str:
    return os.path.join(cache_dir, sym.replace("/", "_").replace(":", "_") + f"_{tf}.csv")


def _last_ts(path: str) -> int | None:
    if not os.path.exists(path) or os.path.getsize(path) < 20:
        return None
    with open(path, "rb") as f:
        f.seek(-min(4096, os.path.getsize(path)), os.SEEK_END)
        lines = f.read().decode().strip().splitlines()
    try:
        return int(float(lines[-1].split(",")[0]))
    except ValueError:
        return None


def _fetch(ex, sym, tf, since, retries: int = 6):
    for k in range(retries):
        try:
            return ex.fetch_ohlcv(sym, tf, since=since, limit=CHUNK)
        except Exception as e:  # noqa: BLE001 rate limit / network
            time.sleep(min(60, 2 ** k))
            err = e
    raise err


def download(ex, sym: str, tf: str, tf_ms: int, years: float, cache_dir: str, log=print) -> int:
    os.makedirs(cache_dir, exist_ok=True)
    path = cache_path(cache_dir, sym, tf)
    last = _last_ts(path)
    now = ex.milliseconds()
    since = last + tf_ms if last else int(now - years * 365.25 * 86_400_000)
    new = 0
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        while since < now:
            rows = _fetch(ex, sym, tf, since)
            if not rows:
                break
            rows = [r for r in rows if r[0] + tf_ms <= now]      # adhoori candle nahi
            for r in rows:
                w.writerow(r[:6])
            new += len(rows)
            if len(rows) < 2:
                break
            since = rows[-1][0] + tf_ms
        f.flush()
    log(f"  {sym}: +{new} candles")
    return new


def load_series(path: str) -> Series:
    ts, h, l, c, v = array("q"), array("d"), array("d"), array("d"), array("d")
    last = -1
    with open(path, newline="") as f:
        for r in csv.reader(f):
            try:
                t = int(float(r[0]))
            except (ValueError, IndexError):
                continue                                          # header ya kharab line
            if t <= last:
                continue                                          # duplicate
            last = t
            ts.append(t); h.append(float(r[2])); l.append(float(r[3])); c.append(float(r[4])); v.append(float(r[5]))
    return Series(ts, h, l, c, v)


def load_cache(cache_dir: str, tf: str, max_coins: int | None = None) -> dict[str, Series]:
    out = {}
    for p in sorted(glob.glob(os.path.join(cache_dir, f"*_{tf}.csv"))):
        sym = os.path.basename(p)[: -len(f"_{tf}.csv")]
        base, _, rest = sym.partition("_USDT_")
        sym = f"{base}/USDT:USDT" if rest else sym
        s = load_series(p)
        if len(s.ts) >= 300:
            out[sym] = s
    if max_coins and len(out) > max_coins:
        btc = [k for k in out if k.startswith("BTC/")]
        rest = sorted((k for k in out if k not in btc), key=lambda k: -len(out[k].ts))[: max_coins - len(btc)]
        out = {k: out[k] for k in btc + rest}
    return out
