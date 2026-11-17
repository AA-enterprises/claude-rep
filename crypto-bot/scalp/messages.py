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
    tp_pct = (pos.tp / pos.entry - 1) * 100 if pos.tp is not None else 0.0
    icon = "🟢" if pos.side == "LONG" else "🔴"
    if cfg.exit_mode == "atr":
        stop = f"Stop: {fp(pos.sl)} ({sl_pct:+.2f}% price, risk ${pos.risk:,.2f} = 1R)"
        tp_line = (f"Take Profit: {fp(pos.tp)} ({tp_pct:+.2f}% price)" if pos.tp is not None
                   else "Take Profit: koi fixed nahi (trailing stop se exit)")
        extra = ([f"Trailing: {pos.trail_start / pos.entry:.2%} profit ke baad stop peeche chalega ({pos.trail_dist / pos.entry:.2%} door)"]
                 if pos.trail_dist > 0 else [])
    else:
        stop = f"Stop: {fp(pos.sl)} ({sl_pct:+.2f}% price, -{cfg.sl_roi:.0%} ROI, risk ${pos.margin * cfg.sl_roi:,.2f})"
        tp_line = f"Take Profit: {fp(pos.tp)} ({tp_pct:+.2f}% price, +{cfg.tp_roi:.0%} ROI)"
        extra = []
    return "\n".join([
        f"{icon} TRADE OPENED — {pos.side} @ {fp(pos.entry)}",
        f"{name(pos.symbol)} · Scalp · Paper" + (f" · {cfg.label}" if cfg.label else ""),
        "──────────────",
        f"Side: {pos.side} ({pos.leverage:g}x)",
        f"Entry: {fp(pos.entry)}",
        stop,
        tp_line,
        *extra,
        f"Size: {pos.qty:,.4f} ≈ ${pos.qty * pos.entry:,.2f} (margin ${pos.margin:,.2f})" + (f" · Entry fee: ${pos.entry_fee:,.2f}" if pos.entry_fee else ""),
        *([f"Liquidation: {fp(pos.liq)} ({abs(pos.liq / pos.entry - 1):.0%} door)"] if pos.liq else []),
        f"Max hold: until {utc(pos.opened_ts + pos.max_hold_ms)}",
        f"Why: {pos.score}/4 gates — " + "; ".join(pos.gates),
        f"Account equity: ${equity:,.2f}",
        "──────────────",
        utc(pos.opened_ts),
    ])


def closed(rec: dict, equity: float, stats: dict, bot_label: str = "") -> str:
    icon = {"TP": "✅", "TRAIL": "✅", "SL": "🛑", "TIMEOUT": "⏱", "TEST": "🧪", "MANUAL": "🖐"}.get(rec["reason"], "ℹ️")
    label = {"TP": "TAKE PROFIT HIT", "TRAIL": "TRAILING STOP HIT", "SL": "STOP-LOSS HIT", "TIMEOUT": "MAX HOLD TIME", "TEST": "TEST TRADE CLOSED", "MANUAL": "MANUAL CLOSE (aapne dashboard se band ki)"}.get(rec["reason"], rec["reason"])
    return "\n".join([
        f"{icon} TRADE CLOSED — {label} @ {fp(rec['exit'])}",
        f"{name(rec['symbol'])} · Scalp · Paper · {rec['side']}" + (f" · {bot_label}" if bot_label else ""),
        "──────────────",
        f"Entry: {fp(rec['entry'])} → Exit: {fp(rec['exit'])}",
        (f"💰 Profit booked: {rec['pnl']:+,.2f} USDT" if rec["pnl"] > 0 else f"Loss: {rec['pnl']:+,.2f} USDT") + f" (after fees) · {rec['roi']:+.1%} ROI" + (f" · {rec['r']:+.2f}R" if rec.get("r") else ""),
        f"Held: {dur(rec['held_min'])}" + (f" · Fees: ${rec['fees']:,.2f}" if rec.get("fees") else ""),
        f"Equity: ${equity:,.2f}",
        f"Total: {stats['n']} trades · win rate {stats['win_rate']:.0%} · net {stats['pnl']:+,.2f} USDT",
        "──────────────",
        utc(rec["closed_ts"]),
    ])



def report(w: dict, since_ms: int, now_ms: int, balance: float, equity: float, n_open: int, unrealized: float,
           scan: dict | None = None, bot_label: str = "") -> str:
    hours = (now_ms - since_ms) / 3_600_000
    lines = [
        f"📊 {hours:.0f}h REPORT" + (f" · {bot_label}" if bot_label else ""),
        f"{utc(since_ms)} → {utc(now_ms)}",
        "──────────────",
        f"Trades closed: {w['n']} (won {w['wins']} / lost {w['losses']})" + (f" · win rate {w['wins'] / w['n']:.0%}" if w["n"] else ""),
        f"💰 Profit booked: {w['profit']:+,.2f} USDT",
        f"Loss: {w['loss']:+,.2f} USDT",
        f"Net: {w['net']:+,.2f} USDT",
    ]
    if w["n"]:
        lines.append(f"Best: {name(w['best'][0])} {w['best'][1]:+,.2f} · Worst: {name(w['worst'][0])} {w['worst'][1]:+,.2f}")
    if scan is not None:
        lines += ["──────────────",
                  f"🔍 Bot zinda: {scan['scans']} scans · {scan['signals']} signals · {scan['skipped']} skip" +
                  (f" · {scan['opened']} trade khuli" if scan.get("opened") else ""),
                  f"Aakhri scan: {utc(scan['last_scan_ms']) if scan.get('last_scan_ms') else 'abhi tak koi nahi'}"]
        if scan.get("last_skip"):
            lines.append(f"Aakhri skip: {scan['last_skip']}")
    lines += [
        "──────────────",
        f"Open positions: {n_open} (unrealized {unrealized:+,.2f} USDT)",
        f"Balance: ${balance:,.2f} · Equity: ${equity:,.2f}",
    ]
    return "\n".join(lines)


def positions_text(bots: list[tuple[str, dict]]) -> str:
    """Discord /positions: har bot ki open trades (dashboard wale build_state se)."""
    out = []
    for label, st in bots:
        if st.get("status") == "no_state":
            out.append(f"**{label}**: abhi data nahi")
            continue
        pos = st.get("positions", [])
        head = f"**{label}** · Open: {len(pos)}"
        head += f" · Equity ${st['equity']:,.2f}"
        t = st.get("today")
        if t:
            head += f" · Aaj: {t['n']} trades, net {t['net']:+,.2f}"
        out.append(head)
        if not pos:
            out.append("  (koi open trade nahi)")
        for p in pos:
            icon = "🟢" if p["pnl"] >= 0 else "🔴"
            out.append(f"{icon} {name(p['symbol'])} {p['side']} {p['leverage']:.0f}x · entry {fp(p['entry'])} → {fp(p['mark'])}\n"
                       f"   PnL {p['pnl']:+,.2f} ({p['roi']:+.1%}) · fees {p['fees_est']:.2f} · band karein to {p['net_if_closed']:+,.2f}\n"
                       f"   SL {fp(p['sl'])} · Liq {fp(p['liq'])} · {dur(p['held_min'])}/{dur(p['max_hold_min'])}")
    return "\n".join(out)[:1900]
