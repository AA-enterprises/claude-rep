"""Find Trades: bot ke apne rules (config) se abhi ke candidates dhundho. Sirf padhta hai, koi trade nahi kholta."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from .config import ScalpConfig
from .features import MIN_CANDLES
from .scanner import fetch_closed, universe
from .signals import evaluate

VALID_MS = 3_600_000          # candidate itni der (1 ghanta) tak lene layak maana jata hai


def max_safe_leverage(cfg: ScalpConfig, sl_frac: float) -> int:
    """Sabse zyada leverage jis par liquidation stop se kaafi door rahe (stop x1.25 + maintenance margin)."""
    if sl_frac <= 0:
        return 1
    return int(max(1, min(20, 1 / (1.25 * sl_frac + cfg.maint_margin_rate))))


def describe_signal(sig, cfg: ScalpConfig, kind: str, now_ms: int, open_symbols: set[str]) -> dict:
    d = 1 if sig.side == "LONG" else -1
    atr_abs = sig.atr_pct * sig.price
    sl_dist = cfg.sl_atr * atr_abs
    sl_frac = sl_dist / sig.price
    return {
        "symbol": sig.symbol, "side": sig.side, "kind": kind, "score": sig.score, "need": cfg.min_gates,
        "gates": [g for g in sig.gates if not g.startswith("INTRABAR")], "price": sig.price,
        "atr_pct": sig.atr_pct, "vol_ratio": sig.vol_ratio,
        "sl_price": sig.price - d * sl_dist, "sl_pct": sl_frac,
        "suggested_leverage": min(int(cfg.leverage), max_safe_leverage(cfg, sl_frac)),
        "max_safe_leverage": max_safe_leverage(cfg, sl_frac),
        "found_ms": now_ms, "valid_until_ms": now_ms + VALID_MS, "already_open": sig.symbol in open_symbols,
    }


def find(ex, cfg: ScalpConfig, open_symbols: set[str] | None = None, include_weak: bool = True) -> dict:
    """{'found_ms', 'items': [...]}. 'signal' = bot ki puri shart poori; 'weak' = ek gate kam (haath se lena apni marzi)."""
    open_symbols = open_symbols or set()
    syms, _ = universe(ex, cfg)
    intrabar = cfg.entry_mode == "intrabar"
    tf = cfg.tf_ms

    def work(sym: str):
        try:
            cs = fetch_closed(ex, sym, cfg)
            if intrabar and cs:
                now = ex.milliseconds()
                f = next((tuple(r[:6]) for r in ex.fetch_ohlcv(sym, cfg.timeframe, since=cs[-1][0] + tf, limit=5)
                          if r[0] + tf > now), None)
                if f:
                    cs = cs + [f]
            return sym, cs
        except Exception:  # noqa: BLE001
            return sym, []

    with ThreadPoolExecutor(max_workers=max(1, cfg.fetch_workers)) as pool:
        rows = list(pool.map(work, syms))
    weak_cfg = replace(cfg, min_gates=max(1, cfg.min_gates - 1))
    now_ms = ex.milliseconds()
    items = []
    for sym, cs in rows:
        if len(cs) < MIN_CANDLES:
            continue
        s = evaluate(sym, cs, cfg, None)
        if s:
            items.append(describe_signal(s, cfg, "signal", now_ms, open_symbols))
        elif include_weak:
            w = evaluate(sym, cs, weak_cfg, None)
            if w and w.score < cfg.min_gates:
                items.append(describe_signal(w, cfg, "weak", now_ms, open_symbols))
    items.sort(key=lambda x: (x["kind"] != "signal", -x["score"], -x["vol_ratio"]))
    return {"found_ms": now_ms, "items": items, "scanned": len(syms)}
