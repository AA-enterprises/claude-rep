"""Settings sweep with walk-forward: pehle ~70% data par tune, baaki ~30% (nayi, ankhi hui) par check."""
from __future__ import annotations

import csv
import itertools
from dataclasses import replace

from .backtest import Dataset, Result, run
from .config import ScalpConfig

FULL = dict(leverage=[5, 10, 20], tp_roi=[0.35, 0.70], sl_roi=[0.10, 0.20], min_gates=[3, 4],
            max_hold_hours=[2, 6, 24], sides=["both", "long", "short"], btc_filter=[False, True])
QUICK = dict(leverage=[10, 20], tp_roi=[0.70], sl_roi=[0.20], min_gates=[3, 4],
             max_hold_hours=[6], sides=["both"], btc_filter=[False, True])


def passes(train: Result, test: Result) -> bool:
    return (len(train.records) >= 100 and len(test.records) >= 50 and train.ret > 0 and test.ret > 0
            and test.profit_factor > 1.1 and test.max_dd < 0.35 and train.max_dd < 0.35)


def sweep(ds: Dataset, base: ScalpConfig, grid: dict, split: float = 0.7, out_csv: str | None = None, log=print):
    t_split = ds.tmin + int((ds.tmax - ds.tmin) * split)
    keys = list(grid)
    combos = [dict(zip(keys, v)) for v in itertools.product(*grid.values())]
    log(f"{len(combos)} combos | train {ds.tmin}..{t_split} | test {t_split}..{ds.tmax}")
    rows = []
    for k, c in enumerate(combos, 1):
        cfg = replace(base, **c)
        cfg.validate()
        tr, te = run(ds, cfg, ds.tmin, t_split), run(ds, cfg, t_split, ds.tmax + 1)
        rows.append((c, tr, te, passes(tr, te)))
        if k % 10 == 0:
            log(f"  {k}/{len(combos)}")
    if out_csv:
        with open(out_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(keys + ["train_ret", "train_dd", "train_trades", "test_ret", "test_dd", "test_trades", "test_pf", "PASS"])
            for c, tr, te, ok in rows:
                w.writerow([c[x] for x in keys] + [f"{tr.ret:.4f}", f"{tr.max_dd:.4f}", len(tr.records),
                                                   f"{te.ret:.4f}", f"{te.max_dd:.4f}", len(te.records), f"{te.profit_factor:.2f}", ok])
    return rows


def report(rows, top: int = 8) -> str:
    ranked = sorted(rows, key=lambda r: r[1].ret / max(r[1].max_dd, 0.05), reverse=True)[:top]
    out = ["TOP (train score ke hisaab se) -> TEST (unseen data) result:"]
    for c, tr, te, ok in ranked:
        out.append(f"{'PASS' if ok else 'fail'} | {c}\n       train {tr.ret:+.1%} (dd {tr.max_dd:.0%}, {len(tr.records)} trades)"
                   f" -> test {te.ret:+.1%} (dd {te.max_dd:.0%}, {len(te.records)} trades, pf {te.profit_factor:.2f})")
    n_ok = sum(1 for r in rows if r[3])
    out.append("")
    out.append(f"PASS hue: {n_ok} / {len(rows)}")
    out.append("VERDICT: " + ("kuch settings dono hisson mein profitable rahin. Inhe paper mein alag se confirm karo (yeh guarantee nahi)."
                              if n_ok else "Koi bhi settings unseen data par profitable nahi nikli. Is strategy ko in rules par live mat karo."))
    return "\n".join(out)
