# Scalping research lab (bot ka hissa nahi)

`download_vision.py`: Binance ke public archive (data.binance.vision) se futures 15m klines -> `.npz`.
`scalp_lab.py`: numba se tez backtest. Har trade R-multiple mein (1R = stop distance), fees (taker 0.05%, maker 0.02%) + slippage (0.02%) ke saath aur bina.

Is research mein (12 coins, 2020-2026, 15m) ~170 combos test hue: mean-reversion fade, momentum burst (continuation/fade), trend pullback, market aur limit entry.

Nateeja:
- Random entry par gross ~0R, par fees ke baad ~ -0.25R (1 ATR stop): 15m par har trade ka ~25% risk sirf fees/slippage mein jata hai.
- Momentum burst aur trend pullback mein 15m par fees ke bina +0.05..+0.08R ka halka edge hai, par fees ke baad -0.04..-0.15R. Dono hisson (train 2020-23, test 2024-26) mein koi combo net profitable nahi.
- Limit (maker) entry se loss ghata (-0.11R -> -0.04R) par positive nahi hua.
- Timeframe badhne par fees ka bojh ghatta hai: 15m -0.07R, 1h +0.02R, 2h +0.06R, 4h +0.05R (4h mein train aur test dono positive). Yahi bot ka 4h trend tareeka hai.

Chalane ke liye (optional): `pip install numpy numba`.

## Binance Square post ki 6 scalping strategies ka test (5m, 8 coins, 2020-2026)
Mechanical version, market entry, taker fee 0.05% + slippage 0.02%, R = ATR stop:
| Strategy | Gross R/trade (fees ke bina) | Net R/trade | Test coins profitable |
|---|---|---|---|
| EMA 9/21 crossover (ulta cross par exit) | -0.007 | -0.216 | 0/8 |
| EMA 9/21 crossover (stop/target) | +0.003 | -0.255 | 0/8 |
| VWAP bounce/reject | -0.007 | -0.260 | 0/8 |
| RSI quick flip 30/70 | -0.019 | -0.227 | 0/8 |
| Range scalping | +0.001 | -0.246 | 0/8 |
| Random entry (control) | -0.094 | -0.340 | 0/8 |
Fees ke bina bhi in tareeko mein koi edge nahi (gross ~0). Order book/tape reading test nahi ho sakta (L2 data + low latency chahiye).

## HTF bias + order flow (taker delta) gates, 12 coins, 2020-2026
Order-flow proxy: Binance klines ka taker-buy volume se delta=(buy-sell)/total, pichli 8 bars par.
- 15m aur 1h par: bias/flow gates ka net result negative ya ~0 (fees ke baad).
- 4h par **bias + 20-bar breakout (flow ke bina)** hi net positive hai (T24: +0.21R, T48: +0.41R; train/test dono positive, long hold, koi TP nahi). Yani edge mostly "higher-timeframe trend + breakout" se aata hai.
- Flow gate (delta>3%) thoda sudhar laata hai (test +0.07R -> +0.16R at T24, +0.24R -> +0.32R at T48), par zyada sakht (6%, 10%) karne par train achha aur test kharab (overfit).
- Lamba hold (T48 = 8 din) 4h par T24 se behtar. Bot ke apne validate mein bhi max_hold_hours=96 behtar nikla (+0.128R vs +0.095R).
Caveat: 12 survivor coins, kuch combos mein se chuna gaya result: bot ke pipeline par validate karna zaroori.
