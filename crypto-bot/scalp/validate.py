"""Ek chune hue config ki sakht jaanch: kya edge asli lagta hai ya sirf 'lucky' / bias?"""
from __future__ import annotations

import random
from dataclasses import fields, replace

from .backtest import Dataset, Result, run
from .config import ScalpConfig


def parse_overrides(pairs: list[str]) -> dict:
    types = {f.name: f.type for f in fields(ScalpConfig)}
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        if k not in types:
            raise ValueError(f"Unknown setting: {k}")
        t = str(types[k])
        out[k] = (v.lower() in ("1", "true", "yes")) if "bool" in t else float(v) if "float" in t else int(v) if "int" in t else v
    return out


def bootstrap(rs: list[float], risk: float, sims: int = 2000, seed: int = 1) -> dict:
    """Trades ke R ko random order mein baar baar chala ke: kitna kamaya, worst drawdown kya ho sakta hai."""
    rng = random.Random(seed)
    n = len(rs)
    finals, dds = [], []
    for _ in range(sims):
        eq = peak = dd = 0.0
        for _ in range(n):
            eq += rng.choice(rs) * risk
            peak = max(peak, eq)
            dd = max(dd, peak - eq)
        finals.append(eq)
        dds.append(dd)
    finals.sort(); dds.sort()
    q = lambda a, p: a[min(len(a) - 1, int(p * len(a)))]
    return {"p_profit": sum(f > 0 for f in finals) / sims, "median": q(finals, 0.5), "p5": q(finals, 0.05),
            "dd50": q(dds, 0.5), "dd95": q(dds, 0.95)}


def neighbors(cfg: ScalpConfig) -> list[tuple[str, ScalpConfig]]:
    out = []
    for name, vals in (("sl_atr", [cfg.sl_atr - 0.5, cfg.sl_atr + 0.5]), ("min_gates", [cfg.min_gates - 1, cfg.min_gates + 1]),
                       ("max_hold_hours", [cfg.max_hold_hours / 2, cfg.max_hold_hours * 2])):
        for v in vals:
            if (name == "sl_atr" and v < 0.5) or (name == "min_gates" and not 2 <= v <= 4):
                continue
            out.append((f"{name}={v:g}", replace(cfg, **{name: v})))
    if cfg.trail_atr > 0:
        out += [(f"trail_atr={v:g}", replace(cfg, trail_atr=v)) for v in (cfg.trail_atr - 0.5, cfg.trail_atr + 0.5) if v > 0]
    if cfg.tp_atr > 0:
        out += [(f"tp_atr={v:g}", replace(cfg, tp_atr=v)) for v in (cfg.tp_atr - 1, cfg.tp_atr + 1) if v > 0]
    return out


def validate(ds: Dataset, cfg: ScalpConfig, log=print) -> bool:
    checks: list[tuple[bool, str]] = []
    full = run(ds, cfg)
    log("=== 1) Poori history (fixed-size) ===")
    log(full.summary())
    checks.append((full.avg_r > 0.05 and full.profit_factor > 1.1, f"poori history: {full.avg_r:+.3f} R/trade, pf {full.profit_factor:.2f} ({len(full.records)} trades)"))

    yrs = full.yearly()
    pos = sum(1 for _, (_, _, p) in yrs.items() if p > 0)
    checks.append((len(yrs) >= 3 and pos / len(yrs) >= 0.6, f"{pos}/{len(yrs)} saal profitable"))

    log("\n=== 2) Coin concentration (kya sirf kuch coins ne kamaya?) ===")
    by: dict[str, float] = {}
    for x in full.records:
        by[x["symbol"]] = by.get(x["symbol"], 0.0) + x["pnl"]
    ranked = sorted(by.items(), key=lambda kv: -kv[1])
    gross = sum(v for v in by.values() if v > 0) or 1.0
    top3 = [k for k, _ in ranked[:3]]
    share = sum(v for k, v in ranked[:3] if v > 0) / gross
    for k, v in ranked[:5]:
        log(f"  {k:22} {v:+10,.0f}")
    rest = [k for k in ds.s if k not in top3]
    ex = run(ds.subset(rest), cfg) if rest else None
    log(f"  Top-3 coins = {share:.0%} of gross profit | top-3 hata ke: {ex.ret:+.1%}, {ex.avg_r:+.3f} R/trade" if ex else "")
    checks.append((share < 0.5 and ex is not None and ex.avg_r > 0, f"top-3 coins ka share {share:.0%}, unke bina {ex.avg_r:+.3f} R/trade" if ex else "n/a"))

    log("\n=== 3) Sirf BTC + ETH (hamesha se maujood, survivorship bias kam) ===")
    majors = [k for k in ds.s if k.startswith(("BTC/", "ETH/"))]
    if majors:
        m = run(ds.subset(majors), cfg)
        log(m.summary())
        checks.append((m.avg_r > 0 and len(m.records) >= 30, f"BTC+ETH only: {m.avg_r:+.3f} R/trade ({len(m.records)} trades)"))
    else:
        checks.append((False, "BTC/ETH data cache mein nahi"))

    log("\n=== 4) Parameters ki stability (thoda hila ke dekho) ===")
    nb = neighbors(cfg)
    good = 0
    for name, c in nb:
        r = run(ds, c)
        good += r.avg_r > 0.02
        log(f"  {name:18} {r.avg_r:+.3f} R/trade | pf {r.profit_factor:.2f} | {r.ret:+.0%}")
    checks.append((bool(nb) and good / len(nb) >= 0.7, f"{good}/{len(nb)} nearby settings bhi profitable"))

    log("\n=== 5) Monte Carlo (trades ko random order mein 2000 baar) ===")
    rs = [x["r"] for x in full.records if "r" in x]
    bs = bootstrap(rs, cfg.risk_pct)
    log(f"  risk_pct {cfg.risk_pct:.2%}: profit ki probability {bs['p_profit']:.0%} | median {bs['median']:+.0%} | "
        f"worst-5% {bs['p5']:+.0%} | drawdown median {bs['dd50']:.0%}, 95% case mein {bs['dd95']:.0%}")
    target = round(cfg.risk_pct * 0.20 / max(bs["dd95"], 1e-9), 4)
    log(f"  95% worst drawdown ko ~20% rakhne ke liye risk_pct ~ {min(target, cfg.risk_pct)}")
    checks.append((bs["p_profit"] >= 0.9, f"Monte Carlo profit probability {bs['p_profit']:.0%}"))

    log("\n=== VERDICT ===")
    for ok, text in checks:
        log(f"  [{'OK' if ok else 'FAIL'}] {text}")
    all_ok = all(ok for ok, _ in checks)
    log("\n" + ("Sab checks pass. Phir bhi: paper trading mein confirm karo, aur survivorship bias (sirf aaj ke top coins) abhi baaki hai."
                if all_ok else "Kuch checks fail: is config par bharosa mat karo. Upar dekho kaunsa fail hua."))
    return all_ok
