"""Futures Terminal: bilkul alag, fresh paper account ($2000), jisme Asli / Freq / Big teeno bots ke TAREEQE (method) alag sections mein hain.

- Ye chalte hue bots se juda nahi: apni state/trades files (terminal_*), apna engine (stop/trailing/timeout khud sambhalta hai).
- Har section: bot kaise kaam karta hai, uske rules se Find Trades, aur usi method se li gayi trades.
- Trade turant khulti hai (bot restart ki zaroorat nahi). Candles sirf Binance ke apne timeframes ke.
- 24 ghante se purani trades dated files mein trade_archive/<section>/ mein save hoti hain."""
from __future__ import annotations

import csv
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config as sc
from . import dashboard, finder, schedule
from .account import PaperAccount

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terminal_ui")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8"),
          "/app.js": ("app.js", "application/javascript; charset=utf-8"),
          "/lightweight-charts.js": ("lightweight-charts.js", "application/javascript; charset=utf-8")}
TIMEFRAMES = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h")          # sirf Binance futures ke apne
BOT_DEFS = [("asli", "scalp_config.json", "scalp_state.json", "scalp_trades.csv", "ASLI"),
            ("freq", "scalp_config_freq.json", "scalp_state_freq.json", "scalp_trades_freq.csv", "FREQ"),
            ("big", "scalp_config_big.json", "scalp_state_big.json", "scalp_trades_big.csv", "BIG")]
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}/USDT:USDT$")
DAY_MS = 86_400_000
PAPER_BUDGET = 2000.0      # terminal ka poora paper budget (teeno sections ka milakar)
TRADE_FIELDS = ["closed_ts", "symbol", "side", "entry", "exit", "reason", "roi", "pnl", "r", "held_min", "score", "gates",
                "vol_ratio", "atr_pct", "fees", "manual", "method"]


def describe(cfg: sc.ScalpConfig) -> list[str]:
    """Bot ke rules, config se (taaki likha hua hamesha asli settings se mile)."""
    cap = cfg.start_balance * cfg.margin_pct * cfg.leverage
    lines = [
        f"Ye bot {cfg.timeframe} candles par TREND-FOLLOWING karta hai: jo coin upar ya neeche mazbooti se chal raha ho, usi ki taraf trade (LONG ya SHORT).",
        f"Signal tab banta hai jab 4 mein se kam se kam {cfg.min_gates} shartein poori hon: trend, momentum, breakout aur volume.",
        ("Har 15 minute mein abhi ban rahi candle bhi dekhta hai, candle band hone ka intezaar nahi karta."
         if cfg.entry_mode == "intrabar" else f"Signal {cfg.timeframe} candle band hone par dekhta hai."),
        f"Top {cfg.max_coins} liquid coins (24h volume ke hisaab se) scan hote hain. Bahut volatile coin (ATR {cfg.max_atr_pct:.0%} se zyada) skip." if cfg.max_atr_pct else
        f"Top {cfg.max_coins} liquid coins scan hote hain.",
        f"Risk: har trade mein balance ka {cfg.risk_pct:.1%}, leverage {cfg.leverage:g}x, ek trade ka size lagbhag ${cap:,.0f} tak.",
        f"Stop-loss: {cfg.sl_atr:g} ATR door. Koi fixed profit target nahi: trailing stop ({cfg.trail_start_atr:g} ATR profit ke baad shuru, {cfg.trail_atr:g} ATR peeche) profit lock karta hai.",
        f"Zyada se zyada {cfg.max_hold_hours:g} ghante hold, ek saath {cfg.max_open} trades tak, ek scan mein {cfg.max_new_per_scan} naye tak.",
    ]
    return lines


def pkt_day(ms: int, tz: float = schedule.PKT_HOURS) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000 + tz * 3600))


