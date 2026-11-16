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


ATR_FULL = dict(sl_atr=[1.0, 1.5, 2.5], tp_atr=[0.0, 2.0, 3.0, 5.0], trail_atr=[0.0, 1.5, 2.5],
                min_gates=[3, 4], max_hold_hours=[6, 24], btc_filter=[False, True])
ATR_QUICK = dict(sl_atr=[1.5], tp_atr=[0.0, 3.0], trail_atr=[0.0, 1.5], min_gates=[3, 4], btc_filter=[False, True])


ATR_SLOW = dict(sl_atr=[1.5, 2.5], tp_atr=[0.0, 3.0, 5.0], trail_atr=[0.0, 2.5], min_gates=[3, 4],
                max_hold_hours=[24, 96], btc_filter=[False, True])
ATR_SLOW_QUICK = dict(sl_atr=[2.0], tp_atr=[0.0, 4.0], trail_atr=[0.0, 2.5], min_gates=[3, 4],
                      max_hold_hours=[48], btc_filter=[False, True])


ROI30 = dict(leverage=[2, 3, 5], tp_roi=[0.30], sl_roi=[0.10, 0.15, 0.30], min_gates=[3, 4], max_hold_hours=[6, 24])


def grid_for(mode: str, quick: bool, slow: bool = False):
    """-> (grid, base overrides)"""
    if mode == "roi30":                                  # 'har trade pe 30% ROI profit book': door liquidation (kam leverage) ke saath
        return ROI30, {"exit_mode": "roi"}
    if slow and mode == "atr":
        return (ATR_SLOW_QUICK if quick else ATR_SLOW), {"exit_mode": "atr"}
    if mode == "roi":
        return (QUICK if quick else FULL), {"exit_mode": "roi"}
    return (ATR_QUICK if quick else ATR_FULL), {"exit_mode": "atr"}


def calmar(r: Result) -> float:
    return r.ret / max(r.max_dd, 0.01)


def passes(train: Result, test: Result) -> bool:
    """Risk-normalized: drawdown position size (risk_pct) se seedha scale hota hai, isliye absolute dd par fail nahi karte.
    Dono hisson mein: profit, R-expectancy > 0, profit factor > 1.1, return/drawdown >= 1."""
    return (len(train.records) >= 100 and len(test.records) >= 50 and train.ret > 0 and test.ret > 0
            and train.avg_r > 0.02 and test.avg_r > 0.03 and test.profit_factor > 1.1
            and calmar(train) >= 1 and calmar(test) >= 1)


def suggested_risk(base_risk: float, *results: Result, target_dd: float = 0.20) -> float:
    """Drawdown ~ risk_pct ke barabar scale hota hai: itna risk jisse worst dd ~20% rahe."""
    worst = max(r.max_dd for r in results)
    return round(min(base_risk, base_risk * target_dd / max(worst, 1e-9)), 4)


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
        out.append(f"{'PASS' if ok else 'fail'} | {c} | risk_pct ~{suggested_risk(0.01, tr, te)} se dd ~20%\n       train {tr.ret:+.1%} (dd {tr.max_dd:.0%}, {len(tr.records)} trades)"
                   f" -> test {te.ret:+.1%} (dd {te.max_dd:.0%}, {len(te.records)} trades, pf {te.profit_factor:.2f})")
    n_ok = sum(1 for r in rows if r[3])
    out.append("")
    out.append(f"PASS hue: {n_ok} / {len(rows)}")
    out.append("VERDICT: " + ("kuch settings dono hisson mein profitable rahin. Ab zaroori hai: python main.py scalp-validate (survivorship, coin concentration, har saal, stability check). Yeh guarantee nahi."
                              if n_ok else "Koi bhi settings unseen data par profitable nahi nikli. Is strategy ko in rules par live mat karo."))
    return "\n".join(out)
