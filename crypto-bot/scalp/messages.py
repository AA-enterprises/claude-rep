"""Telegram message formats."""
from __future__ import annotations

import time

from .account import Position
from .config import ScalpConfig


def fp(p: float) -> str:
    return f"{p:,.2f}" if p >= 100 else f"{p:.4f}" if p >= 1 else f"{p:.6f}"


def name(sym: str) -> str:
    return sym.split(":")[0].replace("/", "")


def utc(ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ms / 1000))


def dur(minutes: float) -> str:
    m = int(minutes)
    return f"{m // 60}h {m % 60}m" if m >= 60 else f"{m}m"


def opened(pos: Position, cfg: ScalpConfig, equity: float) -> str:
    sl_pct = (pos.sl / pos.entry - 1) * 100
    tp_pct = (pos.tp / pos.entry - 1) * 100
    icon = "🟢" if pos.side == "LONG" else "🔴"
    return "\n".join([
        f"{icon} TRADE OPENED — {pos.side} @ {fp(pos.entry)}",
        f"{name(pos.symbol)} · Scalp · Paper",
        "──────────────",
        f"Side: {pos.side} ({pos.leverage:g}x)",
        f"Entry: {fp(pos.entry)}",
        f"Stop: {fp(pos.sl)} ({sl_pct:+.2f}% price, -{cfg.sl_roi:.0%} ROI, risk ${pos.margin * cfg.sl_roi:,.2f})",
        f"Take Profit: {fp(pos.tp)} ({tp_pct:+.2f}% price, +{cfg.tp_roi:.0%} ROI)",
        f"Size: {pos.qty:,.4f} ≈ ${pos.qty * pos.entry:,.2f} (margin ${pos.margin:,.2f})",
        f"Max hold: until {utc(pos.opened_ts + pos.max_hold_ms)}",
        f"Why: {pos.score}/4 gates — " + "; ".join(pos.gates),
        f"Open positions: see /status · equity ${equity:,.2f}",
        "──────────────",
        utc(pos.opened_ts),
    ])


def closed(rec: dict, equity: float, stats: dict) -> str:
    icon = {"TP": "✅", "SL": "🛑", "TIMEOUT": "⏱"}.get(rec["reason"], "ℹ️")
    label = {"TP": "TAKE PROFIT HIT", "SL": "STOP-LOSS HIT", "TIMEOUT": "MAX HOLD TIME"}.get(rec["reason"], rec["reason"])
    return "\n".join([
        f"{icon} TRADE CLOSED — {label} @ {fp(rec['exit'])}",
        f"{name(rec['symbol'])} · Scalp · Paper · {rec['side']}",
        "──────────────",
        f"Entry: {fp(rec['entry'])} → Exit: {fp(rec['exit'])}",
        f"Result: {rec['roi']:+.1%} ROI · {rec['pnl']:+,.2f} USDT (after fees)",
        f"Held: {dur(rec['held_min'])}",
        f"Equity: ${equity:,.2f}",
        f"Total: {stats['n']} trades · win rate {stats['win_rate']:.0%} · net {stats['pnl']:+,.2f} USDT",
        "──────────────",
        utc(rec["closed_ts"]),
    ])
