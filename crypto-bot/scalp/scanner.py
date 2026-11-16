"""Live paper scanner: Binance USDT-M futures ke saare liquid coins, har 15m candle close par scan."""
from __future__ import annotations

import csv
import json
import os
import time

from gridbot.notify import TelegramNotifier

from . import messages
from .account import PaperAccount
from .config import ScalpConfig
from .features import MIN_CANDLES, regime_series
from .signals import LIVE_CANDLES, evaluate

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

    def scan(self) -> None:
        self._roll_day()
        syms, tickers = universe(self.ex, self.cfg)
        print(f"{time.strftime('%H:%M:%S')} scan: {len(syms)} coins")
        now = self.ex.milliseconds()
        sigs, errors, reg = [], 0, None
        if self.cfg.btc_filter:
            try:
                reg = regime_series([c[4] for c in fetch_closed(self.ex, "BTC/USDT:USDT", self.cfg)])[-1]
                print(f"  BTC regime: {'UP' if reg > 0 else 'DOWN' if reg < 0 else 'n/a'}")
            except Exception as e:  # noqa: BLE001
                print(f"  BTC regime fetch fail: {type(e).__name__} (filter skip)")
        for sym in syms:
            if sym in self.acct.positions or now < self.acct.cooldown_until.get(sym, 0):
                continue
            try:
                cs = fetch_closed(self.ex, sym, self.cfg)
                if len(cs) >= MIN_CANDLES:
                    s = evaluate(sym, cs, self.cfg, reg)
                    if s:
                        sigs.append(s)
            except Exception as e:  # noqa: BLE001
                errors += 1
                if errors <= 3:
                    print(f"  {sym}: {type(e).__name__}")
        sigs.sort(key=lambda s: (s.score, s.vol_ratio), reverse=True)
        print(f"  signals: {len(sigs)} (errors {errors})")
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
