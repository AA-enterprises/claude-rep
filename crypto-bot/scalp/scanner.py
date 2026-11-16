"""Live paper scanner: Binance USDT-M futures ke saare liquid coins, har 15m candle close par scan."""
from __future__ import annotations

import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from gridbot.notify import TelegramNotifier

from . import messages
from .account import PaperAccount
from .config import ScalpConfig
from .features import MIN_CANDLES, atr_series, regime_series
from .signals import LIVE_CANDLES, Signal, evaluate

TRADE_FIELDS = ["closed_ts", "symbol", "side", "entry", "exit", "reason", "roi", "pnl", "r", "held_min",
                "score", "gates", "vol_ratio", "atr_pct"]


def make_exchange():
    import ccxt
    ex = ccxt.binanceusdm({"enableRateLimit": True})   # public data: API key ki zaroorat nahi
    ex.load_markets()
    return ex


def universe(ex, cfg: ScalpConfig, limit: int | None = None) -> tuple[list[str], dict]:
    """Liquid USDT perpetuals, volume ke hisaab se. limit None = cfg.max_coins, 0 = koi cap nahi."""
    tickers = ex.fetch_tickers()
    if cfg.symbols and limit is None:                  # chune hue coins: volume/cap ka filter nahi, bas market valid ho
        ok = [x for x in cfg.symbols if ex.markets.get(x, {}).get("active")]
        miss = [x for x in cfg.symbols if x not in ok]
        if miss:
            print(f"  WARNING: ye symbols Binance futures par nahi mile: {', '.join(miss)}")
        return ok, tickers
    out = []
    for s, m in ex.markets.items():
        info = m.get("info", {})
        if not (m.get("swap") and m.get("linear") and m.get("active")
                and m.get("quote") == "USDT" and m.get("settle") == "USDT"):
            continue
        if info.get("contractType", "PERPETUAL") != "PERPETUAL" or info.get("status", "TRADING") != "TRADING":
            continue
        qv = (tickers.get(s) or {}).get("quoteVolume") or 0
        if qv >= cfg.min_quote_volume:
            out.append((qv, s))
    out.sort(reverse=True)
    syms = [s for _, s in out]
    cap = cfg.max_coins if limit is None else limit
    return (syms[:cap] if cap else syms), tickers


def fetch_closed(ex, sym: str, cfg: ScalpConfig, limit: int = LIVE_CANDLES) -> list[tuple]:
    now = ex.milliseconds()
    return [tuple(r[:6]) for r in ex.fetch_ohlcv(sym, cfg.timeframe, limit=limit) if r[0] + cfg.tf_ms <= now]


def stats_from_csv(path: str) -> dict:
    n = wins = 0
    pnl = 0.0
    if os.path.exists(path):
        for r in csv.DictReader(open(path)):
            n += 1
            p = float(r["pnl"])
            wins += p > 0
            pnl += p
    return {"n": n, "win_rate": wins / n if n else 0.0, "pnl": pnl}


def window_stats(path: str, since_ms: int) -> dict:
    w = {"n": 0, "wins": 0, "losses": 0, "profit": 0.0, "loss": 0.0, "net": 0.0, "best": ("", 0.0), "worst": ("", 0.0)}
    if not os.path.exists(path):
        return w
    for r in csv.DictReader(open(path)):
        if float(r["closed_ts"]) < since_ms:
            continue
        p = float(r["pnl"])
        w["n"] += 1
        w["net"] += p
        if p > 0:
            w["wins"] += 1
            w["profit"] += p
        else:
            w["losses"] += 1
            w["loss"] += p
        if w["n"] == 1 or p > w["best"][1]:
            w["best"] = (r["symbol"], p)
        if w["n"] == 1 or p < w["worst"][1]:
            w["worst"] = (r["symbol"], p)
    return w


