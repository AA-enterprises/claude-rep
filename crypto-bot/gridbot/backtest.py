"""Backtest: historical candles par grid strategy chalao."""
from __future__ import annotations

from dataclasses import dataclass

from .broker import PaperBroker
from .data import Candle
from .strategy import GridConfig, GridStrategy, Trade


@dataclass
class Result:
    start_equity: float
    end_equity: float
    trades: list[Trade]
    max_drawdown: float
    buy_hold_return: float
    halted: bool

    @property
    def return_pct(self) -> float:
        return self.end_equity / self.start_equity - 1

    @property
    def completed_cycles(self) -> int:
        return sum(1 for t in self.trades if t.side == "sell" and t.pnl > 0)

    def summary(self) -> str:
        sells = [t for t in self.trades if t.side == "sell"]
        return "\n".join([
            f"Start equity     : {self.start_equity:,.2f} USDT",
            f"End equity       : {self.end_equity:,.2f} USDT",
            f"Strategy return  : {self.return_pct:+.2%}",
            f"Buy & hold return: {self.buy_hold_return:+.2%}",
            f"Max drawdown     : {self.max_drawdown:.2%}",
            f"Trades           : {len(self.trades)} ({len(sells)} sells, {self.completed_cycles} profitable)",
            f"Realised PnL     : {sum(t.pnl for t in sells):+,.2f} USDT",
            f"Stop-loss hit    : {'YES' if self.halted else 'no'}",
        ])


def _path(c: Candle) -> list[float]:
    """Candle ke andar price ka assumed raasta (conservative, intrabar order unknown)."""
    _, o, h, l, cl = c
    return [o, l, h, cl] if cl >= o else [o, h, l, cl]


def run(candles: list[Candle], cfg: GridConfig) -> Result:
    broker = PaperBroker(cfg.investment, cfg.fee_rate)
    strat = GridStrategy(cfg)
    trades: list[Trade] = []
    peak, max_dd = cfg.investment, 0.0
    for c in candles:
        for p in _path(c):
            trades += strat.on_price(c[0], p, broker)
        eq = broker.equity(c[4])
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)
    last = candles[-1][4]
    return Result(cfg.investment, broker.equity(last), trades, max_dd,
                  last / candles[0][1] - 1, strat.halted)
