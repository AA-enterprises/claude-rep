"""Grid trading strategy.

Price range [lower, upper] ko `grids` equal parts mein baanta jata hai.
Har level i par: price level i tak gire -> BUY, aur level i+1 tak chadhe -> SELL.
Har buy-sell pair ka profit = grid spacing - fees.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GridConfig:
    lower: float
    upper: float
    grids: int = 20
    investment: float = 1000.0      # quote currency (USDT) total capital
    fee_rate: float = 0.001         # 0.1% per trade (Binance spot default)
    stop_loss_pct: float | None = 0.10  # lower se itna neeche gaya to sab bech ke bot band

    def validate(self) -> None:
        if not (0 < self.lower < self.upper):
            raise ValueError("0 < lower < upper hona chahiye")
        if self.grids < 2:
            raise ValueError("grids >= 2 hona chahiye")
        if self.investment <= 0:
            raise ValueError("investment > 0 hona chahiye")
        min_spacing_pct = (self.upper - self.lower) / self.grids / self.lower
        if min_spacing_pct <= 2 * self.fee_rate:
            raise ValueError(
                f"Grid spacing ({min_spacing_pct:.4%}) fees (2x{self.fee_rate:.4%}) se kam hai: "
                "har trade loss mein jayega. grids kam karo ya range badi karo."
            )


@dataclass
class Trade:
    ts: int
    side: str       # "buy" | "sell"
    price: float
    qty: float
    fee: float
    pnl: float = 0.0   # sirf sell par: realised profit (fees ke baad)
    entry: float = 0.0  # sirf sell par: jis price par kharida tha
    reason: str = ""    # "target" | "stop-loss"


@dataclass
class GridStrategy:
    cfg: GridConfig
    levels: list[float] = field(init=False)
    # level index -> qty jo us level par kharidi gayi (aur level+1 par bechni hai)
    holdings: dict[int, float] = field(default_factory=dict)
    buy_cost: dict[int, float] = field(default_factory=dict)
    halted: bool = False

    def __post_init__(self) -> None:
        self.cfg.validate()
        step = (self.cfg.upper - self.cfg.lower) / self.cfg.grids
        self.levels = [self.cfg.lower + i * step for i in range(self.cfg.grids + 1)]
        self.quote_per_grid = self.cfg.investment / self.cfg.grids

    def on_price(self, ts: int, price: float, broker) -> list[Trade]:
        """Ek price tick par jo bhi orders banne chahiye unhe broker par execute karo."""
        trades: list[Trade] = []
        if self.halted:
            return trades

        # Stop-loss
        sl = self.cfg.stop_loss_pct
        if sl is not None and price < self.cfg.lower * (1 - sl):
            for i in sorted(self.holdings):
                trades.append(self._sell(ts, i, price, broker, "stop-loss"))
            self.holdings.clear()
            self.halted = True
            return trades

        # SELL: jis level ka upar wala level price ne chhu liya
        for i in [i for i in sorted(self.holdings) if price >= self.levels[i + 1]]:
            trades.append(self._sell(ts, i, self.levels[i + 1], broker))
            del self.holdings[i]

        # BUY: jis level se price neeche aa gaya aur wahan abhi position nahi
        for i in range(self.cfg.grids):
            lvl = self.levels[i]
            if price <= lvl and i not in self.holdings and self.levels[i + 1] > price:
                qty = self.quote_per_grid / lvl
                if broker.buy(lvl, qty):
                    fee = lvl * qty * self.cfg.fee_rate
                    self.holdings[i] = qty
                    self.buy_cost[i] = lvl * qty + fee
                    trades.append(Trade(ts, "buy", lvl, qty, fee))
        return trades

    def _sell(self, ts: int, i: int, price: float, broker, reason: str = "target") -> Trade:
        qty = self.holdings[i]
        broker.sell(price, qty)
        fee = price * qty * self.cfg.fee_rate
        pnl = price * qty - fee - self.buy_cost.pop(i)
        return Trade(ts, "sell", price, qty, fee, pnl, entry=self.levels[i], reason=reason)
