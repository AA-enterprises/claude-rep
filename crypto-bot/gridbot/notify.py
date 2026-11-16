"""Telegram notifications.

Env vars (config/git mein kabhi mat rakho):
  TELEGRAM_BOT_TOKEN  - @BotFather se
  TELEGRAM_CHAT_ID    - aapka chat id (@userinfobot se)
Set na ho to notifier chupchap disabled rehta hai.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from .strategy import GridStrategy, Trade


def _utc(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts_ms / 1000))


def format_open(t: Trade, symbol: str, strat: GridStrategy, mode: str = "Paper") -> str:
    # t.price level i par hai; sell target agla level
    i = min(range(len(strat.levels)), key=lambda k: abs(strat.levels[k] - t.price))
    target = strat.levels[i + 1]
    stop = strat.cfg.lower * (1 - strat.cfg.stop_loss_pct) if strat.cfg.stop_loss_pct is not None else None
    gain = (target / t.price - 1 - 2 * strat.cfg.fee_rate) * 100
    lines = [
        f"🟢 TRADE OPENED — BUY @ {t.price:,.2f}",
        f"{symbol.replace('/', '')} · Grid · {mode}",
        "──────────────",
        f"Entry: {t.price:,.2f}",
        f"Take Profit: {target:,.2f} (≈ +{gain:.2f}% after fees)",
        f"Stop (grid-wide): {stop:,.2f}" if stop else "Stop: none",
        f"Size: {t.qty:.6f} ≈ ${t.price * t.qty:,.2f}",
        f"Open positions: {len(strat.holdings)}",
        "──────────────",
        _utc(t.ts),
    ]
    return "\n".join(lines)


def format_close(t: Trade, symbol: str, equity: float, start_equity: float, mode: str = "Paper") -> str:
    stopped = t.reason == "stop-loss"
    icon = "🛑" if stopped else ("✅" if t.pnl >= 0 else "🔴")
    pct = (t.price / t.entry - 1) * 100 if t.entry else 0.0
    lines = [
        f"{icon} TRADE CLOSED — {'STOP-LOSS' if stopped else 'TARGET HIT'} @ {t.price:,.2f}",
        f"{symbol.replace('/', '')} · Grid · {mode}",
        "──────────────",
        f"Entry: {t.entry:,.2f} → Exit: {t.price:,.2f} ({pct:+.2f}%)",
        f"Size: {t.qty:.6f}",
        f"Profit: {t.pnl:+,.2f} USDT (after fees)",
        f"Account equity: {equity:,.2f} ({equity / start_equity - 1:+.2%})",
        "──────────────",
        _utc(t.ts),
    ]
    return "\n".join(lines)


def explain_network_error(e: Exception, token: str | None = None) -> str:
    """Network error ki wajah saaf shabdon mein (token kabhi nahi dikhata)."""
    reason = str(getattr(e, "reason", e))
    if token:
        reason = reason.replace(token, "***")
    low = reason.lower()
    if "socks" in low and ("missing dependencies" in low or "no module" in low):
        hint = "SOCKS support nahi: pip install pysocks (ya pip install -r requirements.txt)"
    elif ("proxy" in low or "40000" in low or "socks" in low) and ("refused" in low or "10061" in low or "timed out" in low or "failed" in low):
        hint = "proxy chalu nahi hai: Cloudflare WARP ko proxy mode mein connect karo (warp-cli status)"
    elif "getaddrinfo" in low or "name or service" in low or "11001" in low:
        hint = "DNS: api.telegram.org ka address nahi mil raha (internet/DNS ya ISP block)"
    elif "timed out" in low or "timeout" in low:
        hint = "timeout: connection beech mein ruk raha hai (ISP/firewall block ya VPN chahiye)"
    elif "certificate" in low or "ssl" in low:
        hint = "SSL: antivirus/firewall ya proxy certificate badal raha hai"
    elif "refused" in low or "10061" in low or "10060" in low or "unreachable" in low:
        hint = "connection refused/blocked: firewall ya ISP block"
    else:
        hint = "network problem"
    return f"{type(e).__name__}: {reason[:160]} -> {hint}"


def load_dotenv(path: str = ".env") -> dict:
    """Simple .env reader: KEY=VALUE lines (# comments ok, quotes optional). File na ho to khali."""
    vals: dict = {}
    try:
        with open(path, encoding="utf-8-sig") as f:       # Notepad BOM bhi chalega
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip("\"'").strip()
    except FileNotFoundError:
        pass
    return vals


TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,50}$")


