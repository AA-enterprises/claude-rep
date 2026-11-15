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


def test_dashboard_state_reflects_open_and_closed(tmp_path):
    import json
    import urllib.request
    import threading
    from http.server import ThreadingHTTPServer
    from scalp import dashboard

    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    sp, tp = str(tmp_path / "s.json"), str(tmp_path / "t.csv")
    bot = scanner.Bot(cfg, sp, tp, tg, ex=ex)
    bot.scan()
    pos = next(iter(bot.acct.positions.values()))
    ex.price = pos.entry * 1.01
    bot.monitor()
    bot.heartbeat()
    st = dashboard.build_state(sp, tp, sp.replace(".json", "_equity.csv"))
    assert st["status"] == "running" and len(st["positions"]) == 1
    p = st["positions"][0]
    assert p["pnl"] > 0 and p["mark"] == ex.price and p["roi"] > 0.05      # +1% price x10 = ~+10% ROI
    ex.price = pos.tp * 1.001
    bot.monitor()
    bot.heartbeat()
    st = dashboard.build_state(sp, tp, sp.replace(".json", "_equity.csv"))
    assert st["positions"] == [] and st["stats"]["n"] == 1 and st["trades"][0]["reason"] == "TP"

    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.make_handler(sp, tp, sp.replace(".json", "_equity.csv")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    assert json.load(urllib.request.urlopen(base + "/api/state"))["stats"]["n"] == 1
    assert b"Scalp Bot" in urllib.request.urlopen(base + "/").read()
    srv.shutdown()


def test_dashboard_no_state(tmp_path):
    from scalp import dashboard
    assert dashboard.build_state(str(tmp_path / "x.json"), "t.csv", "e.csv")["status"] == "no_state"


def test_dashboard_daily_totals(tmp_path):
    import csv
    import time
    from scalp import dashboard
    from scalp.scanner import TRADE_FIELDS

    st = tmp_path / "s.json"
    st.write_text('{"account": {"balance": 1000, "positions": [], "cooldown_until": {}}, "prices": {}, "updated": %s}' % time.time())
    now = time.time()
    rows = [(now, 30.0), (now - 60, -10.0), (now - 120, -5.0), (now - 86400 * 2, 100.0)]
    with open(tmp_path / "t.csv", "w", newline="") as f:
        w = csv.DictWriter(f, TRADE_FIELDS)
        w.writeheader()
        for ts, pnl in rows:
            w.writerow(dict(closed_ts=int(ts * 1000), symbol="X/USDT:USDT", side="LONG", entry=1, exit=1, reason="TP",
                            roi=0.1, pnl=pnl, held_min=5, score=3, gates="g", vol_ratio=1, atr_pct=0.01))
    out = dashboard.build_state(str(st), str(tmp_path / "t.csv"), "none.csv", now=now)
    t = out["today"]
    assert (t["n"], t["wins"], t["losses"]) == (3, 1, 2)
    assert t["profit"] == 30.0 and t["loss"] == -15.0 and t["net"] == 15.0
    assert len(out["daily"]) == 2 and out["daily"][0]["day"] == t["day"]


def test_stop_move_notifies_telegram(tmp_path):
    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    bot = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), tg, ex=ex)
    bot.scan()
    pos = next(iter(bot.acct.positions.values()))
    n0 = len(tg.msgs)
    ex.price = pos.entry + 2.4 * pos.entry * pos.atr_pct          # ~2.4 ATR profit: trailing chalu
    bot.monitor()
    assert pos.sl > pos.entry * 0.0 and any("STOP MOVED" in m for m in tg.msgs[n0:])
