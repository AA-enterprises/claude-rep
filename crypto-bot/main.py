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


def cmd_scalp_backtest(args) -> int:
    from dataclasses import replace
    from scalp import backtest as sb, config as sc, scanner, sim
    cfg = sc.load(args.scalp_config)
    if args.timeframe:
        cfg = replace(cfg, timeframe=args.timeframe)
        print(f"Timeframe: {cfg.timeframe} (15m cache se resample)")
    if args.source == "cache":
        from scalp import history
        series = history.load_resampled(args.cache_dir, cfg, args.coins)
        if not series:
            print("Cache khali hai. Pehle: python main.py scalp-download")
            return 1
        print(f"{len(series)} coins cache se load hue")
        data_ = sb.Dataset(series, cfg.tf_ms)
    elif args.source == "binance":
        ex = scanner.make_exchange()
        syms, _ = scanner.universe(ex, cfg, limit=0)
        syms = syms[: args.coins]
        print(f"{len(syms)} coins ka data le raha hoon...")
        data_ = {s: scanner.fetch_closed(ex, s, cfg, limit=1000) for s in syms}
    else:
        data_ = sim.market(cfg, coins=args.coins, n=args.limit)
        print("SYNTHETIC data: sirf engine check, asli profit ka sabut nahi")
    print(sb.run(data_, cfg).summary())
    return 0


def cmd_scalp_download(args) -> int:
    from scalp import config as sc, history, scanner
    cfg = sc.load(args.scalp_config)
    ex = scanner.make_exchange()
    syms, _ = scanner.universe(ex, cfg, limit=0)
    syms = ["BTC/USDT:USDT"] + [x for x in syms if not x.startswith("BTC/")][: args.coins - 1]
    print(f"{len(syms)} coins, {args.years} saal tak (jitna Binance par available ho). Beech mein ruk sakte ho, dobara chalane par wahin se aage badhega.")
    for sym in syms:
        history.download(ex, sym, cfg.timeframe, cfg.tf_ms, args.years, args.cache_dir)
    return 0


def cmd_scalp_sweep(args) -> int:
    from dataclasses import replace
    from scalp import backtest as sb, config as sc, history, sim, sweep
    cfg = sc.load(args.scalp_config)
    if args.timeframe:
        cfg = replace(cfg, timeframe=args.timeframe)
        print(f"Timeframe: {cfg.timeframe} (15m cache se resample)")
    if args.source == "synthetic":
        ds = sb.Dataset.from_candles(sim.market(cfg, coins=args.coins, n=args.limit), cfg.tf_ms)
    else:
        series = history.load_resampled(args.cache_dir, cfg, args.coins)
        if not series:
            print("Cache khali hai. Pehle: python main.py scalp-download")
            return 1
        ds = sb.Dataset(series, cfg.tf_ms)
    from dataclasses import replace
    grid, over = sweep.grid_for(args.mode, args.quick, slow=cfg.timeframe != "15m")
    rows = sweep.sweep(ds, replace(cfg, **over), grid, out_csv=args.out)
    print(sweep.report(rows))
    return 0


def cmd_scalp_dashboard(args) -> int:
    from scalp import dashboard
    dashboard.serve(args.state, args.trades, args.port, not args.no_browser)
    return 0


def cmd_scalp_validate(args) -> int:
    from dataclasses import replace
    from scalp import backtest as sb, config as sc, history, validate
    cfg = sc.load(args.scalp_config)
    # default: sweep ka sabse achha 4h candidate
    cand = {"timeframe": "4h", "sl_atr": 2.0, "tp_atr": 0.0, "trail_atr": 2.5, "min_gates": 3, "max_hold_hours": 48.0, "btc_filter": False}
    cand.update(validate.parse_overrides(args.set))
    cfg = replace(cfg, **cand)
    cfg.validate()
    print("Config:", {k: getattr(cfg, k) for k in cand})
    series = history.load_resampled(args.cache_dir, cfg, args.coins)
    if not series:
        print("Cache khali hai. Pehle: python main.py scalp-download")
        return 1
    print(f"{len(series)} coins, timeframe {cfg.timeframe}")
    validate.validate(sb.Dataset(series, cfg.tf_ms), cfg)
    return 0


