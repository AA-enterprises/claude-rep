"""Paper broker: fake balance par trades simulate karta hai. Real paisa kabhi nahi chhuta."""
from __future__ import annotations


class PaperBroker:
    def __init__(self, quote: float, fee_rate: float = 0.001):
        self.quote = quote        # USDT balance
        self.base = 0.0           # coin balance (BTC etc.)
        self.fee_rate = fee_rate

    def buy(self, price: float, qty: float) -> bool:
        cost = price * qty * (1 + self.fee_rate)
        if cost > self.quote + 1e-9:
            return False          # paisa kam hai, order skip
        self.quote -= cost
        self.base += qty
        return True

    def sell(self, price: float, qty: float) -> bool:
        if qty > self.base + 1e-12:
            return False
        self.base -= qty
        self.quote += price * qty * (1 - self.fee_rate)
        return True

    def equity(self, price: float) -> float:
        return self.quote + self.base * price
