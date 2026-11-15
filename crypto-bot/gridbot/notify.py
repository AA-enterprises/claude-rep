"""Telegram notifications.

Env vars (config/git mein kabhi mat rakho):
  TELEGRAM_BOT_TOKEN  - @BotFather se
  TELEGRAM_CHAT_ID    - aapka chat id (@userinfobot se)
Set na ho to notifier chupchap disabled rehta hai.
"""
from __future__ import annotations

import json
import os
import time
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


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        """Kabhi exception nahi uthata: notification fail hone se bot band nahi hona chahiye."""
        if not self.enabled:
            return False
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            data=json.dumps({"chat_id": self.chat_id, "text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status == 200
        except Exception as e:  # noqa: BLE001
            print(f"[telegram] send failed: {type(e).__name__}")  # token print nahi karte
            return False