def cmd_scalp_paper(args) -> int:
    from scalp import config as sc, scanner
    cfg = sc.load(args.scalp_config)
    scanner.Bot(cfg, args.state, args.trades, TelegramNotifier()).run()
    return 0


def cmd_scalp_stats(args) -> int:
    import csv
    rows = list(csv.DictReader(open(args.trades)))
    if not rows:
        print("Abhi koi closed trade nahi")
        return 0
    for key in ("reason", "side", "score"):
        print(f"-- by {key}")
        for v in sorted({r[key] for r in rows}):
            g = [r for r in rows if r[key] == v]
            w = sum(float(r["pnl"]) > 0 for r in g)
            print(f"  {v:8} n={len(g):3} win={w / len(g):.0%} avg_roi={sum(float(r['roi']) for r in g) / len(g):+.1%} pnl={sum(float(r['pnl']) for r in g):+,.2f}")
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
    p.add_argument("--scalp-config", default="scalp_config.json")
    sb_ = sub.add_parser("scalp-backtest")
    sb_.add_argument("--source", choices=["synthetic", "binance", "cache"], default="synthetic")
    sb_.add_argument("--cache-dir", default="data_cache")
    sb_.add_argument("--timeframe", choices=["15m", "1h", "4h"], help="cache 15m se resample hota hai")
    sb_.add_argument("--coins", type=int, default=20)
    sb_.add_argument("--limit", type=int, default=700)
    sb_.set_defaults(fn=cmd_scalp_backtest)
    sd_ = sub.add_parser("scalp-download")
    sd_.add_argument("--coins", type=int, default=30)
    sd_.add_argument("--years", type=float, default=10)
    sd_.add_argument("--cache-dir", default="data_cache")
    sd_.set_defaults(fn=cmd_scalp_download)
    sw_ = sub.add_parser("scalp-sweep")
    sw_.add_argument("--source", choices=["synthetic", "cache"], default="cache")
    sw_.add_argument("--cache-dir", default="data_cache")
    sw_.add_argument("--coins", type=int, default=30)
    sw_.add_argument("--limit", type=int, default=3000)
    sw_.add_argument("--quick", action="store_true")
    sw_.add_argument("--timeframe", choices=["15m", "1h", "4h"], help="cache 15m se resample hota hai")
    sw_.add_argument("--mode", choices=["atr", "roi"], default="atr", help="atr: ATR stop/target + trailing, roi: purana 70/-20 rule")
    sw_.add_argument("--out", default="sweep_results.csv")
    sw_.set_defaults(fn=cmd_scalp_sweep)
    dd_ = sub.add_parser("scalp-dashboard")
    dd_.add_argument("--state", default="scalp_state.json")
    dd_.add_argument("--trades", default="scalp_trades.csv")
    dd_.add_argument("--port", type=int, default=8050)
    dd_.add_argument("--no-browser", action="store_true")
    dd_.set_defaults(fn=cmd_scalp_dashboard)
    sv_ = sub.add_parser("scalp-validate")
    sv_.add_argument("--cache-dir", default="data_cache")
    sv_.add_argument("--coins", type=int, default=30)
    sv_.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="config override, jaise --set sl_atr=2.5 (kayi baar de sakte ho)")
    sv_.set_defaults(fn=cmd_scalp_validate)
    sp_ = sub.add_parser("scalp-paper")
    sp_.add_argument("--state", default="scalp_state.json")
    sp_.add_argument("--trades", default="scalp_trades.csv")
    sp_.set_defaults(fn=cmd_scalp_paper)
    ss_ = sub.add_parser("scalp-stats")
    ss_.add_argument("--trades", default="scalp_trades.csv")
    ss_.set_defaults(fn=cmd_scalp_stats)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
