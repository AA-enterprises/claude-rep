"""Tez multi-coin backtest. Live bot jaisa hi account + decide() logic."""
from __future__ import annotations

import time
from bisect import bisect_left
from dataclasses import dataclass, field

from .account import PaperAccount
from .config import ScalpConfig
from .features import Series, compute, group_bars, intrabar_events, regime_series
from .signals import decide

DAY = 86_400_000


class Dataset:
    def __init__(self, series: dict[str, Series], tf_ms: int):
        self.s, self.tf = series, tf_ms
        self.events: dict[int, list] = {}
        for sym, s in series.items():
            for i, f in compute(s.h, s.l, s.c, s.v).items():
                self.events.setdefault(s.ts[i], []).append((sym, f))
        self.tmin = min(s.ts[0] for s in series.values())
        self.tmax = max(s.ts[-1] for s in series.values())
        btc = next((k for k in series if k.startswith("BTC/")), None)
        self.btc_ts = series[btc].ts if btc else None
        self.btc_reg = regime_series(series[btc].c) if btc else None

    @classmethod
    def from_candles(cls, data: dict[str, list[tuple]], tf_ms: int) -> "Dataset":
        return cls({k: Series.from_candles(v) for k, v in data.items()}, tf_ms)

    def subset(self, syms) -> "Dataset":
        """Kuch coins hata ke/chun ke naya dataset (features dobara nahi nikalte). BTC regime original rehta hai."""
        keep = set(syms)
        new = object.__new__(type(self))
        new.__dict__.update(self.__dict__)
        new.s = {k: v for k, v in self.s.items() if k in keep}
        new.events = {}
        for t, ev in self.events.items():
            e = [x for x in ev if x[0] in keep]
            if e:
                new.events[t] = e
        new.tmin = min(s.ts[0] for s in new.s.values())
        new.tmax = max(s.ts[-1] for s in new.s.values())
        return new

    def at(self, sym: str, t: int) -> int | None:
        ts = self.s[sym].ts
        i = bisect_left(ts, t)
        return i if i < len(ts) and ts[i] == t else None

    def regime(self, t: int) -> int | None:
        if self.btc_ts is None:
            return None
        i = bisect_left(self.btc_ts, t)
        return self.btc_reg[i] if i < len(self.btc_ts) and self.btc_ts[i] == t else None


class IntrabarDataset(Dataset):
    """Entry har 15m candle ke close par adhoori badi (4h) candle dekh kar. Exit/trailing bhi 15m candles par."""

    def __init__(self, series15: dict[str, Series], tf_ms: int, base_ms: int = 900_000, only_close: bool = False):
        """only_close=True: entry sirf band hui badi candle par (aakhri 15m sub-bar), par exit/trailing 15m par (fair compare)."""
        self.s, self.tf, self.grid, self.base = series15, tf_ms, base_ms, base_ms
        self.events = {}
        for sym, s in series15.items():
            for ts, f in intrabar_events(s, base_ms, tf_ms).items():
                if only_close and ts % tf_ms != tf_ms - base_ms:
                    continue
                self.events.setdefault(ts, []).append((sym, f))
        self.tmin = min(s.ts[0] for s in series15.values())
        self.tmax = max(s.ts[-1] for s in series15.values())
        btc = next((k for k in series15 if k.startswith("BTC/")), None)
        self.btc_ts = self.btc_reg = None
        if btc:
            bars, _ = group_bars(series15[btc], base_ms, tf_ms)
            self.btc_ts, self.btc_reg = bars.ts, regime_series(bars.c)

    def regime(self, t: int) -> int | None:
        if self.btc_ts is None:
            return None
        i = bisect_left(self.btc_ts, t + self.base - self.tf + 1) - 1      # aakhri poori band hui 4h bar
        return self.btc_reg[i] if i >= 0 else None


