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
    def fetch_ohlcv(self, s, tf, since=None, limit=250):
        self.calls = getattr(self, "calls", []) + [(since, limit)]
        rows = [list(c) for c in self.cs if since is None or c[0] >= since]
        return rows[-limit:] if since is None else rows[:limit]


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


def test_stop_moves_silently_and_telegram_has_only_open_and_close(tmp_path):
    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    bot = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), tg, ex=ex)
    bot.scan()
    pos = next(iter(bot.acct.positions.values()))
    sl0 = pos.sl
    ex.price = pos.entry + 2.4 * pos.entry * pos.atr_pct          # ~2.4 ATR profit: trailing chalu
    bot.monitor()
    bot.monitor()
    assert pos.sl > sl0                                           # stop khisak gaya
    assert len(tg.msgs) == 1 and "TRADE OPENED" in tg.msgs[0]     # par Telegram par kuch nahi aaya
    ex.price = pos.sl * 0.999
    bot.monitor()
    assert len(tg.msgs) == 2 and "TRADE CLOSED" in tg.msgs[1] and "Profit booked" in tg.msgs[1]
    bot._roll_day(); bot.day = "2000-01-01"; bot._roll_day()
    assert len(tg.msgs) == 2                                      # daily report bhi Telegram par nahi


def test_periodic_telegram_report(tmp_path):
    import time
    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    bot = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), tg, ex=ex)
    bot.heartbeat()
    assert tg.msgs == [] and bot.last_report > 0                  # pehli baar sirf baseline, report nahi
    bot.scan()
    pos = next(iter(bot.acct.positions.values()))
    ex.price = pos.tp * 1.001
    ex.now = int(time.time() * 1000)                              # fake exchange ki ghadi = asli time (real Binance jaisa)
    bot.monitor()                                                 # 1 closed trade (profit)
    n = len(tg.msgs)
    bot.heartbeat()
    assert len(tg.msgs) == n                                      # 12h abhi nahi hue
    bot.last_report = time.time() - 12.5 * 3600
    bot.heartbeat()
    rep = tg.msgs[-1]
    assert "REPORT" in rep and "Profit booked" in rep and "Trades closed: 1" in rep and "Net:" in rep
    k = len(tg.msgs)
    bot.heartbeat()
    assert len(tg.msgs) == k                                      # dobara turant nahi
    bot2 = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), Rec(), ex=ex)
    assert abs(bot2.last_report - bot.last_report) < 1            # restart ke baad bhi yaad


def test_universe_caps_to_top_coins_by_volume():
    cfg = ScalpConfig(max_coins=2, min_quote_volume=1e6)

    class Ex:
        markets = {f"C{i}/USDT:USDT": {"swap": True, "linear": True, "active": True, "quote": "USDT", "settle": "USDT",
                                       "info": {"contractType": "PERPETUAL", "status": "TRADING"}} for i in range(4)}
        def fetch_tickers(self): return {f"C{i}/USDT:USDT": {"quoteVolume": (i + 1) * 1e7} for i in range(4)}
    syms, _ = scanner.universe(Ex(), cfg)
    assert syms == ["C3/USDT:USDT", "C2/USDT:USDT"]
    assert len(scanner.universe(Ex(), cfg, limit=0)[0]) == 4


def test_candle_cache_fetches_only_new_candles_and_handles_gaps(tmp_path):
    cfg = ScalpConfig()
    ex = FakeEx(cfg)
    bot = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), Rec(), ex=ex)
    sym = "UP/USDT:USDT"
    assert bot._update_candles(sym) and len(bot.candles[sym]) == 260 and ex.calls[-1][0] is None      # pehli baar: poori history
    assert bot._update_candles(sym) is False                                                         # naya candle nahi: koi call nahi
    n_calls = len(ex.calls)
    last = ex.cs[-1]
    ex.cs.append((last[0] + cfg.tf_ms, last[4], last[4] * 1.01, last[4] * 0.99, last[4] * 1.005, 150.0))
    ex.now += cfg.tf_ms
    assert bot._update_candles(sym) and len(bot.candles[sym]) == 261
    since, limit = ex.calls[-1]
    assert since == last[0] + cfg.tf_ms and limit == 100 and len(ex.calls) == n_calls + 1             # sirf naye candle ki request
    assert bot.candles[sym][-1][0] == ex.cs[-1][0]
    for k in range(150):                                                                              # bot lamba band raha: gap
        c = ex.cs[-1]
        ex.cs.append((c[0] + cfg.tf_ms, c[4], c[4] * 1.01, c[4] * 0.99, c[4], 100.0))
    ex.now += 150 * cfg.tf_ms
    assert bot._update_candles(sym) and ex.calls[-1][0] is None                                       # poori history dobara
    ts = [c[0] for c in bot.candles[sym]]
    assert all(b - a == cfg.tf_ms for a, b in zip(ts, ts[1:])) and ts[-1] == ex.cs[-1][0]