def _rows(path: str) -> list[dict]:
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def archive_old(trades_path: str, out_dir: str, now_ms: int | None = None, method: str | None = None) -> dict[str, int]:
    """24 ghante se purani trades ko din (Pakistan date) ke hisaab se out_dir/<din>.csv mein save karo. Bot ki apni CSV ko nahi chhedta.
    Dobara chalane par wahi files wahi content ke saath banti hain. Return {din: trades}."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    rows = [r for r in _rows(trades_path) if method is None or r.get("method") == method]
    if not rows:
        return {}
    fields = TRADE_FIELDS
    days: dict[str, list[dict]] = {}
    for r in rows:
        ts = int(float(r["closed_ts"]))
        if ts <= now_ms - DAY_MS:
            days.setdefault(pkt_day(ts), []).append(r)
    os.makedirs(out_dir, exist_ok=True) if days else None
    for day, rs in days.items():
        path = os.path.join(out_dir, f"{day}.csv")
        old = _rows(path)
        if len(old) == len(rs):
            continue
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as f:
            w = csv.DictWriter(f, fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rs)
        os.replace(tmp, path)
    return {d: len(v) for d, v in days.items()}


def _num(r: dict, k: str) -> float:
    try:
        return float(r.get(k) or 0)
    except ValueError:
        return 0.0


class Terminal:
    def __init__(self, folder: str = ".", ex_factory=None, bot_defs=BOT_DEFS, budget: float = PAPER_BUDGET):
        self.folder = os.path.abspath(folder)
        self.budget = budget
        self.bots = {}
        for bid, cfgf, _stf, _trf, label in bot_defs:
            cfg_path = os.path.join(self.folder, cfgf)
            cfg = sc.load(cfg_path) if os.path.exists(cfg_path) else sc.ScalpConfig(label=label)
            self.bots[bid] = {"id": bid, "label": cfg.label or label, "cfg": cfg,
                              "archive": os.path.join(self.folder, "trade_archive", bid)}
        self.state_path = os.path.join(self.folder, "terminal_state.json")
        self.trades_path = os.path.join(self.folder, "terminal_trades.csv")
        self.equity_path = os.path.join(self.folder, "terminal_state_equity.csv")
        self.cfg = sc.ScalpConfig(start_balance=budget, label="TERMINAL")
        self.auto_path = os.path.join(self.folder, "terminal_auto.json")
        saved = dashboard._read_json(self.auto_path) or {}
        self.auto = {bid: bool(saved.get(bid)) for bid in self.bots}
        self.auto_info = {bid: {"last_ms": 0, "note": "abhi tak scan nahi hua"} for bid in self.bots}
        self._auto_next = {bid: 0.0 for bid in self.bots}
        self.lock = threading.RLock()
        self.prices: dict[str, float] = {}
        self.last_eq = 0.0
        st = dashboard._read_json(self.state_path)
        self.acct = PaperAccount.from_dict(self.cfg, st["account"]) if st and "account" in st else PaperAccount(self.cfg)
        self._ex_factory = ex_factory
        self._ex: dict[str, object] = {}
        self._sig_cache: dict[str, dict] = {}
        self._sig_lock = {b: threading.Lock() for b in self.bots}
        self._kl_cache: dict[tuple, tuple[float, list]] = {}
        self._kl_lock = threading.Lock()
        self.save()

    def _exchange(self, which: str):
        if self._ex_factory is None:
            from .scanner import make_exchange
            self._ex_factory = make_exchange
        if which not in self._ex:                      # ccxt thread-safe nahi: har kaam ka apna exchange object
            self._ex[which] = self._ex_factory()
        return self._ex[which]

    def bot(self, bid: str) -> dict:
        if bid not in self.bots:
            raise KeyError("section nahi mila")
        return self.bots[bid]

    # ---------- engine: khuli trades ka stop / trailing / timeout ----------
    def save(self) -> None:
        with self.lock:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"account": self.acct.to_dict(), "prices": self.prices, "updated": time.time(),
                           "fee_rate": self.cfg.fee_rate, "slippage_pct": self.cfg.slippage_pct, "start_balance": self.budget}, f)
            for _ in range(10):
                try:
                    os.replace(tmp, self.state_path)
                    return
                except PermissionError:
                    time.sleep(0.1)

    def _log(self, rec: dict) -> None:
        new = not os.path.exists(self.trades_path)
        with open(self.trades_path, "a", newline="") as f:
            w = csv.DictWriter(f, TRADE_FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(rec)

    def tick(self) -> None:
        """Khuli trades ki live price lo, exit rules (SL / trailing / timeout) lagao. Engine thread har ~5 second chalata hai."""
        with self.lock:
            if self.acct.positions:
                try:
                    ex = self._exchange("engine")
                    tick = ex.fetch_tickers(list(self.acct.positions))
                    now = ex.milliseconds()
                except Exception as e:  # noqa: BLE001
                    print(f"engine: price nahi mili ({type(e).__name__}), agli baar")
                    return
                last_px = {s: (tick.get(s) or {}).get("last") for s in self.acct.positions}
                self.prices.update({k: v for k, v in last_px.items() if v})
                for sym, pos in list(self.acct.positions.items()):
                    last = last_px.get(sym)
                    if not last:
                        continue
                    res = self.acct.check_exit(pos, last, last, last, now, live=True)
                    if res:
                        rec = self.acct.close(pos, res[0], res[1], now)
                        self._log(rec)
                        print(f"CLOSE {sym} ({pos.method}) {rec['reason']} pnl {rec['pnl']:+.2f}")
            if time.time() - self.last_eq >= 60:
                self.last_eq = time.time()
                new = not os.path.exists(self.equity_path)
                with open(self.equity_path, "a", newline="") as f:
                    if new:
                        f.write("ts,balance,equity\n")
                    f.write(f"{int(time.time() * 1000)},{self.acct.balance:.4f},{self.acct.equity(self.prices):.4f}\n")
            self.save()

    def run_engine(self, every: float = 5.0) -> None:
        while True:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                print(f"engine error: {type(e).__name__}")
            time.sleep(every)

    # ---------- Auto: bot ke risk rule se khud trade ----------
    def set_auto(self, bid: str, enabled: bool) -> dict:
        self.bot(bid)
        with self.lock:
            self.auto[bid] = bool(enabled)
            self._auto_next[bid] = 0.0                      # ON karte hi foran scan
            tmp = self.auto_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.auto, f)
            os.replace(tmp, self.auto_path)
        return {"ok": True, "enabled": bool(enabled)}

    def auto_size(self, cfg: sc.ScalpConfig, cand: dict) -> tuple[int, float]:
        """Bot ka risk rule, $budget par: risk_pct x budget / stop ki doori, margin-cap ke andar. Return (leverage, margin)."""
        lev = max(1, min(20, int(cfg.leverage)))
        risk_pct = cfg.risk_pct * (cfg.risk_boost_4 if cand["score"] >= 4 else 1.0)
        notional = min(self.budget * risk_pct / cand["sl_pct"], self.budget * cfg.margin_pct * cfg.leverage)
        return lev, notional / lev

    def _today_pnl(self, now: float) -> float:
        today = pkt_day(int(now * 1000))
        return sum(_num(r, "pnl") for r in _rows(self.trades_path) if pkt_day(int(float(r["closed_ts"]))) == today)

    def auto_scan(self, bid: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        b = self.bot(bid)
        cfg = b["cfg"]
        with self.lock:
            open_syms = set(self.acct.positions)
        try:
            data = finder.find(self._exchange("auto"), cfg, open_syms, include_weak=False)
        except Exception as e:  # noqa: BLE001
            self.auto_info[bid] = {"last_ms": int(now * 1000), "note": f"scan fail ({type(e).__name__}), agli baar dobara"}
            return
        opened, why_skip = 0, ""
        with self.lock:
            if self._today_pnl(now) <= -cfg.max_daily_loss_pct * self.budget:
                self.auto_info[bid] = {"last_ms": int(now * 1000), "note": f"aaj ka loss limit ({cfg.max_daily_loss_pct:.0%}) lag gaya: naye trades band"}
                return
            mine = sum(1 for p in self.acct.positions.values() if p.method == bid)
            for it in data["items"]:
                if it["kind"] != "signal" or it["already_open"]:
                    continue
                if opened >= cfg.max_new_per_scan or mine + opened >= cfg.max_open:
                    why_skip = "limit (max trades) pahunch gayi"
                    break
                sym = it["symbol"]
                if sym in self.acct.positions or now * 1000 < self.acct.cooldown_until.get(sym, 0):
                    continue
                if cfg.max_atr_pct and it["atr_pct"] > cfg.max_atr_pct:
                    why_skip = f"{nm_(sym)} bahut volatile"
                    continue
                lev, margin = self.auto_size(cfg, it)
                if margin < 1 or margin > self.acct.free_margin():
                    why_skip = "budget mein jagah nahi"
                    continue
                try:
                    ex = self._exchange("auto")
                    px, ts = (ex.fetch_ticker(sym) or {}).get("last") or it["price"], ex.milliseconds()
                except Exception:  # noqa: BLE001
                    px, ts = it["price"], int(now * 1000)
                pos, why = self.acct.open_manual(sym, it["side"], float(px), ts, lev, margin, it["atr_pct"], it["score"],
                                                 ["AUTO"] + it["gates"], it["vol_ratio"], method_cfg=cfg, method=bid, manual=False)
                if pos:
                    opened += 1
                    self.prices[sym] = float(px)
                    print(f"AUTO OPEN {pos.side} {sym} ({bid}) {lev}x margin {margin:,.2f}")
                else:
                    why_skip = why
            if opened:
                self.save()
        sigs = sum(1 for x in data["items"] if x["kind"] == "signal")
        note = f"{sigs} signal, {opened} trade khuli" + (f" ({why_skip})" if why_skip else "")
        self.auto_info[bid] = {"last_ms": int(now * 1000), "note": note}

    def auto_step(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        for bid in list(self.bots):
            if self.auto.get(bid) and now >= self._auto_next[bid]:
                self._auto_next[bid] = (int(now // 900) + 1) * 900 + 5          # agla scan: agli 15 minute ki candle band hone par
                self.auto_scan(bid, now)

    def run_auto(self, every: float = 5.0) -> None:
        while True:
            try:
                self.auto_step()
            except Exception as e:  # noqa: BLE001
                print(f"auto error: {type(e).__name__}")
            time.sleep(every)

    # ---------- read ----------
    def overview(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        now_ms = int(now * 1000)
        with self.lock:
            self.save()
            st = dashboard.build_state(self.state_path, self.trades_path, self.equity_path, now=now)
            free = self.acct.free_margin()
        out = []
        for b in self.bots.values():
            cfg = b["cfg"]
            pos = [p for p in st["positions"] if p.get("method") == b["id"]]
            tr24 = [t for t in st["trades"] if t.get("method") == b["id"] and t["closed_ts"] > now_ms - DAY_MS]
            out.append({"id": b["id"], "label": b["label"], "about": describe(cfg),
                        "rules": {"leverage": cfg.leverage, "min_gates": cfg.min_gates, "timeframe": cfg.timeframe,
                                  "sl_atr": cfg.sl_atr, "max_hold_hours": cfg.max_hold_hours,
                                  "maint_margin_rate": self.cfg.maint_margin_rate, "fee_rate": self.cfg.fee_rate},
                        "positions": pos, "trades24": tr24, "unrealized": sum(p["pnl"] for p in pos),
                        "net24": sum(t["pnl"] for t in tr24), "archive_days": self.archive_days(b["id"], now_ms),
                        "auto": {"enabled": self.auto.get(b["id"], False), **self.auto_info[b["id"]]}})
        acct = {k: st[k] for k in ("balance", "equity", "unrealized", "return_pct", "today", "stats", "fees_all")}
        acct.update({"budget": self.budget, "free_margin": free, "margin_used": self.budget_used(), "status": st["status"]})
        return {"sections": out, "account": acct, "timeframes": list(TIMEFRAMES), "now_ms": now_ms}

    def budget_used(self) -> float:
        return sum(p.margin for p in self.acct.positions.values())

    def archive_days(self, bid: str, now_ms: int | None = None) -> list[dict]:
        b = self.bot(bid)
        archive_old(self.trades_path, b["archive"], now_ms, method=bid)
        days = []
        if os.path.isdir(b["archive"]):
            for fn in sorted(os.listdir(b["archive"]), reverse=True):
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.csv", fn):
                    rs = _rows(os.path.join(b["archive"], fn))
                    days.append({"day": fn[:-4], "n": len(rs), "net": sum(_num(r, "pnl") for r in rs),
                                 "fees": sum(_num(r, "fees") for r in rs), "wins": sum(_num(r, "pnl") > 0 for r in rs)})
        return days

    def archive_day(self, bid: str, day: str) -> list[dict]:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError("din galat")
        rs = _rows(os.path.join(self.bot(bid)["archive"], f"{day}.csv"))
        rs.sort(key=lambda r: -int(float(r["closed_ts"])))
        return [{**r, "pnl": _num(r, "pnl"), "roi": _num(r, "roi"), "entry": _num(r, "entry"), "exit": _num(r, "exit"),
                 "fees": _num(r, "fees"), "held_min": _num(r, "held_min"), "closed_ts": int(float(r["closed_ts"]))} for r in rs]

    def signals(self, bid: str, refresh: bool = False) -> dict:
        b = self.bot(bid)
        with self._sig_lock[bid]:
            c = self._sig_cache.get(bid)
            if c and not refresh and time.time() - c["at"] < 60:
                return c["data"]
            with self.lock:
                open_syms = set(self.acct.positions)
            data = finder.find(self._exchange("find"), b["cfg"], open_syms)
            self._sig_cache[bid] = {"at": time.time(), "data": data}
            return data

    def klines(self, symbol: str, tf: str, limit: int = 300) -> list[list]:
        if tf not in TIMEFRAMES:
            raise ValueError("timeframe sirf Binance wale: " + ", ".join(TIMEFRAMES))
        if not SYMBOL_RE.match(symbol):
            raise ValueError("symbol galat")
        limit = max(2, min(int(limit), 500))
        key = (symbol, tf, limit)
        with self._kl_lock:
            hit = self._kl_cache.get(key)
            if hit and time.time() - hit[0] < 1.5:
                return hit[1]
            rows = [[r[0] // 1000, r[1], r[2], r[3], r[4], r[5]] for r in self._exchange("klines").fetch_ohlcv(symbol, tf, limit=limit)]
            self._kl_cache[key] = (time.time(), rows)
            return rows

    # ---------- trade lena / band karna ----------
    def take(self, bid: str, symbol: str, side: str, leverage: int, margin: float, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        b = self.bot(bid)
        if not isinstance(leverage, int) or isinstance(leverage, bool) or not 1 <= leverage <= 20:
            return {"ok": False, "error": "leverage 1x se 20x ke beech ek poora number hona chahiye"}
        if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not 1 <= margin <= 1_000_000:
            return {"ok": False, "error": "margin (USDT) kam se kam 1 hona chahiye"}
        cand = next((x for x in (self._sig_cache.get(bid, {}).get("data", {}).get("items", []))
                     if x["symbol"] == symbol and x["side"] == side), None)
        if not cand or cand["valid_until_ms"] < now * 1000:
            return {"ok": False, "error": "ye candidate purana ho gaya: Find Trades dobara dabao"}
        liq_dist = 1 / leverage - self.cfg.maint_margin_rate
        if liq_dist <= cand["sl_pct"]:
            return {"ok": False, "error": f"{leverage}x par liquidation ({liq_dist:.1%} door) stop ({cand['sl_pct']:.1%} door) se pehle "
                                          f"lag jayegi. Zyada se zyada {cand['max_safe_leverage']}x lo"}
        with self.lock:
            if symbol in self.acct.positions:
                return {"ok": False, "error": "ye coin terminal mein pehle se open hai"}
            free = self.acct.free_margin()
            if margin > free:
                return {"ok": False, "error": f"paper budget mein sirf ${free:,.2f} free hai (budget ${self.budget:,.0f})"}
            try:
                px = (self._exchange("engine").fetch_ticker(symbol) or {}).get("last") or cand["price"]
                ts = self._exchange("engine").milliseconds()
            except Exception:  # noqa: BLE001
                px, ts = cand["price"], int(now * 1000)
            pos, why = self.acct.open_manual(symbol, side, float(px), ts, leverage, float(margin), cand["atr_pct"], cand["score"],
                                             ["MANUAL (terminal)"] + cand["gates"], cand["vol_ratio"], method_cfg=b["cfg"], method=bid)
            if not pos:
                return {"ok": False, "error": why}
            self.prices[symbol] = float(px)
            self.save()
        return {"ok": True, "message": f"{nm_(symbol)} {side} khul gayi ({leverage}x, margin ${margin:,.2f}) @ {pos.entry:,.6g}"}

    def close(self, bid: str, symbol: str) -> dict:
        self.bot(bid)
        with self.lock:
            pos = self.acct.positions.get(symbol)
            if not pos or pos.method != bid:
                return {"ok": False, "error": "ye position ab open nahi hai"}
            try:
                ex = self._exchange("engine")
                px = (ex.fetch_ticker(symbol) or {}).get("last") or self.prices.get(symbol) or pos.entry
                ts = ex.milliseconds()
            except Exception:  # noqa: BLE001
                px, ts = self.prices.get(symbol) or pos.entry, int(time.time() * 1000)
            px = px * (1 - pos.d * self.cfg.slippage_pct)
            rec = self.acct.close(pos, "MANUAL", px, ts)
            self._log(rec)
            self.save()
        return {"ok": True, "message": f"band: pnl {rec['pnl']:+.2f} USDT"}


def nm_(sym: str) -> str:
    return sym.split(":")[0].replace("/", "")


def make_handler(term: Terminal):
    class H(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _safe(self) -> bool:
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            return (host.split(":")[0] in ("127.0.0.1", "localhost") and (origin is None or origin == f"http://{host}")
                    and self.headers.get("X-Requested-With") == "scalp-terminal"
                    and self.headers.get("Content-Type", "").startswith("application/json"))

        def do_GET(self):  # noqa: N802
            path, _, query = self.path.partition("?")
            q = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            from urllib.parse import unquote
            q = {k: unquote(v) for k, v in q.items()}
            try:
                if path in STATIC:
                    fn, ctype = STATIC[path]
                    with open(os.path.join(UI_DIR, fn), "rb") as f:
                        return self._send(200, f.read(), ctype)
                if path == "/api/overview":
                    return self._json(200, term.overview())
                if path == "/api/signals":
                    return self._json(200, term.signals(q.get("bot", ""), q.get("refresh") == "1"))
                if path == "/api/klines":
                    return self._json(200, term.klines(q.get("symbol", ""), q.get("tf", "5m"), int(q.get("limit", "300"))))
                if path == "/api/archive":
                    return self._json(200, term.archive_day(q.get("bot", ""), q.get("day", "")))
            except KeyError:
                return self._json(404, {"ok": False, "error": "bot nahi mila"})
            except ValueError as e:
                return self._json(400, {"ok": False, "error": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._json(502, {"ok": False, "error": f"data nahi mila ({type(e).__name__})"})
            self.send_error(404)

        def do_POST(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path not in ("/api/take", "/api/close", "/api/auto"):
                return self._json(404, {"ok": False, "error": "not found"})
            if not self._safe():
                return self._json(403, {"ok": False, "error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
                if path == "/api/auto":
                    return self._json(200, term.set_auto(str(body.get("bot", "")), body.get("enabled") is True))
                if path == "/api/close":
                    return self._json(200, term.close(str(body.get("bot", "")), str(body.get("symbol", ""))))
                lev, mar = body.get("leverage"), body.get("margin")
                return self._json(200, term.take(str(body.get("bot", "")), str(body.get("symbol", "")), str(body.get("side", "")),
                                                 lev if isinstance(lev, int) else -1, mar if isinstance(mar, (int, float)) else -1))
            except KeyError:
                return self._json(404, {"ok": False, "error": "bot nahi mila"})
            except (ValueError, TypeError):
                return self._json(400, {"ok": False, "error": "bad request"})

        def log_message(self, *a):
            pass
    return H


def serve(folder: str = ".", port: int = 8090, open_browser: bool = True, budget: float = PAPER_BUDGET) -> None:
    term = Terminal(folder, budget=budget)
    threading.Thread(target=term.run_engine, daemon=True).start()
    threading.Thread(target=term.run_auto, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(term))
    url = f"http://127.0.0.1:{port}"
    print(f"Futures Terminal: {url}  (sirf aapke PC par; band karne ke liye Ctrl+C)")
    print(f"Fresh paper account: ${budget:,.0f} (teeno sections ka milakar). Sections: " + ", ".join(b["label"] for b in term.bots.values()))
    print("Ye chalte hue bots se alag hai: bots ko restart karne ki zaroorat nahi.")
    if open_browser:
        import webbrowser
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
