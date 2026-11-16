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
