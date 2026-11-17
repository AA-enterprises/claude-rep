"""Binance funding-rate history (data.binance.vision) download, research ke liye."""
import io
import sys
import zipfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

URL = "https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{y}-{m:02d}.zip"


def one(sym, y, m):
    try:
        with urllib.request.urlopen(URL.format(s=sym, y=y, m=m), timeout=40) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        out = []
        for line in z.read(z.namelist()[0]).decode().splitlines():
            p = line.split(",")
            if p and p[0].isdigit():
                out.append((int(p[0]), float(p[2])))
        return out
    except Exception:
        return []


def download(sym, out_dir, y0=2019, y1=2026):
    with ThreadPoolExecutor(12) as ex:
        parts = list(ex.map(lambda ym: one(sym, *ym), [(y, m) for y in range(y0, y1 + 1) for m in range(1, 13)]))
    rows = sorted({r[0]: r for p in parts for r in p}.values())
    if rows:
        a = np.array(rows)
        np.savez_compressed(f"{out_dir}/{sym}_funding.npz", ts=a[:, 0].astype(np.int64), rate=a[:, 1])
    return len(rows)


if __name__ == "__main__":
    for s in sys.argv[2].split(","):
        print(s, download(s, sys.argv[1]), flush=True)
