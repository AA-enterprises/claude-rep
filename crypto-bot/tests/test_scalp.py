import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scalp import backtest, indicators as ind, messages, sim
from scalp.account import PaperAccount
from scalp.config import ScalpConfig
from scalp.signals import Signal, evaluate

CFG = ScalpConfig(fee_rate=0.0, slippage_pct=0.0, exit_mode="roi")


def sig(side="LONG", sym="X/USDT:USDT"):
    return Signal(sym, side, 3, ["a", "b", "c"], 2.0, 0.01, 100.0)


def test_indicators():
    assert ind.ema([5] * 10, 3)[-1] == pytest.approx(5)
    assert ind.rsi(list(range(1, 40))) == 100.0


def test_tp_sl_prices_use_roi_and_leverage():
    a = PaperAccount(CFG)
    p = a.open(sig("LONG"), 100.0, 0)
    assert p.tp == pytest.approx(107.0) and p.sl == pytest.approx(98.0)   # 10x: +70% / -20% ROI
    s = PaperAccount(CFG).open(sig("SHORT"), 100.0, 0)
    assert s.tp == pytest.approx(93.0) and s.sl == pytest.approx(102.0)


def test_tp_gives_70_percent_roi_and_sl_minus_20():
    a = PaperAccount(CFG)
    p = a.open(sig("LONG"), 100.0, 0)
    reason, px = a.check_exit(p, 108, 99, 107, 1)
    assert reason == "TP"
    rec = a.close(p, reason, px, 1)
    assert rec["roi"] == pytest.approx(0.70)
    b = PaperAccount(CFG)
    p = b.open(sig("SHORT"), 100.0, 0)
    reason, px = b.check_exit(p, 103, 99, 100, 1)
    assert reason == "SL" and b.close(p, reason, px, 1)["roi"] == pytest.approx(-0.20)


def test_sl_wins_when_both_touched_and_timeout():
    a = PaperAccount(CFG)
    p = a.open(sig("LONG"), 100.0, 0)
    assert a.check_exit(p, 120, 90, 100, 1)[0] == "SL"
    assert a.check_exit(p, 100, 100, 100, p.max_hold_ms)[0] == "TIMEOUT"


def test_fees_reduce_profit_and_limits():
    cfg = ScalpConfig(slippage_pct=0.0, exit_mode="roi")
    a = PaperAccount(cfg)
    p = a.open(sig(), 100.0, 0)
    rec = a.close(p, "TP", p.tp, 1)
    assert rec["roi"] < 0.70
    for i in range(10):
        a.open(sig(sym=f"C{i}"), 100.0, 0)
    assert len(a.positions) <= cfg.max_open


def test_state_roundtrip():
    a = PaperAccount(CFG)
    a.open(sig(), 100.0, 5)
    b = PaperAccount.from_dict(CFG, a.to_dict())
    assert b.positions.keys() == a.positions.keys() and b.balance == a.balance


def test_signal_long_on_breakout_with_volume():
    cfg = ScalpConfig()
    cs = [(i, 100 + i * 0.2, 100.4 + i * 0.2, 99.6 + i * 0.2, 100 + i * 0.2 + (0.2 if i % 3 else -0.1), 100.0)
          for i in range(260)]
    t, o, h, l, c, v = cs[-1]
    cs[-1] = (t, c, c * 1.03, c, c * 1.025, 400.0)
    s = evaluate("X", cs, cfg)
    assert s and s.side == "LONG" and s.score >= 3


def test_no_signal_when_too_few_candles():
    assert evaluate("X", sim.coin(50, 10, 1, 900_000), ScalpConfig()) is None


def test_backtest_books_balance_and_closes_everything():
    cfg = ScalpConfig()
    r = backtest.run(sim.market(cfg, coins=5, n=500), cfg)
    assert r.end == pytest.approx(cfg.start_balance + sum(x["pnl"] for x in r.records), rel=1e-9)
    assert all(x["reason"] in ("TP", "TRAIL", "SL", "TIMEOUT", "END") for x in r.records)


