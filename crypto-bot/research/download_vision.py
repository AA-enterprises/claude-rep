"""Binance public data archive (data.binance.vision) se futures 15m klines download -> numpy .npz (sirf research ke liye)."""
import io
import sys
import zipfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

BASE = "https://data.binance.vision/data/futures/um/monthly/klines/{s}/{tf}/{s}-{tf}-{y}-{m:02d}.zip"


def fetch(sym, tf, y, m):
    try:
        with urllib.request.urlopen(BASE.format(s=sym, tf=tf, y=y, m=m), timeout=40) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        rows = []
        for line in z.read(z.namelist()[0]).decode().splitlines():
            p = line.split(",")
            if not p or not p[0].isdigit():
                continue                                  # header
            rows.append((int(p[0]), float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[9])))
        return rows
    except Exception:
        return []


def download(sym, tf, y0, y1, out_dir, workers=12):
    months = [(y, m) for y in range(y0, y1 + 1) for m in range(1, 13)]
    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(lambda ym: fetch(sym, tf, *ym), months))
    rows = sorted({r[0]: r for p in parts for r in p}.values())
    if not rows:
        return 0
    a = np.array(rows, dtype=np.float64)
    np.savez_compressed(f"{out_dir}/{sym}_{tf}.npz", ts=a[:, 0].astype(np.int64), o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], v=a[:, 5], tb=a[:, 6])
    return len(rows)


if __name__ == "__main__":
    out = sys.argv[1]
    tf = sys.argv[3] if len(sys.argv) > 3 else "15m"
    for s in sys.argv[2].split(","):
        print(s, download(s, tf, 2020, 2026, out), flush=True)
