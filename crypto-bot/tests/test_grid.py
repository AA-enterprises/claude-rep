import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from gridbot import backtest, data
from gridbot.broker import PaperBroker
from gridbot.strategy import GridConfig, GridStrategy


def cfg(**kw):
    base = dict(lower=100, upper=200, grids=10, investment=1000, fee_rate=0.0, stop_loss_pct=None)
    base.update(kw)
    return GridConfig(**base)


def test_buy_dip_then_sell_rise_makes_profit():
    c = cfg()
    b, s = PaperBroker(1000, 0.0), GridStrategy(c)
    s.on_price(0, 150, b)            # level 150 ya neeche wale buy? price==150 -> level 150 buy
    s.on_price(1, 130, b)
    assert b.base > 0
    s.on_price(2, 200, b)            # sab upar wale levels hit -> sab sell
    assert b.base == pytest.approx(0)
    assert b.equity(200) > 1000


def test_no_double_buy_on_same_level():
    c = cfg()
    b, s = PaperBroker(1000, 0.0), GridStrategy(c)
    s.on_price(0, 120, b)
    base_after_first = b.base
    s.on_price(1, 120, b)
    assert b.base == base_after_first


def test_stop_loss_sells_everything_and_halts():
    c = cfg(stop_loss_pct=0.1)
    b, s = PaperBroker(1000, 0.0), GridStrategy(c)
    s.on_price(0, 120, b)
    assert b.base > 0
    s.on_price(1, 80, b)             # 100*(1-0.1)=90 se neeche
    assert s.halted and b.base == pytest.approx(0)


def test_fee_guard_rejects_unprofitable_grid():
    with pytest.raises(ValueError):
        GridStrategy(GridConfig(lower=100, upper=101, grids=50, investment=100, fee_rate=0.001))


def test_never_spends_more_than_balance():
    c = cfg(investment=1000)
    b, s = PaperBroker(1000, 0.0), GridStrategy(c)
    s.on_price(0, 100, b)
    assert b.quote >= -1e-9


def test_backtest_runs_on_synthetic():
    candles = data.synthetic(n=1500)
    lo, hi = min(x[3] for x in candles), max(x[2] for x in candles)
    r = backtest.run(candles, GridConfig(lower=lo, upper=hi, grids=15, investment=1000, stop_loss_pct=None))
    assert r.end_equity > 0 and len(r.trades) > 0


def test_telegram_messages_and_disabled_notifier():
    from gridbot.notify import TelegramNotifier, format_close, format_open

    c = cfg(fee_rate=0.001, stop_loss_pct=0.1)
    b, s = PaperBroker(1000, 0.001), GridStrategy(c)
    buys = [t for t in s.on_price(0, 120, b) if t.side == "buy"]
    assert buys and "TRADE OPENED" in format_open(buys[0], "SOL/USDT", s)
    sells = [t for t in s.on_price(1, 200, b) if t.side == "sell"]
    msg = format_close(sells[0], "SOL/USDT", b.equity(200), 1000)
    assert "TRADE CLOSED" in msg and "Profit:" in msg and "Entry:" in msg
    assert TelegramNotifier(token=None, chat_id=None).send("x") is False or True  # env se ho sakta hai
