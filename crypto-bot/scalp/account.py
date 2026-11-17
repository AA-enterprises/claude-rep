"""Paper futures account: leverage, fees, slippage, SL/TP/trailing/timeout."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import ScalpConfig
from .signals import Signal


@dataclass
class Position:
    symbol: str
    side: str
    entry: float
    qty: float
    margin: float
    leverage: float
    tp: float | None
    sl: float
    opened_ts: int
    max_hold_ms: int
    entry_fee: float
    score: int = 0
    gates: list[str] = field(default_factory=list)
    vol_ratio: float = 0.0
    atr_pct: float = 0.0
    trail_start: float = 0.0     # price distance (absolute); 0 = trailing off
    trail_dist: float = 0.0
    best: float = 0.0            # favourable extreme abhi tak
    risk: float = 0.0            # stop lagne par (fees se pehle) USDT loss = 1R
    notified_sl: float = 0.0     # (purana, ab use nahi hota)
    liq: float = 0.0             # liquidation price ka andaza (isolated margin)

    @property
    def d(self) -> int:
        return 1 if self.side == "LONG" else -1

    def unrealized(self, price: float) -> float:
        return self.d * (price - self.entry) * self.qty


class PaperAccount:
    def __init__(self, cfg: ScalpConfig, balance: float | None = None, unlimited: bool = False):
        self.unlimited = unlimited      # sirf backtest: balance khatam hone par bhi sab saal test hote rahein
        self.cfg = cfg
        self.balance = cfg.start_balance if balance is None else balance
        self.positions: dict[str, Position] = {}
        self.cooldown_until: dict[str, int] = {}

    def free_margin(self) -> float:
        return self.balance - sum(p.margin for p in self.positions.values())

    def equity(self, prices: dict[str, float]) -> float:
        return self.balance + sum(p.unrealized(prices.get(s, p.entry)) for s, p in self.positions.items())

    def liq_distance(self) -> float:
        """Entry se liquidation tak price ka % (andaza): 1/leverage - maintenance margin."""
        return max(0.0, 1 / self.cfg.leverage - self.cfg.maint_margin_rate)

    def liq_price(self, entry: float, d: int) -> float:
        return entry * (1 - d * self.liq_distance())

    def reject_reason(self, sig: Signal, price: float) -> str | None:
        """Trade kyun nahi khul sakti (None = khul sakti hai). open() jin shartein par None deta hai, unka saaf kaaran."""
        cfg = self.cfg
        if sig.symbol in self.positions:
            return "pehle se open hai"
        if len(self.positions) >= cfg.max_open:
            return f"{cfg.max_open} trades pehle se open hain (max_open)"
        if self.balance <= 0 and not self.unlimited:
            return "balance khatam"
        if cfg.min_liq_distance and self.liq_distance() < cfg.min_liq_distance:
            return (f"liquidation sirf {self.liq_distance():.0%} door hai ({cfg.leverage:g}x), kam se kam "
                    f"{cfg.min_liq_distance:.0%} chahiye: leverage kam karo")
        if cfg.max_atr_pct and sig.atr_pct > cfg.max_atr_pct:
            return f"coin bahut volatile: ATR {sig.atr_pct:.1%} > limit {cfg.max_atr_pct:.1%}"
        if cfg.exit_mode == "atr":
            sl_frac = cfg.sl_atr * sig.atr_pct * ((sig.price or price) / price)
            if sl_frac <= 0:
                return "ATR zero hai"
            if sl_frac * cfg.leverage > 0.8:
                return (f"coin bahut volatile: stop {sl_frac:.1%} door hai, {cfg.leverage:g}x leverage par "
                        f"liquidation stop se pehle lag jayegi (safety rule)")
        return None

    def open(self, sig: Signal, price: float, ts: int) -> Position | None:
        cfg = self.cfg
        if sig.symbol in self.positions or len(self.positions) >= cfg.max_open or (self.balance <= 0 and not self.unlimited):
            return None
        if self.reject_reason(sig, price) is not None:
            return None
        base = self.balance if cfg.compound else cfg.start_balance
        d = 1 if sig.side == "LONG" else -1
        entry = price * (1 + d * cfg.slippage_pct)
        trail_start = trail_dist = 0.0
        if cfg.exit_mode == "atr":
            atr_abs = sig.atr_pct * (sig.price or price)
            sl_dist = cfg.sl_atr * atr_abs
            sl_frac = sl_dist / entry
            if sl_frac <= 0 or sl_frac * cfg.leverage > 0.8:      # liquidation stop se pehle aa jayegi
                return None
            if cfg.sizing_mode == "margin":                          # equity ka margin_pct% margin, stop kitna bhi door ho
                notional = base * cfg.margin_pct * cfg.leverage
            else:
                notional = min(base * cfg.risk_pct / sl_frac, base * cfg.margin_pct * cfg.leverage)
            margin = notional / cfg.leverage
            qty = notional / entry
            sl = entry - d * sl_dist
            tp = entry + d * cfg.tp_atr * atr_abs if cfg.tp_atr > 0 else None
            risk = qty * sl_dist
            if cfg.trail_atr > 0:
                trail_start, trail_dist = cfg.trail_start_atr * atr_abs, cfg.trail_atr * atr_abs
        else:
            margin = base * cfg.margin_pct
            notional = margin * cfg.leverage
            qty = notional / entry
            tp = entry * (1 + d * cfg.tp_roi / cfg.leverage)
            sl = entry * (1 - d * cfg.sl_roi / cfg.leverage)
            risk = margin * cfg.sl_roi
        if margin <= 0 or (margin > self.free_margin() and not self.unlimited):
            return None
        fee = notional * cfg.fee_rate
        self.balance -= fee
        pos = Position(
            sig.symbol, sig.side, entry, qty, margin, cfg.leverage, tp=tp, sl=sl,
            opened_ts=ts, max_hold_ms=int(cfg.max_hold_hours * 3_600_000), entry_fee=fee,
            score=sig.score, gates=list(sig.gates), vol_ratio=sig.vol_ratio, atr_pct=sig.atr_pct,
            trail_start=trail_start, trail_dist=trail_dist, best=entry, risk=risk, notified_sl=sl, liq=self.liq_price(entry, d),
        )
        self.positions[sig.symbol] = pos
        return pos

    def check_exit(self, pos: Position, hi: float, lo: float, last: float, ts: int,
                   live: bool = False) -> tuple[str, float] | None:
        """SL pehle check hota hai (conservative: ek candle mein dono touch hon to SL maana jata hai).
        Trailing stop agli candle se lagu hota hai (isi candle ki high/low se nahi)."""
        s = self.cfg.slippage_pct
        d = pos.d
        if (d == 1 and lo <= pos.sl) or (d == -1 and hi >= pos.sl):
            px = pos.sl * (1 - d * s)
            if live and ((d == 1 and last < px) or (d == -1 and last > px)):
                px = last              # gap: stop se bhi bura price
            trailed = (d == 1 and pos.sl > pos.entry) or (d == -1 and pos.sl < pos.entry)
            return ("TRAIL" if trailed else "SL"), px
        if pos.tp is not None and ((d == 1 and hi >= pos.tp) or (d == -1 and lo <= pos.tp)):
            return "TP", pos.tp
        if ts - pos.opened_ts >= pos.max_hold_ms:
            return "TIMEOUT", last * (1 - d * s)
        if pos.trail_dist > 0:                                   # ratchet: stop sirf favourable disha mein khiske
            if d == 1:
                pos.best = max(pos.best, hi)
                if pos.best - pos.entry >= pos.trail_start:
                    pos.sl = max(pos.sl, pos.best - pos.trail_dist)
            else:
                pos.best = min(pos.best, lo)
                if pos.entry - pos.best >= pos.trail_start:
                    pos.sl = min(pos.sl, pos.best + pos.trail_dist)
        return None

    def close(self, pos: Position, reason: str, px: float, ts: int) -> dict:
        exit_fee = pos.qty * px * self.cfg.fee_rate
        gross = pos.d * (px - pos.entry) * pos.qty
        self.balance += gross - exit_fee
        net = gross - exit_fee - pos.entry_fee      # entry fee pehle hi balance se kat chuki hai
        del self.positions[pos.symbol]
        self.cooldown_until[pos.symbol] = ts + self.cfg.cooldown_candles * self.cfg.tf_ms
        return {
            "closed_ts": ts, "symbol": pos.symbol, "side": pos.side, "entry": pos.entry, "exit": px,
            "fees": pos.entry_fee + exit_fee,
            "reason": reason, "roi": net / pos.margin, "pnl": net, "r": net / pos.risk if pos.risk else 0.0,
            "held_min": (ts - pos.opened_ts) / 60_000, "score": pos.score,
            "gates": "|".join(pos.gates), "vol_ratio": pos.vol_ratio, "atr_pct": pos.atr_pct,
        }

    # persistence
    def to_dict(self) -> dict:
        return {"balance": self.balance, "positions": [asdict(p) for p in self.positions.values()],
                "cooldown_until": self.cooldown_until}

    @classmethod
    def from_dict(cls, cfg: ScalpConfig, d: dict) -> "PaperAccount":
        a = cls(cfg, d["balance"])
        a.positions = {p["symbol"]: Position(**p) for p in d["positions"]}
        a.cooldown_until = d.get("cooldown_until", {})
        return a
