"""Futures Terminal: Asli / Freq / Big teeno bots ek alag dashboard par (alag port, bots ko nahi rokta).

- Har bot ka apna section: bot kaise kaam karta hai, uske apne rules se Find Trades, uski open trades.
- Trade lene par terminal sirf bot ki command file mein request likhta hai; trade bot khud kholta hai (paper).
- Candles sirf Binance ke apne timeframes ke (koi nakli 10m/20m nahi).
- 24 ghante se purani trades dated files mein alag folder (trade_archive/) mein save hoti hain."""
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
PAPER_BUDGET = 2000.0      # terminal se li gayi (haath wali) trades ka poora paper budget: teeno bots ka milakar


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


def archive_old(trades_path: str, out_dir: str, now_ms: int | None = None) -> dict[str, int]:
    """24 ghante se purani trades ko din (Pakistan date) ke hisaab se out_dir/<din>.csv mein save karo. Bot ki apni CSV ko nahi chhedta.
    Dobara chalane par wahi files wahi content ke saath banti hain. Return {din: trades}."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    rows = _rows(trades_path)
    if not rows:
        return {}
    fields = list(rows[0].keys())
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
            w = csv.DictWriter(f, fields)
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
        for bid, cfgf, stf, trf, label in bot_defs:
            cfg_path = os.path.join(self.folder, cfgf)
            cfg = sc.load(cfg_path) if os.path.exists(cfg_path) else sc.ScalpConfig(label=label)
            self.bots[bid] = {"id": bid, "label": cfg.label or label, "cfg": cfg,
                              "state": os.path.join(self.folder, stf), "trades": os.path.join(self.folder, trf),
                              "equity": os.path.join(self.folder, stf.replace(".json", "_equity.csv")),
                              "archive": os.path.join(self.folder, "trade_archive", bid)}
        self._ex_factory = ex_factory
        self._ex_find = self._ex_klines = None
        self._sig_cache: dict[str, dict] = {}
        self._sig_lock = {b: threading.Lock() for b in self.bots}
        self._kl_cache: dict[tuple, tuple[float, list]] = {}
        self._kl_lock = threading.Lock()

    def _exchange(self, which: str):
        if self._ex_factory is None:
            from .scanner import make_exchange
            self._ex_factory = make_exchange
        attr = "_ex_find" if which == "find" else "_ex_klines"
        if getattr(self, attr) is None:
            setattr(self, attr, self._ex_factory())
        return getattr(self, attr)

    def bot(self, bid: str) -> dict:
        if bid not in self.bots:
            raise KeyError("bot nahi mila")
        return self.bots[bid]

    def pool(self) -> dict:
        """Teeno bots ka milakar ek paper budget: budget + haath wali band trades ka net, minus haath wali khuli trades ka margin."""
        used = 0.0
        realized = 0.0
        for b in self.bots.values():
            st = dashboard._read_json(b["state"]) or {}
            used += sum(p["margin"] for p in st.get("account", {}).get("positions", []) if p.get("manual"))
            realized += sum(_num(r, "pnl") for r in _rows(b["trades"]) if str(r.get("manual", "")).strip() in ("1", "True"))
        total = self.budget + realized
        return {"budget": self.budget, "realized": realized, "total": total, "used": used, "free": max(0.0, total - used)}

    # ---------- read ----------
    def overview(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        now_ms = int(now * 1000)
        out = []
        for b in self.bots.values():
            st = dashboard.build_state(b["state"], b["trades"], b["equity"], now=now)
            cfg = b["cfg"]
            info = {"id": b["id"], "label": b["label"], "about": describe(cfg),
                    "rules": {"leverage": cfg.leverage, "min_gates": cfg.min_gates, "timeframe": cfg.timeframe,
                              "sl_atr": cfg.sl_atr, "max_hold_hours": cfg.max_hold_hours, "max_open": cfg.max_open,
                              "maint_margin_rate": cfg.maint_margin_rate, "fee_rate": cfg.fee_rate}}
            if st.get("status") == "no_state":
                info["state"] = {"status": "no_state"}
            else:
                recent = [t for t in st["trades"] if t["closed_ts"] > now_ms - DAY_MS]
                free = st["balance"] - sum(p["margin"] for p in st["positions"])
                info["state"] = {k: st[k] for k in ("status", "age_sec", "balance", "equity", "unrealized", "return_pct",
                                                    "positions", "today", "stats", "fees_all", "net_if_closed")}
                info["state"]["free_margin"] = free + st["unrealized"]
                info["state"]["trades24"] = recent
                info["state"]["margin_used"] = sum(p["margin"] for p in st["positions"])
            info["archive_days"] = self.archive_days(b["id"], now_ms)
            out.append(info)
        return {"bots": out, "timeframes": list(TIMEFRAMES), "now_ms": now_ms, "pool": self.pool()}

    def archive_days(self, bid: str, now_ms: int | None = None) -> list[dict]:
        b = self.bot(bid)
        archive_old(b["trades"], b["archive"], now_ms)
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
            st = dashboard._read_json(b["state"]) or {}
            open_syms = {p["symbol"] for p in st.get("account", {}).get("positions", [])}
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

    # ---------- write (bot ki command file) ----------
    def _push(self, b: dict, cmd: dict) -> None:
        with open(b["state"].replace(".json", "_commands.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({**cmd, "ts": time.time()}) + "\n")

    def take(self, bid: str, symbol: str, side: str, leverage: int, margin: float, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        b = self.bot(bid)
        if not isinstance(leverage, int) or isinstance(leverage, bool) or not 1 <= leverage <= 20:
            return {"ok": False, "error": "leverage 1x se 20x ke beech ek poora number hona chahiye"}
        if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not 1 <= margin <= 1_000_000:
            return {"ok": False, "error": "margin (USDT) kam se kam 1 hona chahiye"}
        st = dashboard._read_json(b["state"])
        if not st or now - st.get("updated", 0) > 60:
            return {"ok": False, "error": f"{b['label']} bot chal nahi raha (ya data purana hai): pehle bot chalao"}
        if not st.get("manual_ok"):
            return {"ok": False, "error": f"{b['label']} bot purane code par chal raha hai: git pull karke bot restart karo (tab terminal se trade khulegi)"}
        acct = st["account"]
        if symbol in {p["symbol"] for p in acct["positions"]}:
            return {"ok": False, "error": "ye coin is bot mein pehle se open hai"}
        free = acct["balance"] - sum(p["margin"] for p in acct["positions"])
        if margin > free:
            return {"ok": False, "error": f"is bot mein free margin sirf ${free:,.2f} hai"}
        pool = self.pool()
        if margin > pool["free"]:
            return {"ok": False, "error": f"dashboard ka paper budget (${pool['total']:,.2f}) mein sirf ${pool['free']:,.2f} free hai"}
        cand = next((x for x in (self._sig_cache.get(bid, {}).get("data", {}).get("items", []))
                     if x["symbol"] == symbol and x["side"] == side), None)
        if not cand or cand["valid_until_ms"] < now * 1000:
            return {"ok": False, "error": "ye candidate purana ho gaya: Find Trades dobara dabao"}
        liq_dist = 1 / leverage - b["cfg"].maint_margin_rate
        if liq_dist <= cand["sl_pct"]:
            return {"ok": False, "error": f"{leverage}x par liquidation ({liq_dist:.1%} door) stop ({cand['sl_pct']:.1%} door) se pehle "
                                          f"lag jayegi. Zyada se zyada {cand['max_safe_leverage']}x lo"}
        self._push(b, {"action": "open", "symbol": symbol, "side": side, "leverage": leverage, "margin": float(margin),
                       "atr_pct": cand["atr_pct"], "price": cand["price"], "score": cand["score"],
                       "gates": ["MANUAL (terminal)"] + cand["gates"], "vol_ratio": cand["vol_ratio"]})
        return {"ok": True, "message": f"{b['label']} ko request bhej di: ~10 second mein trade khul jayegi"}

    def close(self, bid: str, symbol: str) -> dict:
        b = self.bot(bid)
        st = dashboard._read_json(b["state"]) or {}
        if symbol not in {p["symbol"] for p in st.get("account", {}).get("positions", [])}:
            return {"ok": False, "error": "ye position ab open nahi hai"}
        self._push(b, {"action": "close", "symbol": symbol})
        return {"ok": True}


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
            if path not in ("/api/take", "/api/close"):
                return self._json(404, {"ok": False, "error": "not found"})
            if not self._safe():
                return self._json(403, {"ok": False, "error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
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
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(term))
    url = f"http://127.0.0.1:{port}"
    print(f"Futures Terminal: {url}  (sirf aapke PC par; band karne ke liye Ctrl+C)")
    print(f"Paper budget (teeno bots ka milakar, haath wali trades ke liye): ${budget:,.0f}")
    print("Bots: " + ", ".join(f"{b['label']}" for b in term.bots.values()) + "  (bots ko chalta rehne do)")
    if open_browser:
        import webbrowser
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
