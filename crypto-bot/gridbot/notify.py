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


class TelegramNotifier:
    """Token/chat id/proxy ka order: argument > environment variable > .env file (crypto-bot folder mein).

    TELEGRAM_PROXY (optional): sirf Telegram ka traffic is proxy se jayega, baaki bot (Binance) seedha.
    Jaise: socks5h://127.0.0.1:40000 (Cloudflare WARP proxy mode). `h` = DNS bhi proxy se.
    """

    API = "https://api.telegram.org"

    def __init__(self, token: str | None = None, chat_id: str | None = None, env_file: str = ".env",
                 proxy: str | None = None):
        f = load_dotenv(env_file)
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN") or f.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID") or f.get("TELEGRAM_CHAT_ID")
        raw = proxy or os.environ.get("TELEGRAM_PROXY") or f.get("TELEGRAM_PROXY") or ""
        self.proxies = [x for x in re.split(r"[,;\s]+", raw) if x]      # kai proxy: pehla chale to wahi, warna agla
        self.proxy = self.proxies[0] if self.proxies else None
        self.last_proxy: str | None = None
        self._fails, self._pause_until = 0, 0.0      # lagataar fail hone par Telegram ko kuch der skip (bot atke nahi)

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _post(self, text: str) -> tuple[int, str]:
        """(HTTP status, body). Network fail par exception uthata hai."""
        payload = {"chat_id": self.chat_id, "text": text}
        url = f"{self.API}/bot{self.token}/sendMessage"
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

    def check(self) -> tuple[bool, str]:
        """Test message bhej ke saaf wajah batata hai (error text mein token kabhi nahi hota)."""
        if not self.enabled:
            return False, "token ya chat id set nahi hai"
        try:
            code, body = self._post("✅ Telegram test: bot connected")
        except Exception as e:  # noqa: BLE001
            return False, f"network error ({len(self.proxies)} proxy try ki)" + ": " + explain_network_error(e, self.token) if self.proxies \
                else "network error: " + explain_network_error(e, self.token)
        via = f" (proxy: {self.last_proxy.split('@')[-1]})" if self.last_proxy else ""     # password kabhi nahi dikhate
        if code == 200:
            return True, "ok" + via
        try:
            desc = json.loads(body).get("description", "")
        except Exception:  # noqa: BLE001
            desc = ""
        hint = {401: "token galat ya revoke ho chuka", 400: "chat id galat ya aapne bot ko /start nahi bheja",
                403: "aapne bot ko block kiya hai ya /start nahi bheja", 404: "token galat"}.get(code, "")
        return False, f"HTTP {code}: {desc} ({hint})" if hint else f"HTTP {code}: {desc}"

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
