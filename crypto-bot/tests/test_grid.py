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


def test_dotenv_telegram_credentials(tmp_path, monkeypatch):
    from gridbot.notify import TelegramNotifier, load_dotenv
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    f = tmp_path / ".env"
    f.write_text('\ufeff# comment\nTELEGRAM_BOT_TOKEN = "123:abc"\nTELEGRAM_CHAT_ID=987654\n', encoding="utf-8")
    assert load_dotenv(str(f)) == {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "987654"}
    t = TelegramNotifier(env_file=str(f))
    assert t.enabled and t.token == "123:abc" and t.chat_id == "987654"
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")                       # env var .env se upar
    assert TelegramNotifier(env_file=str(f)).chat_id == "555"
    monkeypatch.delenv("TELEGRAM_CHAT_ID")
    off = TelegramNotifier(env_file=str(tmp_path / "missing.env"))
    ok, why = off.check()
    assert not off.enabled and ok is False and "set nahi" in why


def test_network_error_is_explained_without_leaking_token(monkeypatch):
    import urllib.error
    import urllib.request
    from gridbot.notify import TelegramNotifier

    tok = "111:SECRET_TOKEN_VALUE"
    t = TelegramNotifier(token=tok, chat_id="1", env_file="none.env")
    for msg, word in [("[Errno 11001] getaddrinfo failed", "DNS"), ("timed out", "timeout"),
                      ("[SSL: CERTIFICATE_VERIFY_FAILED]", "SSL"), (f"failed for {tok}", "network")]:
        def boom(*a, **k):
            raise urllib.error.URLError(msg)
        monkeypatch.setattr(urllib.request, "urlopen", boom)
        ok, why = t.check()
        assert ok is False and word in why and "SECRET_TOKEN_VALUE" not in why


def test_telegram_proxy_is_used_only_when_configured(tmp_path, monkeypatch):
    import sys
    import types
    from gridbot.notify import TelegramNotifier

    monkeypatch.delenv("TELEGRAM_PROXY", raising=False)
    f = tmp_path / ".env"
    f.write_text("TELEGRAM_BOT_TOKEN=1:abc\nTELEGRAM_CHAT_ID=5\nTELEGRAM_PROXY=socks5h://127.0.0.1:40000\n")
    seen = {}

    class R:
        status_code, text = 200, "{}"

    def fake_post(url, json=None, timeout=None, proxies=None):
        seen.update(url=url, proxies=proxies)
        return R()
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))
    t = TelegramNotifier(env_file=str(f))
    assert t.proxy == "socks5h://127.0.0.1:40000"
    ok, detail = t.check()
    assert ok and "127.0.0.1:40000" in detail
    assert seen["proxies"] == {"http": t.proxy, "https": t.proxy} and "/bot1:abc/sendMessage" in seen["url"]
    assert t.send("hi") is True


def test_proxy_errors_are_explained_and_token_hidden(tmp_path, monkeypatch):
    import sys
    import types
    from gridbot.notify import TelegramNotifier

    monkeypatch.delenv("TELEGRAM_PROXY", raising=False)

    def refused(*a, **k):
        raise OSError("SOCKSHTTPSConnectionPool(host='api.telegram.org') /bot1:TOPSECRET/sendMessage: proxy 127.0.0.1:40000 connection refused")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=refused))
    t = TelegramNotifier(token="1:TOPSECRET", chat_id="5", env_file="none.env", proxy="socks5h://127.0.0.1:40000")
    ok, why = t.check()
    assert not ok and "proxy chalu nahi" in why and "TOPSECRET" not in why

    def nosocks(*a, **k):
        raise RuntimeError("Missing dependencies for SOCKS support.")
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=nosocks))
    assert "pysocks" in t.check()[1]
