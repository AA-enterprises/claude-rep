"""Scalp bot settings. Saare percentages fraction mein (0.70 = 70%)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields


@dataclass
class ScalpConfig:
    timeframe: str = "15m"
    leverage: float = 10.0
    tp_roi: float = 0.70          # margin par +70% -> profit book
    sl_roi: float = 0.20          # margin par -20% -> stop loss
    margin_pct: float = 0.05      # har trade mein balance ka 5% margin
    max_open: int = 5
    max_new_per_scan: int = 2
    min_gates: int = 3            # 4 mein se kam se kam itne gates agree karein
    min_quote_volume: float = 20_000_000   # 24h volume (USDT) se kam wale coins skip
    min_atr_pct: float = 0.004    # candle ATR/price: itni volatility ho tabhi TP reach ho sakta hai
    max_hold_hours: float = 6.0
    cooldown_candles: int = 4     # trade band hone ke baad us coin par itni candles wait
    max_daily_loss_pct: float = 0.05  # din ka loss itna ho to naye trades band
    fee_rate: float = 0.0005      # Binance futures taker 0.05% per side (notional par)
    slippage_pct: float = 0.0002
    start_balance: float = 10_000.0
    poll_seconds: float = 10.0

    @property
    def tf_ms(self) -> int:
        n, unit = int(self.timeframe[:-1]), self.timeframe[-1]
        return n * {"m": 60_000, "h": 3_600_000}[unit]

    def validate(self) -> None:
        if self.leverage < 1:
            raise ValueError("leverage >= 1")
        if not 0 < self.sl_roi < 1:
            raise ValueError("sl_roi 0 aur 1 ke beech (liquidation se pehle stop)")
        if self.tp_roi <= 0:
            raise ValueError("tp_roi > 0")
        if self.margin_pct * self.max_open > 1:
            raise ValueError("margin_pct x max_open 100% se zyada hai")


def load(path: str | None) -> ScalpConfig:
    cfg = ScalpConfig()
    if path and os.path.exists(path):
        raw = json.load(open(path))
        known = {f.name for f in fields(ScalpConfig)}
        bad = set(raw) - known
        if bad:
            raise ValueError(f"Unknown config keys: {sorted(bad)}")
        cfg = ScalpConfig(**raw)
    cfg.validate()
    return cfg