class Bot:
    def __init__(self, cfg: ScalpConfig, state_path: str, trades_path: str, tg: TelegramNotifier, ex=None):
        self.cfg, self.tg, self.ex = cfg, tg, ex or make_exchange()
        self.state_path, self.trades_path = state_path, trades_path
        self.day, self.day_start, self.halted_msg = "", cfg.start_balance, False
        self.acct = PaperAccount(cfg)
        self.prices: dict[str, float] = {}
        self.updated, self.last_eq_log = 0.0, 0.0
        self.last_report = 0.0
        self.candles: dict[str, list[tuple]] = {}     # har coin ki closed candles yaad (memory mein)
        self.equity_path = state_path.replace(".json", "_equity.csv")
        if os.path.exists(state_path):
            st = json.load(open(state_path))
            self.acct = PaperAccount.from_dict(cfg, st["account"])
            self.day, self.day_start = st.get("day", ""), st.get("day_start", self.acct.balance)
            self.last_report = st.get("last_report", 0.0)
            print(f"State load hua: balance {self.acct.balance:,.2f}, open {len(self.acct.positions)}")

    # ---------- helpers ----------
    def save(self) -> None:
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"account": self.acct.to_dict(), "day": self.day, "day_start": self.day_start,
                       "prices": self.prices, "updated": self.updated, "last_report": self.last_report, "start_balance": self.cfg.start_balance}, f)
        for _ in range(10):                      # Windows: dashboard file padh raha ho to replace fail ho sakta hai
            try:
                os.replace(tmp, self.state_path)
                return
            except PermissionError:
                time.sleep(0.1)

    def _maybe_report(self, now: float) -> None:
        """Har `report_hours` ghante mein Telegram report. Pehli baar sirf baseline set hota hai (turant report nahi)."""
        hrs = self.cfg.report_hours
        if hrs <= 0:
            return
        if not self.last_report:
            self.last_report = now
            return
        if now - self.last_report >= hrs * 3600:
            since_ms, now_ms = int(self.last_report * 1000), int(now * 1000)
            unreal = sum(p.unrealized(self.prices.get(sym, p.entry)) for sym, p in self.acct.positions.items())
            self.tg.send(messages.report(window_stats(self.trades_path, since_ms), since_ms, now_ms, self.acct.balance,
                                         self.acct.balance + unreal, len(self.acct.positions), unreal))
            self.last_report = now

    def heartbeat(self) -> None:
        """Har cycle: dashboard ke liye state + (har 60s) equity point + periodic report."""
        now = time.time()
        self._maybe_report(now)
        self.updated = now
        if now - self.last_eq_log >= 60:
            self.last_eq_log = now
            new = not os.path.exists(self.equity_path)
            with open(self.equity_path, "a", newline="") as f:
                if new:
                    f.write("ts,balance,equity\n")
                f.write(f"{int(now * 1000)},{self.acct.balance:.4f},{self.acct.equity(self.prices):.4f}\n")
        self.save()

    def log_trade(self, rec: dict) -> None:
        new = not os.path.exists(self.trades_path)
        with open(self.trades_path, "a", newline="") as f:
            w = csv.DictWriter(f, TRADE_FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: rec[k] for k in TRADE_FIELDS})

    def equity(self, prices: dict[str, float]) -> float:
        return self.acct.equity(prices)

    def _roll_day(self) -> None:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self.day:
            if self.day:
                s = stats_from_csv(self.trades_path)
                print(f"Daily report ({self.day}): balance {self.acct.balance:,.2f} | {s['n']} trades | net {s['pnl']:+,.2f} USDT")
            self.day, self.day_start, self.halted_msg = today, self.acct.balance, False

    def _entries_allowed(self) -> bool:
        loss = self.acct.balance / self.day_start - 1
        if loss <= -self.cfg.max_daily_loss_pct:
            if not self.halted_msg:
                print(f"Daily loss limit hit ({loss:.1%}). Naye trades aaj band.")
                self.halted_msg = True
            return False
        return True

    # ---------- cycle ----------
    def monitor(self) -> None:
        if not self.acct.positions:
            return
        tick = self.ex.fetch_tickers(list(self.acct.positions))
        now = self.ex.milliseconds()
        prices = {s: (tick.get(s) or {}).get("last") for s in self.acct.positions}
        self.prices.update({k: v for k, v in prices.items() if v})
        for sym, pos in list(self.acct.positions.items()):
            last = prices[sym]
            if not last:
                continue
            res = self.acct.check_exit(pos, last, last, last, now, live=True)
            if res:
                rec = self.acct.close(pos, res[0], res[1], now)
                self.log_trade(rec)
                print(f"CLOSE {sym} {rec['reason']} roi {rec['roi']:+.1%}")
                self.tg.send(messages.closed(rec, self.acct.balance, stats_from_csv(self.trades_path)))
                self.save()

    def _update_candles(self, sym: str) -> bool:
        """Cache mein sirf nayi closed candles jodta hai (pehli baar poori history). True = nayi candle mili."""
        cfg, tf = self.cfg, self.cfg.tf_ms
        cs = self.candles.get(sym)
        if cs:
            since = cs[-1][0] + tf
            if since + tf > self.ex.milliseconds():          # agli candle abhi band nahi hui
                return False
            rows = self.ex.fetch_ohlcv(sym, cfg.timeframe, since=since, limit=100)
            now = self.ex.milliseconds()
            new = [tuple(r[:6]) for r in rows if r[0] >= since and r[0] + tf <= now]
            if not new:
                return False
            if new[0][0] == since and len(rows) < 100:       # bina gap ke: bas jod do
                cs.extend(new)
                del cs[:-LIVE_CANDLES]
                return True
            # gap (bot bahut der band raha) ya data khisak gaya: poori history dobara
        full = fetch_closed(self.ex, sym, cfg)
        self.candles[sym] = full
        return bool(full)

    def scan(self) -> None:
        t0 = time.time()
        self._roll_day()
        syms, tickers = universe(self.ex, self.cfg)
        print(f"{time.strftime('%H:%M:%S')} scan: {len(syms)} coins")
        now = self.ex.milliseconds()
        sigs, errors, reg = [], 0, None
        todo = [s for s in syms if s not in self.acct.positions and now >= self.acct.cooldown_until.get(s, 0)]
        if self.cfg.btc_filter and "BTC/USDT:USDT" not in todo:
            todo.append("BTC/USDT:USDT")

        def work(sym: str):
            try:
                return sym, self._update_candles(sym), None
            except Exception as e:  # noqa: BLE001
                return sym, False, e
        with ThreadPoolExecutor(max_workers=max(1, self.cfg.fetch_workers)) as pool:
            results = list(pool.map(work, todo))
        if self.cfg.btc_filter:
            btc = self.candles.get("BTC/USDT:USDT")
            if btc:
                reg = regime_series([c[4] for c in btc])[-1]
                print(f"  BTC regime: {'UP' if reg > 0 else 'DOWN' if reg < 0 else 'n/a'}")
            else:
                print("  BTC regime: data nahi mila (filter skip)")
        for sym, fresh, err in results:
            if err is not None:
                errors += 1
                if errors <= 3:
                    print(f"  {sym}: {type(err).__name__}")
                continue
            cs = self.candles.get(sym) or []
            if fresh and sym in syms and len(cs) >= MIN_CANDLES:      # sirf nayi candle par signal dekho
                s = evaluate(sym, cs, self.cfg, reg)
                if s:
                    sigs.append(s)
        sigs.sort(key=lambda s: (s.score, s.vol_ratio), reverse=True)
        print(f"  signals: {len(sigs)} (errors {errors}) | scan {time.time() - t0:.1f}s")
        if not self._entries_allowed():
            return
        opened = 0
        for s in sigs:
            if opened >= self.cfg.max_new_per_scan or len(self.acct.positions) >= self.cfg.max_open:
                break
            px = (self.ex.fetch_ticker(s.symbol) or {}).get("last") or s.price
            pos = self.acct.open(s, px, self.ex.milliseconds())
            if pos:
                opened += 1
                print(f"OPEN {pos.side} {s.symbol} @ {px}")
                self.tg.send(messages.opened(pos, self.cfg, self.acct.balance))
        self.save()

    def run(self) -> None:
        print(f"Scalp bot started (Paper) | balance {self.acct.balance:,.2f} | Telegram: {'ON (sirf trade open/close)' if self.tg.enabled else 'OFF'}")
        tf = self.cfg.tf_ms / 1000
        next_scan = 0.0
        try:
            while True:
                try:
                    if time.time() >= next_scan:
                        self.scan()
                        next_scan = (int(time.time() / tf) + 1) * tf + 5
                    self.monitor()
                    self.heartbeat()
                except KeyboardInterrupt:
                    raise
                except Exception as e:  # noqa: BLE001  network glitch pe bot band nahi hona chahiye
                    print(f"cycle error: {type(e).__name__}: {str(e)[:120]}")
                    time.sleep(30)
                time.sleep(self.cfg.poll_seconds)
        except KeyboardInterrupt:
            self.save()
            print(f"Bot stopped. Balance {self.acct.balance:,.2f}, open positions: {len(self.acct.positions)}")