def test_messages():
    a = PaperAccount(ScalpConfig(exit_mode="roi"))
    p = a.open(sig("SHORT", "SOL/USDT:USDT"), 70.03, 1_763_172_900_000)
    m = messages.opened(p, a.cfg, a.balance)
    assert "SHORT" in m and "SOLUSDT" in m and "Take Profit" in m and "Stop" in m
    rec = a.close(p, "TP", p.tp, 1_763_176_500_000)
    c = messages.closed(rec, a.balance, {"n": 1, "win_rate": 1.0, "pnl": rec["pnl"]})
    assert "TAKE PROFIT HIT" in c and "Profit booked" in c and "ROI" in c


def test_fast_features_match_live_evaluate():
    from scalp.features import Series, compute
    from scalp.signals import decide, evaluate
    cfg = ScalpConfig(min_gates=2, min_atr_pct=0.002)
    cs = sim.coin(1500, 50, 7, cfg.tf_ms)
    s = Series.from_candles(cs)
    feats = compute(s.h, s.l, s.c, s.v)
    agree = total = 0
    for i in range(600, 1500, 7):
        a = decide("X", feats[i], cfg) if i in feats else None
        b = evaluate("X", cs[: i + 1], cfg)
        total += 1
        agree += (a.side if a else None) == (b.side if b else None)
    assert agree / total >= 0.95


def test_fast_backtest_matches_paper_logic_and_accounts():
    cfg = ScalpConfig()
    data = sim.market(cfg, coins=4, n=800)
    r = backtest.run(data, cfg)
    assert r.end == pytest.approx(cfg.start_balance + sum(x["pnl"] for x in r.records), rel=1e-9)
    ds = backtest.Dataset.from_candles(data, cfg.tf_ms)
    mid = ds.tmin + (ds.tmax - ds.tmin) // 2
    a, b = backtest.run(ds, cfg, ds.tmin, mid), backtest.run(ds, cfg, mid, ds.tmax + 1)
    assert a.start == b.start == cfg.start_balance


def test_sides_and_btc_filter():
    from scalp.features import Feat
    from scalp.signals import decide
    f = Feat(100.0, 0.01, 2.0, 3, 0, (True, True, True, False), (False,) * 4)
    assert decide("X", f, ScalpConfig(sides="short")) is None
    assert decide("X", f, ScalpConfig(btc_filter=True), regime=-1) is None
    assert decide("X", f, ScalpConfig(btc_filter=True), regime=1).side == "LONG"


def test_sweep_runs_and_reports(tmp_path):
    from scalp import sweep
    cfg = ScalpConfig()
    ds = backtest.Dataset.from_candles(sim.market(cfg, coins=5, n=1500), cfg.tf_ms)
    rows = sweep.sweep(ds, cfg, sweep.QUICK, out_csv=str(tmp_path / "o.csv"), log=lambda *_: None)
    assert len(rows) == 8 and "VERDICT" in sweep.report(rows)
    assert (tmp_path / "o.csv").exists()


def test_download_resume_and_cache(tmp_path):
    from scalp import history
    cfg = ScalpConfig()
    allc = sim.coin(2500, 100, 3, cfg.tf_ms)
    now = allc[-1][0] + cfg.tf_ms + 1

    class Ex:
        def __init__(self, upto): self.upto = upto
        def milliseconds(self): return self.upto[-1][0] + cfg.tf_ms
        def fetch_ohlcv(self, s, tf, since=None, limit=1000):
            return [list(c) for c in self.upto if c[0] >= since][:limit]

    sym = "BTC/USDT:USDT"
    history.download(Ex(allc[:1500]), sym, "15m", cfg.tf_ms, 1, str(tmp_path), log=lambda *_: None)
    history.download(Ex(allc), sym, "15m", cfg.tf_ms, 1, str(tmp_path), log=lambda *_: None)   # resume
    series = history.load_cache(str(tmp_path), "15m")
    assert list(series) == [sym]
    assert len(series[sym].ts) == 2500      # resume ke baad na duplicate, na gap
    assert all(b - a == cfg.tf_ms for a, b in zip(series[sym].ts, series[sym].ts[1:]))


