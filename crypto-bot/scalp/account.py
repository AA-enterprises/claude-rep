"""Paper futures account: leverage, fees, slippage, TP/SL/timeout."""
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
    tp: float
    sl: float
    opened_ts: int
    max_hold_ms: int
    entry_fee: float
    score: int = 0
    gates: list[str] = field(default_factory=list)
    vol_ratio: float = 0.0
    atr_pct: float = 0.0

    @property
    def d(self) -> int:
        return 1 if self.side == "LONG" else -1

    def unrealized(self, price: float) -> float:
        return self.d * (price - self.entry) * self.qty


class PaperAccount:
    def __init__(self, cfg: ScalpConfig, balance: float | None = None):
        self.cfg = cfg
        self.balance = cfg.start_balance if balance is None else balance
        self.positions: dict[str, Position] = {}
        self.cooldown_until: dict[str, int] = {}

    def free_margin(self) -> float:
        return self.balance - sum(p.margin for p in self.positions.values())

    def equity(self, prices: dict[str, float]) -> float:
        return self.balance + sum(p.unrealized(prices.get(s, p.entry)) for s, p in self.positions.items())

    def open(self, sig: Signal, price: float, ts: int) -> Position | None:
        cfg = self.cfg
        if sig.symbol in self.positions or len(self.positions) >= cfg.max_open:
            return None
        margin = self.balance * cfg.margin_pct
        if margin <= 0 or margin > self.free_margin():
            return None
        d = 1 if sig.side == "LONG" else -1
        entry = price * (1 + d * cfg.slippage_pct)
        notional = margin * cfg.leverage
        fee = notional * cfg.fee_rate
        self.balance -= fee
        pos = Position(
            sig.symbol, sig.side, entry, notional / entry, margin, cfg.leverage,
            tp=entry * (1 + d * cfg.tp_roi / cfg.leverage),
            sl=entry * (1 - d * cfg.sl_roi / cfg.leverage),
            opened_ts=ts, max_hold_ms=int(cfg.max_hold_hours * 3_600_000), entry_fee=fee,
            score=sig.score, gates=list(sig.gates), vol_ratio=sig.vol_ratio, atr_pct=sig.atr_pct,
        )
        self.positions[sig.symbol] = pos
        return pos

    def check_exit(self, pos: Position, hi: float, lo: float, last: float, ts: int,
                   live: bool = False) -> tuple[str, float] | None:
        """SL pehle check hota hai (conservative: ek candle mein dono touch hon to SL maana jata hai)."""
        s = self.cfg.slippage_pct
        d = pos.d
        if (d == 1 and lo <= pos.sl) or (d == -1 and hi >= pos.sl):
            px = pos.sl * (1 - d * s)
            if live and ((d == 1 and last < px) or (d == -1 and last > px)):
                px = last              # gap: stop se bhi bura price
            return "SL", px
        if (d == 1 and hi >= pos.tp) or (d == -1 and lo <= pos.tp):
            return "TP", pos.tp
        if ts - pos.opened_ts >= pos.max_hold_ms:
            return "TIMEOUT", last * (1 - d * s)
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
            "reason": reason, "roi": net / pos.margin, "pnl": net,
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
