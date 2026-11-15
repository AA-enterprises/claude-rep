import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scalp import backtest, indicators as ind, messages, sim
from scalp.account import PaperAccount
from scalp.config import ScalpConfig
from scalp.signals import Signal, evaluate

CFG = ScalpConfig(fee_rate=0.0, slippage_pct=0.0)


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
    cfg = ScalpConfig(slippage_pct=0.0)
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
    assert all(x["reason"] in ("TP", "SL", "TIMEOUT", "END") for x in r.records)


def test_messages():
    a = PaperAccount(ScalpConfig())
    p = a.open(sig("SHORT", "SOL/USDT:USDT"), 70.03, 1_763_172_900_000)
    m = messages.opened(p, a.cfg, a.balance)
    assert "SHORT" in m and "SOLUSDT" in m and "Take Profit" in m and "Stop" in m
    rec = a.close(p, "TP", p.tp, 1_763_176_500_000)
    c = messages.closed(rec, a.balance, {"n": 1, "win_rate": 1.0, "pnl": rec["pnl"]})
    assert "TAKE PROFIT HIT" in c and "ROI" in c