def test_backtest_finds_trades_and_split_is_grid_aligned():
    cfg = ScalpConfig()
    ds = backtest.Dataset.from_candles(sim.market(cfg, coins=6, n=2000), cfg.tf_ms)
    assert len(backtest.run(ds, cfg).records) > 0
    odd = ds.tmin + 123_457            # candle grid par nahi
    assert len(backtest.run(ds, cfg, odd, ds.tmax + 1).records) > 0


def atr_cfg(**kw):
    base = dict(fee_rate=0.0, slippage_pct=0.0, exit_mode="atr", sl_atr=1.5, tp_atr=3.0,
                trail_start_atr=1.5, trail_atr=1.5, risk_pct=0.01, margin_pct=0.10)
    base.update(kw)
    return ScalpConfig(**base)


def atr_sig(side="LONG"):
    return Signal("X/USDT:USDT", side, 3, ["a", "b", "c"], 2.0, 0.01, 100.0)     # ATR = 1.0


def test_atr_stop_target_and_risk_sizing():
    a = PaperAccount(atr_cfg())
    p = a.open(atr_sig("LONG"), 100.0, 0)
    assert p.sl == pytest.approx(98.5) and p.tp == pytest.approx(103.0)          # 1.5 ATR / 3 ATR
    assert p.risk == pytest.approx(100.0)                                         # 1% of 10,000
    assert a.close(p, "SL", p.sl, 1)["pnl"] == pytest.approx(-100.0)              # stop = ~1R loss
    capped = PaperAccount(atr_cfg(margin_pct=0.05)).open(atr_sig("LONG"), 100.0, 0)
    assert capped.margin == pytest.approx(500.0) and capped.risk == pytest.approx(75.0)   # margin cap risk ko chhota kar deta hai
    b = PaperAccount(atr_cfg())
    s = b.open(atr_sig("SHORT"), 100.0, 0)
    assert s.sl == pytest.approx(101.5) and s.tp == pytest.approx(97.0)


def test_trailing_stop_ratchets_only_in_profit_direction():
    a = PaperAccount(atr_cfg())
    p = a.open(atr_sig("LONG"), 100.0, 0)
    assert a.check_exit(p, 101.0, 100.5, 101.0, 1) is None and p.sl == pytest.approx(98.5)   # profit < 1.5 ATR: stop wahin
    assert a.check_exit(p, 102.5, 101.5, 102.4, 2) is None
    assert p.sl == pytest.approx(101.0)                                           # best 102.5 - 1.5
    assert a.check_exit(p, 102.0, 101.6, 101.8, 3) is None and p.sl == pytest.approx(101.0)   # kabhi peeche nahi
    reason, px = a.check_exit(p, 101.7, 100.9, 101.0, 4)
    assert reason == "TRAIL" and px == pytest.approx(101.0)
    assert a.close(p, reason, px, 4)["pnl"] > 0                                   # profit lock hua


def test_trailing_short_and_no_fixed_target():
    a = PaperAccount(atr_cfg(tp_atr=0.0))
    p = a.open(atr_sig("SHORT"), 100.0, 0)
    assert p.tp is None
    a.check_exit(p, 99.0, 96.0, 96.5, 1)
    assert p.sl == pytest.approx(97.5)                                            # best 96 + 1.5
    a.check_exit(p, 98.0, 97.0, 97.2, 2)
    assert p.sl == pytest.approx(97.5)
    assert a.check_exit(p, 97.6, 97.0, 97.5, 3)[0] == "TRAIL"


def test_atr_rejects_stop_too_close_to_liquidation():
    a = PaperAccount(atr_cfg(leverage=50))
    assert a.open(Signal("X", "LONG", 3, [], 2.0, 0.05, 100.0), 100.0, 0) is None  # 7.5% stop x 50 = liquidation


def test_state_roundtrip_keeps_trailing_fields():
    a = PaperAccount(atr_cfg())
    p = a.open(atr_sig(), 100.0, 0)
    a.check_exit(p, 102.5, 101.5, 102.4, 1)
    b = PaperAccount.from_dict(atr_cfg(), a.to_dict())
    q = b.positions["X/USDT:USDT"]
    assert q.sl == p.sl and q.best == p.best and q.trail_dist == p.trail_dist and q.tp == p.tp


