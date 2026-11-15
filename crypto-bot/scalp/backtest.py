"""Multi-coin backtest: wahi signals + account jo paper mode mein chalte hain."""
from __future__ import annotations

from dataclasses import dataclass, field

from .account import PaperAccount
from .config import ScalpConfig
from .signals import MIN_CANDLES, evaluate


@dataclass
class Result:
    start: float
    end: float
    records: list[dict] = field(default_factory=list)
    max_dd: float = 0.0

    def summary(self) -> str:
        r = self.records
        n = len(r)
        wins = [x for x in r if x["pnl"] > 0]
        by = {k: sum(1 for x in r if x["reason"] == k) for k in ("TP", "SL", "TIMEOUT", "END")}
        longs = [x for x in r if x["side"] == "LONG"]
        shorts = [x for x in r if x["side"] == "SHORT"]
        def wr(a): return f"{sum(1 for x in a if x['pnl'] > 0) / len(a):.0%}" if a else "-"
        return "\n".join([
            f"Start / End balance : {self.start:,.2f} -> {self.end:,.2f} USDT ({self.end / self.start - 1:+.2%})",
            f"Max drawdown        : {self.max_dd:.2%}",
            f"Trades              : {n} | win rate {len(wins) / n:.0%}" if n else "Trades              : 0",
            f"Exits               : TP {by['TP']} | SL {by['SL']} | TIMEOUT {by['TIMEOUT']} | END {by['END']}",
            f"Long / Short        : {len(longs)} (win {wr(longs)}) / {len(shorts)} (win {wr(shorts)})",
            f"Avg ROI per trade   : {sum(x['roi'] for x in r) / n:+.1%}" if n else "",
        ])


def run(data: dict[str, list[tuple]], cfg: ScalpConfig) -> Result:
    acct = PaperAccount(cfg)
    idx = {s: {c[0]: i for i, c in enumerate(cs)} for s, cs in data.items()}
    all_ts = sorted({c[0] for cs in data.values() for c in cs})
    res = Result(cfg.start_balance, cfg.start_balance)
    peak, last_px = cfg.start_balance, {}
    for ts in all_ts:
        # 1) exits (is candle ke high/low se)
        for sym, pos in list(acct.positions.items()):
            i = idx[sym].get(ts)
            if i is None or ts <= pos.opened_ts:
                continue
            c = data[sym][i]
            ex = acct.check_exit(pos, c[2], c[3], c[4], ts)
            if ex:
                res.records.append(acct.close(pos, ex[0], ex[1], ts))
        # 2) naye signals (candle close par)
        sigs = []
        for sym, cs in data.items():
            i = idx[sym].get(ts)
            if i is None:
                continue
            last_px[sym] = cs[i][4]
            if sym in acct.positions or ts < acct.cooldown_until.get(sym, 0) or i + 1 < MIN_CANDLES:
                continue
            s = evaluate(sym, cs[: i + 1], cfg)
            if s:
                sigs.append(s)
        sigs.sort(key=lambda s: (s.score, s.vol_ratio), reverse=True)
        for s in sigs[: cfg.max_new_per_scan]:
            acct.open(s, s.price, ts)
        eq = acct.equity(last_px)
        peak = max(peak, eq)
        res.max_dd = max(res.max_dd, (peak - eq) / peak)
    for sym, pos in list(acct.positions.items()):          # end par sab band
        res.records.append(acct.close(pos, "END", last_px[sym], all_ts[-1]))
    res.end = acct.balance
    return res
