# Grid Trading Bot (Binance, backtest + paper)

Sirf **backtest** aur **paper trading** (fake money). Live trading jaanbujhkar nahi hai.

## Setup
```bash
pip install -r requirements.txt
```

## Chalana
```bash
python main.py backtest --source synthetic              # demo data
python main.py backtest --source binance --symbol BTC/USDT --timeframe 1h --limit 1000
python main.py backtest --source csv --csv data.csv     # columns: timestamp,open,high,low,close
python main.py paper --symbol BTC/USDT                  # live price, fake money
python -m pytest
```

## config.json
- `lower` / `upper`: grid ki price range. Isse **current price ke aas-paas** rakho.
- `grids`: levels ki sankhya. Zyada grids = zyada trades, lekin har grid ka profit chhota.
- `investment`: total USDT capital (har grid ko barabar baanta jata hai).
- `fee_rate`: Binance spot 0.1%. Agar grid spacing 2x fee se kam hai to bot start hi nahi hoga.
- `stop_loss_pct`: price `lower` se itna neeche gira to sab bech ke bot band.

## Grid strategy kaise kaam karti hai
Range ko levels mein baanta. Price level par girte hi BUY, ek level upar jate hi SELL.
Sideways market mein chhote chhote profits jama hote hain. **Risk:** agar price range se
neeche trend karke girta rahe, to bot coins pakde rehta hai (isliye stop-loss). Agar price
range se upar nikal jaye to profit rukta hai aur buy & hold se kam milta hai.

## Live trading se pehle
1. Kam se kam kuch hafte paper trading chalao, aur alag alag market periods par backtest karo.
2. Backtest assumptions: orders level price par fill ho jate hain, slippage nahi hai.
3. Live karna ho to Binance **testnet** se shuru karo, API key mein **withdrawal permission kabhi mat do**, aur sirf wahi paisa lagao jo khone ka dukh na ho.

## Telegram notifications
Bot har trade open/close par message bhejta hai (entry, take-profit, size, exit, profit, account equity), plus start/stop par.

1. Telegram par **@BotFather** → `/newbot` → token copy karo.
2. Apne naye bot ko ek message bhejo, aur chat id **@userinfobot** se lo.
3. Environment variables set karo (inhe config ya git mein kabhi mat daalo):
```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"
python main.py paper --symbol SOL/USDT
```
Variables set na hon to bot normal chalta hai, bas notification nahi bhejta. Agar token kahin share ho gaya ho to BotFather mein `/revoke` karo.

## Scalp bot (multi-coin, long + short, paper)
Binance USDT-M futures ke saare liquid coins ko har 15m candle close par scan karta hai. 4 gates
(trend, momentum, breakout, volume spike) mein se jis coin par sabse zyada agree kare, wahan LONG ya SHORT paper trade.

- **TP / SL margin ROI par hain:** `tp_roi` 70%, `sl_roi` 20%. 10x leverage par yeh price ka +7% / -2% hota hai.
- Risk controls: `max_open`, `margin_pct`, `max_hold_hours`, `cooldown_candles`, `max_daily_loss_pct`.
- Settings: `scalp_config.json`.

```bash
python main.py scalp-backtest --source binance --coins 30 --limit 1500   # real data par test
python main.py scalp-paper                                               # live scan, fake money, Telegram alerts
python main.py scalp-stats                                               # closed trades ka analysis
```
`scalp_trades.csv` mein har trade ke gates/volume/ATR save hote hain, taaki review karke settings tune kar sako.
`scalp_state.json` se restart ke baad open positions wapas aa jaati hain.
Synthetic backtest (`--source synthetic`) sirf engine check hai, profit ka sabut nahi.