@dataclass
class Result:
    start: float
    end: float
    records: list[dict] = field(default_factory=list)
    max_dd: float = 0.0

    @property
    def ret(self) -> float:
        return self.end / self.start - 1

    @property
    def win_rate(self) -> float:
        return sum(1 for x in self.records if x["pnl"] > 0) / len(self.records) if self.records else 0.0

    @property
    def profit_factor(self) -> float:
        g = sum(x["pnl"] for x in self.records if x["pnl"] > 0)
        l = -sum(x["pnl"] for x in self.records if x["pnl"] < 0)
        return g / l if l > 0 else (float("inf") if g > 0 else 0.0)

    @property
    def avg_r(self) -> float:
        return sum(x.get("r", 0.0) for x in self.records) / len(self.records) if self.records else 0.0

    def yearly(self) -> dict[int, tuple[int, float, float]]:
        out: dict[int, list] = {}
        for x in self.records:
            y = time.gmtime(x["closed_ts"] / 1000).tm_year
            o = out.setdefault(y, [0, 0, 0.0])
            o[0] += 1
            o[1] += x["pnl"] > 0
            o[2] += x["pnl"]
        return {y: (n, w / n, p) for y, (n, w, p) in sorted(out.items())}

    def summary(self) -> str:
        r = self.records
        n = len(r)
        by = {k: sum(1 for x in r if x["reason"] == k) for k in ("TP", "TRAIL", "SL", "TIMEOUT", "END")}
        longs = [x for x in r if x["side"] == "LONG"]
        shorts = [x for x in r if x["side"] == "SHORT"]

        def wr(a):
            return f"{sum(1 for x in a if x['pnl'] > 0) / len(a):.0%}" if a else "-"
        lines = [
            f"Start / End balance : {self.start:,.2f} -> {self.end:,.2f} USDT ({self.ret:+.2%})  [fixed-size: -100% se zyada loss = poori history mein yeh size chalta to]",
            f"Max drawdown        : {self.max_dd:.2%}",
            f"Trades              : {n} | win rate {self.win_rate:.0%} | profit factor {self.profit_factor:.2f}" if n else "Trades              : 0",
            f"Exits               : TP {by['TP']} | TRAIL {by['TRAIL']} | SL {by['SL']} | TIMEOUT {by['TIMEOUT']} | END {by['END']}",
            f"Avg per trade      : {self.avg_r:+.3f} R (1R = stop lagne par loss; positive = edge)" if n else "",
            f"Long / Short        : {len(longs)} (win {wr(longs)}) / {len(shorts)} (win {wr(shorts)})",
        ]
        if n:
            lines.append("Saal-ba-saal PnL    : " + " | ".join(f"{y}: {p:+,.0f} ({k} trades)" for y, (k, _, p) in self.yearly().items()))
        return "\n".join(lines)


def run(data, cfg: ScalpConfig, t0: int | None = None, t1: int | None = None) -> Result:
    ds = data if isinstance(data, Dataset) else Dataset.from_candles(data, cfg.tf_ms)
    t0 = ds.tmin if t0 is None else t0
    t1 = ds.tmax + 1 if t1 is None else t1
    step = getattr(ds, "grid", None) or cfg.tf_ms                  # intrabar mein 15m, warna candle timeframe
    t0 = ds.tmin + -(-(t0 - ds.tmin) // step) * step                # dataset ki apni grid par align (ceil)
    acct = PaperAccount(cfg, unlimited=not cfg.compound)
    res = Result(cfg.start_balance, cfg.start_balance)
    peak = cfg.start_balance
    day, day_start, last_t = None, cfg.start_balance, t0
    for t in range(t0, t1, step):
        last_t = t
        for sym, pos in list(acct.positions.items()):
            i = ds.at(sym, t)
            if i is None or t <= pos.opened_ts:
                continue
            s = ds.s[sym]
            ex = acct.check_exit(pos, s.h[i], s.l[i], s.c[i], t)
            if ex:
                res.records.append(acct.close(pos, ex[0], ex[1], t))
        ev = ds.events.get(t)
        if ev:
            if t // DAY != day:
                day, day_start = t // DAY, acct.balance
            if (acct.balance - day_start) / cfg.start_balance > -cfg.max_daily_loss_pct and len(acct.positions) < cfg.max_open:
                reg = ds.regime(t)
                sigs = [g for sym, f in ev
                        if sym not in acct.positions and t >= acct.cooldown_until.get(sym, 0)
                        for g in [decide(sym, f, cfg, reg)] if g]
                sigs.sort(key=lambda g: (g.score, g.vol_ratio), reverse=True)
                for g in sigs[: cfg.max_new_per_scan]:
                    acct.open(g, g.price, t)
        if acct.positions:
            eq = acct.balance
            for sym, pos in acct.positions.items():
                i = ds.at(sym, t)
                eq += pos.unrealized(ds.s[sym].c[i]) if i is not None else 0.0
        else:
            eq = acct.balance
        peak = max(peak, eq)
        res.max_dd = max(res.max_dd, (peak - eq) / (peak if cfg.compound else cfg.start_balance))
    for sym, pos in list(acct.positions.items()):
        s = ds.s[sym]
        i = max(0, bisect_left(s.ts, last_t + 1) - 1)
        res.records.append(acct.close(pos, "END", s.c[i], last_t))
    res.end = acct.balance
    return res