class TelegramNotifier:
    """Token/chat id/proxy ka order: argument > .env file (crypto-bot folder) > environment variable.

    TELEGRAM_PROXY (optional): sirf Telegram ka traffic is proxy se jayega, baaki bot (Binance) seedha.
    Kai proxy comma se alag karke likh sakte ho. Jaise: socks5h://127.0.0.1:40000
    """

    API = "https://api.telegram.org"

    def __init__(self, token: str | None = None, chat_id: str | None = None, env_file: str = ".env",
                 proxy: str | None = None):
        self.env_file = env_file
        f = load_dotenv(env_file)
        self.src: dict[str, str] = {}

        def pick(name: str, arg: str | None) -> str | None:
            if arg:
                self.src[name] = "argument"
                return arg
            if f.get(name):
                self.src[name] = ".env file"
                return f[name]
            if os.environ.get(name):
                self.src[name] = "environment variable"
                return os.environ[name]
            return None

        self.token = pick("TELEGRAM_BOT_TOKEN", token)
        self.chat_id = pick("TELEGRAM_CHAT_ID", chat_id)
        raw = pick("TELEGRAM_PROXY", proxy) or ""
        self.proxies = [x for x in re.split(r"[,;\s]+", raw) if x]      # kai proxy: pehla chale to wahi, warna agla
        self.proxy = self.proxies[0] if self.proxies else None
        self.last_proxy: str | None = None
        self._fails, self._pause_until = 0, 0.0      # lagataar fail hone par Telegram ko kuch der skip (bot atke nahi)

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _call(self, method: str, payload: dict | None = None) -> tuple[int, str]:
        """(HTTP status, body). Network fail par exception uthata hai."""
        payload = payload or {}
        url = f"{self.API}/bot{self.token}/{method}"
        if self.proxies:                                  # SOCKS/HTTP proxy ke liye requests (+pysocks)
            import requests
            order = self.proxies[:]
            if self.last_proxy in order:                  # jo pichli baar chala wahi pehle
                order.remove(self.last_proxy)
                order.insert(0, self.last_proxy)
            last_exc: Exception | None = None
            for px in order:
                try:
                    r = requests.post(url, json=payload, timeout=15, proxies={"http": px, "https": px})
                    self.last_proxy = px
                    return r.status_code, r.text
                except Exception as e:  # noqa: BLE001
                    last_exc = e
            raise last_exc  # type: ignore[misc]
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def _post(self, text: str) -> tuple[int, str]:
        return self._call("sendMessage", {"chat_id": self.chat_id, "text": text})

    @staticmethod
    def _desc(body: str) -> str:
        try:
            return json.loads(body).get("description", "")
        except Exception:  # noqa: BLE001
            return ""

    def diagnose(self) -> tuple[bool, list[str]]:
        """Step-by-step jaanch: file, token ka format, token valid hai?, chat id sahi hai?, test message. Token kabhi print nahi hota."""
        out: list[str] = []
        f = load_dotenv(self.env_file)
        out.append(f".env file: {os.path.abspath(self.env_file)} -> "
                   + (f"mili (keys: {', '.join(sorted(f)) or 'koi nahi'})" if f else "NAHI mili ya khali (file ka naam bilkul .env hona chahiye, .env.txt nahi)"))
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            ev = os.environ.get(name)
            if ev and f.get(name) and ev != f[name]:
                out.append(f"NOTE: environment variable {name} bhi set hai (alag value). Ab .env wali value use hoti hai.")
        t, c = self.token or "", self.chat_id or ""
        if not t:
            return False, out + ["TOKEN: set nahi hai"]
        issues = []
        if t != t.strip() or " " in t:
            issues.append("space hai")
        if '"' in t or "'" in t:
            issues.append("quotes hain")
        if "apna" in t.lower() or "token" in t.lower() or "yahan" in t.lower():
            issues.append("ye placeholder lagta hai (asli token nahi)")
        if not TOKEN_RE.match(t):
            issues.append("format galat (sahi: 123456789:ABC... 'number:letters', lagbhag 46 akshar)")
        out.append(f"TOKEN: source = {self.src.get('TELEGRAM_BOT_TOKEN')}, lambai = {len(t)} akshar -> "
                   + ("format theek" if not issues else "PROBLEM: " + "; ".join(issues)))
        if not c:
            return False, out + ["CHAT ID: set nahi hai"]
        if not re.fullmatch(r"-?\d+", c):
            out.append("CHAT ID: PROBLEM: sirf numbers hone chahiye" + (" (ye bot token jaisa lagta hai!)" if ":" in c else ""))
        else:
            out.append(f"CHAT ID: source = {self.src.get('TELEGRAM_CHAT_ID')}, numeric -> theek")
        out.append("PROXY: " + (f"{len(self.proxies)} set" if self.proxies else "koi nahi (seedha connection)"))
        try:
            code, body = self._call("getMe")
        except Exception as e:  # noqa: BLE001
            return False, out + ["CONNECTION: FAIL -> " + explain_network_error(e, self.token)]
        out.append("CONNECTION: Telegram tak pahunch gaye" + (f" (proxy: {self.last_proxy.split('@')[-1]})" if self.last_proxy else ""))
        if code != 200:
            hint = {401: "token galat ya revoke ho chuka", 404: "token galat"}.get(code, "")
            return False, out + [f"TOKEN CHECK: FAIL HTTP {code} {self._desc(body)} ({hint}) -> BotFather se token dobara copy karo"]
        try:
            uname = json.loads(body)["result"].get("username", "?")
        except Exception:  # noqa: BLE001
            uname = "?"
        out.append(f"TOKEN CHECK: OK, bot = @{uname}")
        try:
            code, body = self._post("✅ Telegram test: bot connected")
        except Exception as e:  # noqa: BLE001
            return False, out + ["MESSAGE: FAIL -> " + explain_network_error(e, self.token)]
        if code == 200:
            return True, out + ["MESSAGE: OK, aapko Telegram par test message mil gaya hoga"]
        hint = {400: "chat id galat, ya aapne @" + uname + " ko /start nahi bheja", 403: "bot block hai ya /start nahi bheja"}.get(code, "")
        return False, out + [f"MESSAGE: FAIL HTTP {code} {self._desc(body)} ({hint})"]

    def check(self) -> tuple[bool, str]:
        """Chhota test (diagnose ka short version)."""
        if not self.enabled:
            return False, "token ya chat id set nahi hai"
        try:
            code, body = self._post("✅ Telegram test: bot connected")
        except Exception as e:  # noqa: BLE001
            return False, "network error: " + explain_network_error(e, self.token)
        via = f" (proxy: {self.last_proxy.split('@')[-1]})" if self.last_proxy else ""     # password kabhi nahi dikhate
        if code == 200:
            return True, "ok" + via
        hint = {401: "token galat ya revoke ho chuka", 400: "chat id galat ya aapne bot ko /start nahi bheja",
                403: "aapne bot ko block kiya hai ya /start nahi bheja", 404: "token galat"}.get(code, "")
        return False, f"HTTP {code}: {self._desc(body)} ({hint})" if hint else f"HTTP {code}: {self._desc(body)}"

    def send(self, text: str) -> bool:
        """Kabhi exception nahi uthata. 3 baar lagataar fail hone par 10 minute skip, taaki bot har message par 10-15s na atke."""
        if not self.enabled or time.time() < self._pause_until:
            return False
        try:
            ok = self._post(text)[0] == 200
        except Exception as e:  # noqa: BLE001
            print("[telegram] send failed: " + explain_network_error(e, self.token))  # token print nahi karte
            ok = False
        if ok:
            self._fails = 0
            return True
        self._fails += 1
        if self._fails >= 3:
            self._fails, self._pause_until = 0, time.time() + 600
            print("[telegram] 3 baar fail: 10 minute ke liye Telegram skip (bot chalta rahega)")
        return False