def pick_current_setup(bot: "Bot") -> Signal:
    """Abhi ki (adhoori) candle ko bhi shamil karke sabse achha setup. Sirf TEST ke liye (backtest mein aisa nahi hota)."""
    from dataclasses import replace
    relaxed = replace(bot.cfg, min_gates=2, min_atr_pct=0.002)
    syms, _ = universe(bot.ex, bot.cfg)

    def one(sym: str):
        try:
            rows = bot.ex.fetch_ohlcv(sym, bot.cfg.timeframe, limit=LIVE_CANDLES)      # aakhri candle abhi ban rahi hai
            cs = [tuple(r[:6]) for r in rows]
            return sym, cs, (evaluate(sym, cs, relaxed) if len(cs) >= MIN_CANDLES else None)
        except Exception:  # noqa: BLE001
            return sym, [], None
    with ThreadPoolExecutor(max_workers=max(1, bot.cfg.fetch_workers)) as pool:
        res = list(pool.map(one, syms))
    sigs = [g for _, _, g in res if g]
    if sigs:
        best = max(sigs, key=lambda g: (g.score, g.vol_ratio))
        best.gates = ["TEST (abhi ki adhoori candle par): " + "; ".join(best.gates)]
        return best
    # koi setup nahi: sabse bade coin ki trend disha (sirf demo ke liye)
    sym, cs, _ = next(((s_, c_, g) for s_, c_, g in res if c_), (syms[0], [], None))
    from . import indicators as ind
    closes = [c[4] for c in cs]
    side = "LONG" if ind.ema(closes, 20)[-1] >= ind.ema(closes, 50)[-1] else "SHORT"
    atr = atr_series([c[2] for c in cs], [c[3] for c in cs], closes)[-1]
    return Signal(sym, side, 0, ["TEST: koi setup nahi mila, sirf trend disha"], 0.0, atr / closes[-1], closes[-1])


