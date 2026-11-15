"""Grid trading bot CLI.

  python main.py backtest --source synthetic
  python main.py backtest --source binance --symbol BTC/USDT --timeframe 1h --limit 1000
  python main.py backtest --source csv --csv data.csv
  python main.py paper    --symbol BTC/USDT      # live prices, fake money
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from gridbot import backtest, data
from gridbot.broker import PaperBroker
from gridbot.notify import TelegramNotifier, format_close, format_open
from gridbot.strategy import GridConfig, GridStrategy


def load_cfg(path: str, args) -> tuple[GridConfig, dict]:
    with open(path) as f:
        raw = json.load(f)
    g = raw["grid"]
    cfg = GridConfig(lower=g["lower"], upper=g["upper"], grids=g["grids"],
                     investment=g["investment"], fee_rate=g.get("fee_rate", 0.001),
                     stop_loss_pct=g.get("stop_loss_pct", 0.10))
    return cfg, raw


def cmd_backtest(args) -> int:
    cfg, raw = load_cfg(args.config, args)
    symbol = args.symbol or raw.get("symbol", "BTC/USDT")
    if args.source == "binance":
        candles = data.from_binance(symbol, args.timeframe, args.limit)
    elif args.source == "csv":
        candles = data.from_csv(args.csv)
    else:
        candles = data.synthetic(n=args.limit)
    if not candles:
        print("Koi candles nahi mile", file=sys.stderr)
        return 1
    lo, hi = min(c[3] for c in candles), max(c[2] for c in candles)
    print(f"{len(candles)} candles | data range {lo:,.0f} - {hi:,.0f} | grid {cfg.lower:,.0f} - {cfg.upper:,.0f}")
    print(backtest.run(candles, cfg).summary())
    return 0


def cmd_paper(args) -> int:
    import ccxt

    cfg, raw = load_cfg(args.config, args)
    symbol = args.symbol or raw.get("symbol", "BTC/USDT")
    ex = ccxt.binance({"enableRateLimit": True})
    broker, strat = PaperBroker(cfg.investment, cfg.fee_rate), GridStrategy(cfg)
    tg = TelegramNotifier()
    print(f"PAPER mode (fake money) | {symbol} | Telegram: {'ON' if tg.enabled else 'OFF (env vars set nahi)'} | Ctrl+C se band")
    tg.send(f"🤖 Grid bot started · {symbol} · Paper\nRange {cfg.lower:,.0f} - {cfg.upper:,.0f} · {cfg.grids} grids · {cfg.investment:,.0f} USDT")
    price = None
    try:
        while not strat.halted:
            price = ex.fetch_ticker(symbol)["last"]
            for t in strat.on_price(int(time.time() * 1000), price, broker):
                print(f"\n{time.strftime('%H:%M:%S')} {t.side.upper():4} {t.qty:.6f} @ {t.price:,.2f}"
                      + (f"  pnl {t.pnl:+.2f}" if t.side == "sell" else ""))
                if t.side == "buy":
                    tg.send(format_open(t, symbol, strat))
                else:
                    tg.send(format_close(t, symbol, broker.equity(price), cfg.investment))
            print(f"\r price {price:,.2f} | equity {broker.equity(price):,.2f}", end="", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    if price is not None:
        print(f"\nFinal equity: {broker.equity(price):,.2f} USDT")
        tg.send(f"⏹ Grid bot stopped · {symbol}\nFinal equity: {broker.equity(price):,.2f} USDT ({broker.equity(price) / cfg.investment - 1:+.2%})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Grid trading bot (backtest / paper)")
    p.add_argument("--config", default="config.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest")
    b.add_argument("--source", choices=["synthetic", "binance", "csv"], default="synthetic")
    b.add_argument("--symbol")
    b.add_argument("--timeframe", default="1h")
    b.add_argument("--limit", type=int, default=1000)
    b.add_argument("--csv")
    b.set_defaults(fn=cmd_backtest)
    pp = sub.add_parser("paper")
    pp.add_argument("--symbol")
    pp.add_argument("--interval", type=float, default=10.0, help="price poll seconds")
    pp.set_defaults(fn=cmd_paper)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