def test_second_scan_only_evaluates_symbols_with_a_new_candle(tmp_path):
    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    bot = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), tg, ex=ex)
    bot.scan()
    assert len(bot.acct.positions) == 1
    calls_after_first = len(ex.calls)
    bot.acct.positions.clear()                     # position band maan lo, naya candle nahi aaya
    bot.scan()
    assert len(ex.calls) == calls_after_first      # candle cache hit: network par koi nayi candle request nahi
    assert len(bot.acct.positions) == 0            # purani candle par dobara signal/trade nahi


def test_symbols_list_overrides_universe_and_accepts_short_names(tmp_path):
    import json
    from scalp import config as sc

    assert sc.normalize_symbols("btc, eth;SOL BNB/USDT") == ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
    assert sc.normalize_symbols(["BTC/USDT:USDT", "btc"]) == ["BTC/USDT:USDT"]
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"symbols": ["BTC", "ETH", "SOL", "BNB"], "max_coins": 30}))
    cfg = sc.load(str(f))
    assert cfg.symbols == ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]

    class Ex:
        markets = {f"{n}/USDT:USDT": {"swap": True, "linear": True, "active": True, "quote": "USDT", "settle": "USDT",
                                      "info": {"contractType": "PERPETUAL", "status": "TRADING"}} for n in ("BTC", "ETH", "SOL", "BNB", "DOGE")}
        def fetch_tickers(self): return {s: {"quoteVolume": 1e3} for s in self.markets}      # volume bahut kam: phir bhi chune hue coins aayenge
    syms, _ = scanner.universe(Ex(), cfg)
    assert syms == cfg.symbols and "DOGE/USDT:USDT" not in syms
    assert len(scanner.universe(Ex(), cfg, limit=0)[0]) == 0                                # limit=0: purana universe (volume filter), download ke liye


def test_cache_loader_can_select_only_given_symbols(tmp_path, capsys):
    from scalp import history, sim
    cfg = ScalpConfig()
    for n, seed in (("BTC", 1), ("ETH", 2), ("DOGE", 3)):
        cs = sim.coin(400, 10, seed, cfg.tf_ms)
        with open(history.cache_path(str(tmp_path), f"{n}/USDT:USDT", "15m"), "w", newline="") as f:
            for c in cs:
                f.write(",".join(str(x) for x in c) + "\n")
    got = history.load_cache(str(tmp_path), "15m", only=["BTC/USDT:USDT", "SOL/USDT:USDT", "ETH/USDT:USDT"])
    assert list(got) == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    assert "SOL/USDT:USDT" in capsys.readouterr().out                                         # missing coin ki chetavni


def test_manual_test_trade_opens_and_closes_in_separate_files(tmp_path):
    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    sp, tp = str(tmp_path / "test_state.json"), str(tmp_path / "test_trades.csv")
    ok = scanner.run_test_trade(cfg, "UP/USDT:USDT", "SHORT", 0, sp, tp, tg, ex=ex, sleep=lambda s: None)
    assert ok
    assert "TRADE OPENED" in tg.msgs[0] and "SHORT" in tg.msgs[0] and "manual TEST" in tg.msgs[0]
    assert "TEST TRADE CLOSED" in tg.msgs[-1]
    rows = open(tp).read().strip().splitlines()
    assert len(rows) == 2 and ",TEST," in rows[1]                                  # header + 1 trade
    import json
    st = json.load(open(sp))
    assert st["account"]["positions"] == []
    assert not (tmp_path / "scalp_trades.csv").exists()                             # asli files nahi chhui


def test_auto_test_trade_picks_setup_from_current_candle(tmp_path):
    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    ok = scanner.run_test_trade(cfg, None, None, 0, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), tg, ex=ex, sleep=lambda s: None)
    assert ok and "TRADE OPENED" in tg.msgs[0] and "LONG" in tg.msgs[0] and "UP" in tg.msgs[0] and "TEST" in tg.msgs[0]
    assert "TEST TRADE CLOSED" in tg.msgs[-1]
    assert scanner.stats_from_csv(str(tmp_path / "t.csv"))["n"] == 1


