"""Scalping research lab (sirf research, bot ka hissa nahi): 15m Binance futures data par signal families ka walk-forward test.
Har trade R-multiple mein (1R = stop distance), fees/slippage ke saath aur bina."""
import glob
import os
import sys
import time

import numpy as np
from numba import njit

# ---------------- indicators ----------------


@njit(cache=True)
def ema(x, n):
    a = 2.0 / (n + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


@njit(cache=True)
def atr_w(h, l, c, n=14):
    out = np.full(len(c), np.nan)
    tr = np.empty(len(c))
    tr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    a = 0.0
    for i in range(1, n + 1):
        a += tr[i]
    a /= n
    out[n] = a
    for i in range(n + 1, len(c)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


@njit(cache=True)
def rsi_w(c, n=14):
    out = np.full(len(c), np.nan)
    ag = 0.0
    al = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        ag += max(d, 0.0)
        al += max(-d, 0.0)
    ag /= n
    al /= n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


@njit(cache=True)
def sma_prior(x, n):
    out = np.full(len(x), np.nan)
    s = 0.0
    for i in range(len(x)):
        if i >= n:
            out[i] = s / n
        s += x[i]
        if i >= n:
            s -= x[i - n]
    return out


@njit(cache=True)
def vwap_daily(ts, h, l, c, v):
    out = np.empty(len(c))
    pv = 0.0
    vv = 0.0
    day = -1
    for i in range(len(c)):
        dday = ts[i] // 86_400_000
        if dday != day:
            day, pv, vv = dday, 0.0, 0.0
        pv += (h[i] + l[i] + c[i]) / 3.0 * v[i]
        vv += v[i]
        out[i] = pv / vv if vv > 0 else c[i]
    return out


@njit(cache=True)
def roll_max_prior(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        m = x[i - n]
        for j in range(i - n + 1, i):
            m = max(m, x[j])
        out[i] = m
    return out


@njit(cache=True)
def roll_min_prior(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        m = x[i - n]
        for j in range(i - n + 1, i):
            m = min(m, x[j])
        out[i] = m
    return out


# ---------------- simulation ----------------


@njit(cache=True)
def sim(sig, o, h, l, c, atr, s, t, T, mode, off, W, fee_t, fee_m, slip, out_i, out_rn, out_rg, out_k, rev):
    """mode 0: market entry bar-close par | mode 1: limit entry (c -+ off*ATR), W bars tak wait.
    Stop market (taker+slip), TP limit (maker), time-stop market. Ek candle mein stop aur TP dono touch ho to stop."""
    n = len(c)
    cnt = 0
    i = 60
    while i < n - T - W - 3:
        d = sig[i]
        if d == 0 or np.isnan(atr[i]):
            i += 1
            continue
        a = atr[i]
        if mode == 0:
            entry = c[i] * (1 + d * slip)
            fee_in = fee_t
            j0 = i
        else:
            lim = c[i] - d * off * a
            j0 = -1
            for j in range(i + 1, i + 1 + W):
                if (d == 1 and l[j] < lim) or (d == -1 and h[j] > lim):
                    j0 = j
                    break
            if j0 < 0:
                i += 1
                continue
            entry = lim
            fee_in = fee_m
        stop = entry - d * s * a
        tp = entry + d * t * a
        exit_p = np.nan
        fee_out = fee_t
        k = j0 + T
        if mode == 1 and ((d == 1 and l[j0] <= stop) or (d == -1 and h[j0] >= stop)):
            exit_p = stop * (1 - d * slip)
            k = j0
        else:
            for j in range(j0 + 1, j0 + T + 1):
                if d == 1:
                    if l[j] <= stop:
                        exit_p = stop * (1 - slip)
                        k = j
                        break
                    if t > 0 and h[j] >= tp:
                        exit_p = tp
                        fee_out = fee_m
                        k = j
                        break
                else:
                    if h[j] >= stop:
                        exit_p = stop * (1 + slip)
                        k = j
                        break
                    if t > 0 and l[j] <= tp:
                        exit_p = tp
                        fee_out = fee_m
                        k = j
                        break
                if rev != 0 and sig[j] == -d:                      # ulta signal aaya: market par band
                    exit_p = c[j] * (1 - d * slip)
                    k = j
                    break
        if np.isnan(exit_p):
            exit_p = c[j0 + T] * (1 - d * slip)
        gross = d * (exit_p - entry)
        cost = fee_in * entry + fee_out * exit_p
        out_i[cnt] = i
        out_rg[cnt] = gross / (s * a)
        out_rn[cnt] = (gross - cost) / (s * a)
        out_k[cnt] = k - i
        cnt += 1
        i = k + 1
    return cnt


@njit(cache=True)
def sim_partial(sig, o, h, l, c, atr, s, T, tp1_r, frac, fee_t, fee_m, slip, out_i, out_rn, out_k):
    """Market entry. tp1_r*R par `frac` position limit (maker) se band, baaki ka stop entry (break-even) par. Time-stop T bars.
    Ek candle mein stop aur TP1 dono touch ho to stop pehle."""
    n = len(c)
    cnt = 0
    i = 60
    while i < n - T - 3:
        d = sig[i]
        if d == 0 or np.isnan(atr[i]):
            i += 1
            continue
        a = atr[i]
        entry = c[i] * (1 + d * slip)
        sd = s * a
        stop = entry - d * sd
        tp1 = entry + d * tp1_r * sd
        reached = False
        k = i + T
        exit2 = np.nan
        fee2 = fee_t
        for j in range(i + 1, i + T + 1):
            if d == 1:
                if l[j] <= stop:
                    exit2 = stop * (1 - slip)
                    k = j
                    break
                if (not reached) and h[j] >= tp1:
                    reached = True
                    stop = entry                      # break-even
            else:
                if h[j] >= stop:
                    exit2 = stop * (1 + slip)
                    k = j
                    break
                if (not reached) and l[j] <= tp1:
                    reached = True
                    stop = entry
        if np.isnan(exit2):
            exit2 = c[i + T] * (1 - d * slip)
        if reached:
            g1 = d * (tp1 - entry)
            pnl = frac * (g1 - fee_m * tp1) + (1 - frac) * (d * (exit2 - entry) - fee_t * exit2)
        else:
            pnl = d * (exit2 - entry) - fee_t * exit2
        pnl -= fee_t * entry
        out_i[cnt] = i
        out_rn[cnt] = pnl / sd
        out_k[cnt] = k - i
        cnt += 1
        i = k + 1
    return cnt


def run_partial(data, make_sig, s, T, tp1_r, frac, cost=None, split_year=2024):
    cost = cost or COST
    allr, yrs, per = [], [], {}
    for name, d in data.items():
        sig = make_sig(d)
        cap = int((sig != 0).sum()) + 1
        oi, orn, ok = np.zeros(cap, np.int64), np.zeros(cap), np.zeros(cap, np.int64)
        n = sim_partial(sig, d["o"], d["h"], d["l"], d["c"], d["atr"], s, T, tp1_r, frac, cost["fee_t"], cost["fee_m"], cost["slip"], oi, orn, ok)
        if n:
            allr.append(orn[:n]); yrs.append(d["year"][oi[:n]]); per[name] = (orn[:n], d["year"][oi[:n]])
    r, y = np.concatenate(allr), np.concatenate(yrs)
    tr, te = r[y < split_year], r[y >= split_year]
    pos = sum(1 for nm, (rr, yy) in per.items() if (yy >= split_year).any() and rr[yy >= split_year].mean() > 0)
    return dict(n=len(r), win=float((r > 0).mean()), net=float(r.mean()), train=float(tr.mean()), test=float(te.mean()), pos=pos, coins=len(per),
                dd=float(np.max(np.maximum.accumulate(np.cumsum(r)) - np.cumsum(r))))


# ---------------- signal families ----------------


def sig_meanrev(d, zk, rsi_lo, vmin):
    z = (d["c"] - d["ema20"]) / d["atr"]
    long_ = (z < -zk) & (d["rsi"] < rsi_lo) & (d["vr"] > vmin)
    short_ = (z > zk) & (d["rsi"] > 100 - rsi_lo) & (d["vr"] > vmin)
    return (long_.astype(np.int8) - short_.astype(np.int8))


def sig_burst(d, a, vmin, cont=1):
    rng = d["h"] - d["l"]
    up = (rng > a * d["atr"]) & (d["vr"] > vmin) & (d["c"] > d["l"] + 0.8 * rng)
    dn = (rng > a * d["atr"]) & (d["vr"] > vmin) & (d["c"] < d["l"] + 0.2 * rng)
    return cont * (up.astype(np.int8) - dn.astype(np.int8))


def sig_pullback(d, rsi_lo):
    up = (d["ema50"] > d["ema200"]) & (d["c"] > d["ema200"]) & (d["rsi7"] < rsi_lo)
    dn = (d["ema50"] < d["ema200"]) & (d["c"] < d["ema200"]) & (d["rsi7"] > 100 - rsi_lo)
    return up.astype(np.int8) - dn.astype(np.int8)


def _cross_up(a, b):
    x = np.zeros(len(a), bool)
    x[1:] = (a[:-1] <= b[:-1]) & (a[1:] > b[1:])
    return x


def _cross_dn(a, b):
    x = np.zeros(len(a), bool)
    x[1:] = (a[:-1] >= b[:-1]) & (a[1:] < b[1:])
    return x


def sig_emacross(d):
    return _cross_up(d["ema9"], d["ema21"]).astype(np.int8) - _cross_dn(d["ema9"], d["ema21"]).astype(np.int8)


def sig_rsiflip(d, lo=30.0, hi=70.0):
    r = d["rsi"]
    up = np.zeros(len(r), bool)
    dn = np.zeros(len(r), bool)
    up[1:] = (r[:-1] < lo) & (r[1:] >= lo)
    dn[1:] = (r[:-1] > hi) & (r[1:] <= hi)
    return up.astype(np.int8) - dn.astype(np.int8)


def sig_vwap(d):
    c, l, h, v = d["c"], d["l"], d["h"], d["vwap"]
    up = np.zeros(len(c), bool)
    dn = np.zeros(len(c), bool)
    up[1:] = (c[:-1] > v[:-1]) & (l[1:] <= v[1:]) & (c[1:] > v[1:])             # vwap ko chhoo kar upar band: bounce
    dn[1:] = (c[:-1] < v[:-1]) & (h[1:] >= v[1:]) & (c[1:] < v[1:])             # vwap se reject
    return up.astype(np.int8) - dn.astype(np.int8)


def sig_range(d, width=6.0, edge=0.15):
    rng = d["hi20"] - d["lo20"]
    tight = rng < width * d["atr"]
    up = tight & (d["c"] <= d["lo20"] + edge * rng)
    dn = tight & (d["c"] >= d["hi20"] - edge * rng)
    return up.astype(np.int8) - dn.astype(np.int8)


def sig_flow(d, th=0.08, cont=1):
    x = d["dr"]
    up = np.zeros(len(x), bool)
    dn = np.zeros(len(x), bool)
    up[1:] = (x[:-1] <= th) & (x[1:] > th)
    dn[1:] = (x[:-1] >= -th) & (x[1:] < -th)
    return cont * (up.astype(np.int8) - dn.astype(np.int8))


def sig_bias_flow(d, mode, rl=35, th=0.03):
    """mode 'pb': bias + flow + pullback (RSI7) | 'bo': bias + flow + 20-bar breakout (3 gates)."""
    up_b, dn_b = d["bias_f"] > d["bias_s"], d["bias_f"] < d["bias_s"]
    up_f, dn_f = d["dr"] > th, d["dr"] < -th
    if mode == "pb":
        up, dn = up_b & up_f & (d["rsi7"] < rl), dn_b & dn_f & (d["rsi7"] > 100 - rl)
    else:
        up, dn = up_b & up_f & (d["c"] > d["hi20"]), dn_b & dn_f & (d["c"] < d["lo20"])
    return up.astype(np.int8) - dn.astype(np.int8)


def sig_random(d, p, seed=1):
    r = np.random.default_rng(seed)
    x = r.random(len(d["c"]))
    side = np.where(r.random(len(d["c"])) < 0.5, 1, -1).astype(np.int8)
    return np.where(x < p, side, 0).astype(np.int8)


# ---------------- loading / evaluation ----------------


def add_flow(d, n=8):
    """Order-flow proxy: taker buy volume se delta = (buy - sell)/total, pichli n bars par."""
    delta = 2.0 * d["tb"] - d["v"]
    cd, cv = np.cumsum(delta), np.cumsum(d["v"])
    dr = np.full(len(delta), np.nan)
    dr[n:] = (cd[n:] - cd[:-n]) / np.maximum(cv[n:] - cv[:-n], 1e-12)
    d["dr"] = dr
    return d


def load(dir_, tf="15m"):
    data = {}
    for p in sorted(glob.glob(os.path.join(dir_, f"*_{tf}.npz"))):
        z = np.load(p)
        d = {k: z[k].astype(np.float64) if k != "ts" else z[k] for k in ("ts", "o", "h", "l", "c", "v", "tb")}
        d["atr"] = atr_w(d["h"], d["l"], d["c"])
        d["ema20"], d["ema50"], d["ema200"] = ema(d["c"], 20), ema(d["c"], 50), ema(d["c"], 200)
        d["rsi"], d["rsi7"] = rsi_w(d["c"], 14), rsi_w(d["c"], 7)
        d["vr"] = d["v"] / sma_prior(d["v"], 20)
        d["ema9"], d["ema21"] = ema(d["c"], 9), ema(d["c"], 21)
        d["vwap"] = vwap_daily(d["ts"], d["h"], d["l"], d["c"], d["v"])
        d["hi20"], d["lo20"] = roll_max_prior(d["h"], 20), roll_min_prior(d["l"], 20)
        add_flow(d)
        d["bias_f"], d["bias_s"] = ema(d["c"], 800), ema(d["c"], 3200)      # ~ 1h EMA50/EMA200 ke barabar (15m par)
        d["year"] = (d["ts"] // 1000 // 31_557_600 + 1970).astype(np.int32)
        data[os.path.basename(p).split("_")[0]] = d
    return data


COST = dict(fee_t=0.0005, fee_m=0.0002, slip=0.0002)
FREE = dict(fee_t=0.0, fee_m=0.0, slip=0.0)


def run(data, make_sig, s, t, T, mode=0, off=0.0, W=2, cost=COST, split_year=2024, rev=0):
    """Saare coins par: (n, winrate, avgR net, avgR gross, train avgR, test avgR, test coins positive)."""
    allr, allg, yrs, per = [], [], [], {}
    for name, d in data.items():
        sig = make_sig(d)
        cap = int((sig != 0).sum()) + 1
        oi, orn, org, ok = np.zeros(cap, np.int64), np.zeros(cap), np.zeros(cap), np.zeros(cap, np.int64)
        n = sim(sig, d["o"], d["h"], d["l"], d["c"], d["atr"], s, t, T, mode, off, W, cost["fee_t"], cost["fee_m"], cost["slip"], oi, orn, org, ok, rev)
        if n == 0:
            continue
        allr.append(orn[:n]); allg.append(org[:n]); yrs.append(d["year"][oi[:n]])
        per[name] = (orn[:n], d["year"][oi[:n]])
    if not allr:
        return None
    r, g, y = np.concatenate(allr), np.concatenate(allg), np.concatenate(yrs)
    tr, te = r[y < split_year], r[y >= split_year]
    pos = sum(1 for nm, (rr, yy) in per.items() if (rr[yy >= split_year].mean() if (yy >= split_year).any() else -1) > 0)
    return dict(n=len(r), win=float((r > 0).mean()), net=float(r.mean()), gross=float(g.mean()),
                train=float(tr.mean()) if len(tr) else float("nan"), test=float(te.mean()) if len(te) else float("nan"),
                ntr=len(tr), nte=len(te), pos=pos, coins=len(per), years={int(k): float(r[y == k].mean()) for k in np.unique(y)})


def fmt(name, res):
    if not res:
        return f"{name:52} (koi trade nahi)"
    return (f"{name:52} n={res['n']:6d} ({res['n'] / max(1, res['coins']) / 6.8 / 365:4.2f}/coin/din) win={res['win']:.0%} "
            f"gross={res['gross']:+.3f}R net={res['net']:+.3f}R | train {res['train']:+.3f} test {res['test']:+.3f} | test coins+ {res['pos']}/{res['coins']}")


if __name__ == "__main__":
    d = load(sys.argv[1])
    print(len(d), "coins loaded:", ", ".join(d), flush=True)


def resample(d, k, base_ms=900_000):
    """15m -> k*15m bars (sirf poore, bina gap wale groups) + indicators dobara."""
    ts = d["ts"]
    new_ms = k * base_ms
    start = int(np.argmax(ts % new_ms == 0))
    n = (len(ts) - start) // k * k
    sl = slice(start, start + n)
    t2 = ts[sl].reshape(-1, k)
    ok = (t2[:, -1] - t2[:, 0]) == (k - 1) * base_ms
    r = {}
    for key, fn in (("o", lambda a: a[:, 0]), ("h", lambda a: a.max(1)), ("l", lambda a: a.min(1)), ("c", lambda a: a[:, -1]), ("v", lambda a: a.sum(1)), ("tb", lambda a: a.sum(1))):
        r[key] = fn(d[key][sl].reshape(-1, k))[ok]
    r["ts"] = t2[:, 0][ok]
    r["atr"] = atr_w(r["h"], r["l"], r["c"])
    r["ema20"], r["ema50"], r["ema200"] = ema(r["c"], 20), ema(r["c"], 50), ema(r["c"], 200)
    r["rsi"], r["rsi7"] = rsi_w(r["c"], 14), rsi_w(r["c"], 7)
    r["vr"] = r["v"] / sma_prior(r["v"], 20)
    r["ema9"], r["ema21"] = ema(r["c"], 9), ema(r["c"], 21)
    r["vwap"] = vwap_daily(r["ts"], r["h"], r["l"], r["c"], r["v"])
    r["hi20"], r["lo20"] = roll_max_prior(r["h"], 20), roll_min_prior(r["l"], 20)
    add_flow(r)
    r["bias_f"], r["bias_s"] = ema(r["c"], 50), ema(r["c"], 200)
    r["year"] = (r["ts"] // 1000 // 31_557_600 + 1970).astype(np.int32)
    return r