def run_test_trade(cfg: ScalpConfig, symbol: str | None, side: str | None, close_after_min: float, state_path: str,
                   trades_path: str, tg: TelegramNotifier, ex=None, sleep=time.sleep) -> bool:
    """TEST paper trade (alag state file): pipeline dekhne ke liye (Telegram open/close, dashboard, stop khiskna).
    symbol None = abhi ki candle ke hisaab se khud chune. Normal stop/trailing chalta hai, `close_after_min` baad market par band."""
    bot = Bot(cfg, state_path, trades_path, tg, ex=ex)
    if not bot.acct.positions:
        if symbol is None:
            sig = pick_current_setup(bot)
            if side:
                sig.side = side.upper()
            symbol = sig.symbol
            price = (bot.ex.fetch_ticker(symbol) or {}).get("last") or sig.price
        else:
            if not bot._update_candles(symbol) or len(bot.candles[symbol]) < 50:
                print(f"{symbol}: candles nahi mile")
                return False
            cs = bot.candles[symbol]
            atr = atr_series([c[2] for c in cs], [c[3] for c in cs], [c[4] for c in cs])[-1]
            price = (bot.ex.fetch_ticker(symbol) or {}).get("last") or cs[-1][4]
            sig = Signal(symbol, (side or "long").upper(), 0, ["manual TEST trade (asli signal nahi)"], 0.0, atr / price, price)
        pos = bot.acct.open(sig, price, bot.ex.milliseconds())
        if not pos:
            print("Trade khul nahi payi (risk/limit check)")
            return False
        print(f"TEST OPEN {pos.side} {symbol} @ {price} | stop {pos.sl:.4f} | {close_after_min:g} minute baad band hogi")
        print("   kaaran:", "; ".join(pos.gates))
        tg.send(messages.opened(pos, cfg, bot.acct.balance))
        bot.save()
    deadline = time.time() + close_after_min * 60
    while bot.acct.positions:
        bot.monitor()
        bot.heartbeat()
        if not bot.acct.positions:
            break                                           # stop/trailing se khud band ho gayi
        if time.time() >= deadline:
            pos = next(iter(bot.acct.positions.values()))
            px = (bot.ex.fetch_ticker(pos.symbol) or {}).get("last") or pos.entry
            rec = bot.acct.close(pos, "TEST", px, bot.ex.milliseconds())
            bot.log_trade(rec)
            print(f"TEST CLOSE {pos.symbol} roi {rec['roi']:+.2%} pnl {rec['pnl']:+.2f} USDT")
            tg.send(messages.closed(rec, bot.acct.balance, stats_from_csv(trades_path)))
            bot.heartbeat()
            break
        sleep(cfg.poll_seconds)
    return True