def test_intrabar_live_scan_enters_on_forming_candle_without_waiting(tmp_path):
    from dataclasses import replace
    base = ScalpConfig()
    cfg = replace(base, entry_mode="intrabar")
    ex, tg = FakeEx(cfg), Rec()
    # pichli candle normal, aur abhi ki ADHOORI candle mein breakout + volume (open ts <= now < ts + tf)
    closed = ex.cs[:-1]
    c = closed[-1]
    forming = (ex.now - cfg.tf_ms // 4, c[4], c[4] * 1.04, c[4], c[4] * 1.035, 400.0)
    ex.cs = closed + [forming]
    bot = scanner.Bot(cfg, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), tg, ex=ex)
    bot.scan()
    assert len(bot.acct.positions) == 1 and "TRADE OPENED" in tg.msgs[0]
    assert "INTRABAR" in tg.msgs[0]
    # close mode mein wahi data: band candle par signal nahi, to trade nahi
    ex2, tg2 = FakeEx(base), Rec()
    ex2.cs = closed + [forming]
    bot2 = scanner.Bot(base, str(tmp_path / "s2.json"), str(tmp_path / "t2.csv"), tg2, ex=ex2)
    bot2.scan()
    assert len(bot2.acct.positions) == 0


def test_watch_rows_show_gates_for_each_coin(tmp_path):
    cfg = ScalpConfig()
    ex = FakeEx(cfg)
    rows = scanner.watch_rows(cfg, ex=ex)
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "UP/USDT:USDT" and r["side"] == "LONG" and r["score"] >= 3 and r["ok_atr"]
    assert "breakout" in r["met"] and set(r["met"]) | set(r["missing"]) == set(scanner.GATE_NAMES)


def test_test_trade_skips_untradable_coins_and_explains(tmp_path, capsys):
    from dataclasses import replace
    cfg = replace(ScalpConfig(), leverage=200)                  # itni leverage par koi coin tradable nahi: saaf wajah chahiye
    ex, tg = FakeEx(cfg), Rec()
    try:
        ok = scanner.run_test_trade(cfg, None, None, 0, str(tmp_path / "s.json"), str(tmp_path / "t.csv"), tg, ex=ex, sleep=lambda s: None)
    except RuntimeError as e:
        assert "tradable nahi" in str(e)
        return
    assert not ok and "volatile" in capsys.readouterr().out


def test_dashboard_shows_liquidation_price(tmp_path):
    from dataclasses import replace
    from scalp import dashboard
    cfg = replace(ScalpConfig(), leverage=3)
    ex, tg = FakeEx(cfg), Rec()
    sp, tp = str(tmp_path / "s.json"), str(tmp_path / "t.csv")
    bot = scanner.Bot(cfg, sp, tp, tg, ex=ex)
    bot.scan()
    bot.heartbeat()
    st = dashboard.build_state(sp, tp, sp.replace(".json", "_equity.csv"))
    p = st["positions"][0]
    assert p["liq"] < p["entry"] and 0.25 < p["liq_dist"] < 0.40                 # LONG: liquidation neeche, ~33% door
    assert "Liq. Price" in dashboard.PAGE


def test_dashboard_close_button_flow_end_to_end(tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from scalp import dashboard

    cfg = ScalpConfig()
    ex, tg = FakeEx(cfg), Rec()
    sp, tp = str(tmp_path / "s.json"), str(tmp_path / "t.csv")
    bot = scanner.Bot(cfg, sp, tp, tg, ex=ex)
    bot.scan()
    sym = next(iter(bot.acct.positions))
    bot.heartbeat()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.make_handler(sp, tp, sp.replace(".json", "_equity.csv")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(headers, body):
        req = urllib.request.Request(base + "/api/close", data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)
    good = {"Content-Type": "application/json", "X-Requested-With": "scalp-dashboard"}
    assert post({"Content-Type": "application/json"}, {"symbol": sym})[0] == 403                     # custom header ke bina: nahi
    assert post({**good, "Origin": "http://evil.example"}, {"symbol": sym})[0] == 403                # dusri website: nahi
    assert post(good, {"symbol": "NOPE/USDT:USDT"})[0] == 404                                         # open nahi hai
    assert not os.path.exists(sp.replace(".json", "_commands.jsonl"))
    assert post(good, {"symbol": sym}) == (200, {"ok": True})
    st = dashboard.build_state(sp, tp, sp.replace(".json", "_equity.csv"))
    assert st["positions"][0]["closing"] is True                                                      # UI 'band ho rahi...' dikhayega
    n_msgs = len(tg.msgs)
    bot.heartbeat()                                                                                    # bot agle cycle mein command uthata hai
    assert not bot.acct.positions and "MANUAL CLOSE" in tg.msgs[-1] and len(tg.msgs) == n_msgs + 1
    assert ",MANUAL," in open(tp).read() and not os.path.exists(sp.replace(".json", "_commands.jsonl"))
    srv.shutdown()
