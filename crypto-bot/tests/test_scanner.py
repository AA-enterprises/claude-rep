import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scalp import scanner, sim
from scalp.config import ScalpConfig


class FakeEx:
    """Binance jaisa fake exchange: ek coin jisme last candle par breakout + volume spike hai."""
    def __init__(self, cfg):
        self.now = 1_700_000_000_000 + 300 * cfg.tf_ms
        cs = [(self.now - (260 - i) * cfg.tf_ms, 100 + i * 0.2, 100.4 + i * 0.2, 99.6 + i * 0.2,
               100 + i * 0.2 + (0.2 if i % 3 else -0.1), 100.0) for i in range(260)]
        t, o, h, l, c, v = cs[-1]
        cs[-1] = (t, c, c * 1.03, c, c * 1.025, 400.0)
        self.cs, self.price = cs, cs[-1][4]
        self.markets = {"UP/USDT:USDT": {"swap": True, "linear": True, "active": True, "quote": "USDT",
                                         "settle": "USDT", "info": {"contractType": "PERPETUAL", "status": "TRADING"}}}

    def milliseconds(self): return self.now
    def fetch_tickers(self, syms=None): return {"UP/USDT:USDT": {"last": self.price, "quoteVolume": 5e9}}
    def fetch_ticker(self, s): return {"last": self.price}
    def fetch_ohlcv(self, s, tf, limit=250): return [list(c) for c in self.cs[-limit:]]


class Rec:
    enabled = True
    def __init__(self): self.msgs = []
    def send(self, t): self.msgs.append(t); return True


def test_full_cycle(tmp_path):
    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    bot = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), tg, ex=ex)
    bot.scan()
    assert len(bot.acct.positions) == 1 and "TRADE OPENED" in tg.msgs[-1]
    pos = next(iter(bot.acct.positions.values()))
    ex.price = pos.tp * 1.001
    bot.monitor()
    assert not bot.acct.positions and "TAKE PROFIT HIT" in tg.msgs[-1]
    assert scanner.stats_from_csv(str(tmp_path / "t.csv"))["n"] == 1
    bot2 = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), Rec(), ex=ex)  # state reload
    assert bot2.acct.balance == bot.acct.balance
