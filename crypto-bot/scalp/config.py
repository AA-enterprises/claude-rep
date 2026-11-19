"""Scalp bot settings. Saare percentages fraction mein (0.70 = 70%)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields


def normalize_symbols(items) -> list[str]:
    """['btc', 'ETH', 'SOL/USDT:USDT'] -> ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']; 'BTC,ETH' string bhi chalegi."""
    if isinstance(items, str):
        items = items.replace(";", ",").replace(" ", ",").split(",")
    out = []
    for x in items or []:
        x = x.strip().upper()
        if not x:
            continue
        x = x if "/" in x else f"{x}/USDT:USDT"
        if not x.endswith(":USDT"):
            x = f"{x.split(':')[0]}:USDT" if x.endswith("/USDT") else x
        if x not in out:
            out.append(x)
    return out


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
    symbols: list[str] = field(default_factory=list)   # khali = top max_coins; warna sirf yahi coins (BTC, ETH ya BTC/USDT:USDT)
    max_coins: int = 30           # volume ke hisaab se top N coins (backtest 30 coins par validate hua). 0 = sab
    min_quote_volume: float = 20_000_000   # 24h volume (USDT) se kam wale coins skip
    min_atr_pct: float = 0.004    # candle ATR/price: itni volatility ho tabhi TP reach ho sakta hai
    min_vol_ratio: float = 0.0    # signal candle ka volume average se itne guna ho tabhi trade (0 = band). 1H bot: bade volume spike wali trades hi
    discord_commands: bool = False   # True: ye bot Discord slash command (/positions) bhi chalaye (DISCORD_BOT_TOKEN chahiye). Sirf EK bot par True rakho
    max_hold_hours: float = 6.0
    cooldown_candles: int = 4     # trade band hone ke baad us coin par itni candles wait
    max_daily_loss_pct: float = 0.05  # din ka loss itna ho to naye trades band
    fee_rate: float = 0.0005      # Binance futures taker 0.05% per side (notional par)
    slippage_pct: float = 0.0002
    start_balance: float = 10_000.0
    poll_seconds: float = 10.0
    fetch_workers: int = 5        # candles parallel mein itne coins ek saath mangta hai
    report_hours: float = 12.0    # Telegram par itne ghante mein ek report (0 = band)
    report_daily_at: str = ""      # "08:00": roz is time (Pakistan) par 24h report; khali = report_hours wala
    report_tz_hours: float = 5.0  # Pakistan = UTC+5
    # --- ATR exit mode (default): stop/target har coin ki volatility ke hisaab se ---
    risk_boost_4: float = 1.0     # sab 4 gates mile to risk_pct ko itne se guna karo (1 = barabar). Achhe signal par badi position
    lock_fees: bool = False       # True: trailing shuru hote hi stop kam se kam entry + fees (fees ke baad loss na ho)
    notify_trades: bool = True    # False: har trade open/close ka alert nahi (bahut trades wale bot ke liye), sirf report
    label: str = ""               # alert messages mein bot ka naam (jaise "FREQ"), do bot alag pehchanne ke liye
    entry_mode: str = "close"     # "close": band hui candle par (validate hua) | "intrabar": har 15 min adhoori candle dekh kar foran entry
    exit_mode: str = "atr"        # "atr" | "roi" (purana 70%/-20% ROI rule)
    sl_atr: float = 1.5           # stop = entry se 1.5 x ATR door
    tp_atr: float = 3.0           # target = 3 x ATR (risk:reward 1:2). 0 = koi fixed target nahi
    trail_start_atr: float = 1.5  # itna profit hone par trailing shuru
    trail_atr: float = 1.5        # stop best price se itni ATR peeche. 0 = trailing band
    min_liq_distance: float = 0.0  # liquidation price entry se kam se kam itni door ho (0.30 = 30%), warna trade nahi
    maint_margin_rate: float = 0.005  # liquidation price ke andaze ke liye (Binance mein tier ke hisaab se alag)
    max_atr_pct: float = 0.0      # ATR (candle) price ke is % se zyada ho to coin skip (0 = band). Bahut volatile coins
    sizing_mode: str = "risk"     # "risk": stop lagne par risk_pct loss | "margin": har trade mein margin_pct (equity ka %) margin lagao
    risk_pct: float = 0.01        # har trade mein start balance ka 1% risk (stop lagne par itna loss)
    compound: bool = False        # False: size start_balance se (backtest fair rahe), True: current balance se
    sides: str = "both"           # "both" | "long" | "short"
    btc_filter: bool = False      # True: BTC trend ke saath hi trade (up -> long, down -> short)

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
        if any(not x.endswith('/USDT:USDT') for x in self.symbols):
            raise ValueError("symbols: BTC jaisa naam ya BTC/USDT:USDT")
        if self.report_daily_at:
            from .schedule import parse_hhmm
            parse_hhmm(self.report_daily_at)
        if self.report_hours < 0:
            raise ValueError("report_hours >= 0")
        if not 0 <= self.min_liq_distance < 1 or self.max_atr_pct < 0:
            raise ValueError("min_liq_distance 0..1, max_atr_pct >= 0")
        if not 0 < self.risk_boost_4 <= 5:
            raise ValueError("risk_boost_4 0..5")
        if self.sizing_mode not in ("risk", "margin"):
            raise ValueError("sizing_mode: risk/margin")
        if self.entry_mode not in ("close", "intrabar"):
            raise ValueError("entry_mode: close/intrabar")
        if self.exit_mode not in ("atr", "roi"):
            raise ValueError("exit_mode: atr/roi")
        if self.exit_mode == "atr" and (self.sl_atr <= 0 or self.tp_atr < 0 or self.trail_atr < 0 or not 0 < self.risk_pct <= 0.05):
            raise ValueError("atr settings galat: sl_atr>0, tp_atr>=0, trail_atr>=0, 0<risk_pct<=0.05")
        if self.sides not in ("both", "long", "short"):
            raise ValueError("sides: both/long/short")
        if self.min_atr_pct < 0.002:
            raise ValueError("min_atr_pct >= 0.002")
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
        raw["symbols"] = normalize_symbols(raw.get("symbols", []))
        cfg = ScalpConfig(**raw)
    cfg.validate()
    return cfg