def test_atr_backtest_fixed_size_no_compounding():
    cfg = ScalpConfig()
    r = backtest.run(sim.market(cfg, coins=6, n=1200), cfg)
    assert r.records and all(abs(x["pnl"]) < cfg.start_balance * 0.05 for x in r.records)   # koi trade 5% se bada nahi
    assert r.end == pytest.approx(cfg.start_balance + sum(x["pnl"] for x in r.records), rel=1e-9)
    assert abs(r.avg_r) < 5


def test_resample_15m_to_1h_and_drops_incomplete_groups():
    from scalp import history
    from scalp.features import Series
    t0 = 3_600_000 * 1000                                        # 1h boundary par
    cs = [(t0 + i * 900_000, 0, 10 + i, 5 - i * 0.1, 7 + i * 0.5, 100.0) for i in range(10)]
    r = history.resample(Series.from_candles(cs), 900_000, 3_600_000)
    assert len(r.ts) == 2                                       # 10 candles: 2 poore ghante, aakhri adhoora drop
    assert r.ts[0] == t0 and r.h[0] == 13 and r.l[0] == pytest.approx(5 - 0.3) and r.c[0] == pytest.approx(7 + 1.5) and r.v[0] == 400.0
    gap = cs[:2] + cs[3:8]                                       # beech ki candle missing -> woh ghanta nahi banega
    assert len(history.resample(Series.from_candles(gap), 900_000, 3_600_000).ts) == 1


def test_fixed_size_backtest_keeps_testing_after_loss_exceeds_capital():
    cfg = ScalpConfig(start_balance=100.0, risk_pct=0.05, margin_pct=0.5, sl_atr=0.5, tp_atr=50.0, trail_atr=0.0, fee_rate=0.01)
    data = sim.market(cfg, coins=6, n=3000)
    r = backtest.run(data, cfg)
    t0, t1 = min(c[0] for cs in data.values() for c in cs), max(c[0] for cs in data.values() for c in cs)
    assert len(r.records) > 30
    assert max(x["closed_ts"] for x in r.records) > t0 + 0.9 * (t1 - t0)       # aakhri 10% data mein bhi trades
    assert r.end < 0                                                            # capital se zyada loss, phir bhi test chalta raha


def test_pass_rule_is_risk_normalized_and_suggests_risk():
    from scalp import sweep
    mk = lambda ret, dd, avg_r, pf, n=200: backtest.Result(1000.0, 1000.0 * (1 + ret), [
        {"pnl": 1.0 if i % 2 else -0.5, "r": avg_r, "closed_ts": 0, "symbol": "X", "side": "LONG", "reason": "TP"} for i in range(n)], dd)
    tr, te = mk(1.7, 0.28, 0.10, 1.2), mk(0.58, 0.36, 0.08, 1.2)      # 4h candidate: dd 36% ho to bhi pass
    assert sweep.passes(tr, te)
    assert not sweep.passes(tr, mk(0.05, 0.50, 0.08, 1.2))              # return/dd < 1
    assert sweep.suggested_risk(0.01, tr, te) == pytest.approx(0.01 * 0.2 / 0.36, abs=1e-4)


def test_subset_and_validate_run_end_to_end():
    from dataclasses import replace
    from scalp import validate
    cfg = replace(ScalpConfig(), timeframe="1h")
    ds = backtest.Dataset.from_candles(
        {k: v for k, v in sim.market(ScalpConfig(), coins=6, n=4000).items()}, ScalpConfig().tf_ms)
    sub = ds.subset(list(ds.s)[:2])
    assert len(sub.s) == 2 and all(sym in sub.s for ev in sub.events.values() for sym, _ in ev)
    lines = []
    validate.validate(ds, ScalpConfig(), log=lines.append)
    text = "\n".join(lines)
    assert "VERDICT" in text and "Monte Carlo" in text and "coin concentration" in text.lower()
    assert validate.parse_overrides(["sl_atr=2.5", "btc_filter=true", "min_gates=4"]) == {"sl_atr": 2.5, "btc_filter": True, "min_gates": 4}
    b = validate.bootstrap([1.0, -1.0, 2.0, -1.0], 0.01, sims=200)
    assert 0 <= b["p_profit"] <= 1 and b["dd95"] >= b["dd50"] >= 0
