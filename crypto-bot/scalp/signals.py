"""Signal decision: features -> LONG/SHORT. Backtest aur live dono yahi use karte hain."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import ScalpConfig
from .features import MIN_CANDLES, Feat, compute

LONG_GATES = ["trend (EMA20>EMA50, price>EMA200)", "momentum (RSI 50-75, MACD rising)",
              "breakout (20-bar high)", "volume spike (>1.5x)"]
SHORT_GATES = ["trend (EMA20<EMA50, price<EMA200)", "momentum (RSI 25-50, MACD falling)",
               "breakdown (20-bar low)", "volume spike (>1.5x)"]
LIVE_CANDLES = 499      # Binance weight 2 (500 se kam); EMA200 ke liye kaafi


@dataclass
class Signal:
    symbol: str
    side: str            # "LONG" | "SHORT"
    score: int
    gates: list[str] = field(default_factory=list)
    vol_ratio: float = 0.0
    atr_pct: float = 0.0
    price: float = 0.0


def decide(symbol: str, f: Feat, cfg: ScalpConfig, regime: int | None = None) -> Signal | None:
    if f.atr_pct < cfg.min_atr_pct or max(f.ls, f.ss) < cfg.min_gates or f.ls == f.ss:
        return None
    if cfg.min_vol_ratio and f.vol_ratio < cfg.min_vol_ratio:
        return None
    side = "LONG" if f.ls > f.ss else "SHORT"
    if cfg.sides != "both" and cfg.sides.upper() != side:
        return None
    if cfg.btc_filter and regime:                    # BTC up -> sirf LONG, BTC down -> sirf SHORT
        if (side == "LONG" and regime < 0) or (side == "SHORT" and regime > 0):
            return None
    mask, names = (f.lmask, LONG_GATES) if side == "LONG" else (f.smask, SHORT_GATES)
    return Signal(symbol, side, f.ls if side == "LONG" else f.ss,
                  [n for n, ok in zip(names, mask) if ok], f.vol_ratio, f.atr_pct, f.price)


def evaluate(symbol: str, candles: list[tuple], cfg: ScalpConfig, regime: int | None = None) -> Signal | None:
    """candles: (ts, o, h, l, c, v), sirf closed candles. Aakhri candle par signal."""
    if len(candles) < MIN_CANDLES:
        return None
    w = candles[-LIVE_CANDLES:]
    f = compute([x[2] for x in w], [x[3] for x in w], [x[4] for x in w], [x[5] for x in w]).get(len(w) - 1)
    return decide(symbol, f, cfg, regime) if f else None
