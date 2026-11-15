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
