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
Telegram par **teen tarah ke message** aate hain: trade open (entry, stop, target, size, kaaran), trade close (exit, booked profit/loss, equity), aur **har 12 ghante ki report** (trades, total profit, total loss, net, win rate, open positions, equity; `report_hours` se badlo, 0 = band). Start/stop aur stop-loss khiskna sirf console mein dikhte hain.

1. Telegram par **@BotFather** → `/newbot` → token copy karo.
2. Apne naye bot ko ek message bhejo, aur chat id **@userinfobot** se lo.
3. **Sabse aasan tareeka (Windows):** `crypto-bot` folder mein `notepad .env` chalao, "Yes" (create new file) dabao, 2 lines likho aur save karo:
```
TELEGRAM_BOT_TOKEN=aapka_token
TELEGRAM_CHAT_ID=aapka_numeric_chat_id
```
Phir `python main.py telegram-test` se check karo. `.env` git mein nahi jaati. (Ya environment variables set karo:)
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

## Lamba history backtest + settings sweep (walk-forward)
Binance USDT-M futures ka data Sept 2019 se hai (BTC/ETH ~6 saal). Naye coins ka kam. Download ek baar hota hai aur `data_cache/` mein save rehta hai.

```powershell
python main.py scalp-download --coins 30 --years 10        # shuru mein lamba time lagega, beech mein ruk ke dobara chala sakte ho
python main.py scalp-backtest --source cache --coins 30    # saal-ba-saal PnL dikhata hai
python main.py scalp-sweep --quick                         # 8 combos (jaldi)
python main.py scalp-sweep                                 # 432 combos (kaafi der lagega)
```
Sweep data ko do hisson mein baantta hai: pehle ~70% par settings tune hoti hain, baaki ~30% (jo tune mein dekha hi nahi) par check. Sirf wahi settings **PASS** hoti hain jo dono hisson mein profitable hon
(test hisse mein profit factor > 1.1, drawdown < 35%, kam se kam 50 trades). Sab results `sweep_results.csv` mein.

Limits (zaroor padho):
- Aaj ke top coins ka hi data hota hai; jo coins delist ho gaye woh nahi hain, isliye result thoda zyada achha dikhta hai (survivorship bias).
- Bahut saare combos test karne par koi na koi "lucky" nikal sakta hai. PASS ko guarantee mat samjho; paper mode mein alag se confirm karo.
- `btc_filter`: BTC up ho to sirf LONG, down ho to sirf SHORT.

## Local dashboard
Do alag PowerShell windows kholo (dono `crypto-bot` folder mein):
```powershell
python main.py scalp-paper
```
```powershell
python main.py scalp-dashboard
```
Browser mein `http://127.0.0.1:8050` khulega (sirf aapke PC par). Open positions (symbol, side, leverage, size, entry, mark price, TP/SL, live PnL + ROI%, kitni der se open),
trade history, equity chart, win rate. Har 3 second mein refresh. Dashboard sirf `scalp_state.json` aur `scalp_trades.csv` padhta hai, bot ko chhuta nahi.
Mark price bot ke monitor se aata hai (har `poll_seconds`), isliye bot band ho to dashboard "Bot ruka hua" dikhayega.

Dashboard mein **Aaj ka Profit / Loss / Net** (closed trades) cards ke roop mein, aur **Daily P&L** tab mein din-ba-din table (trades, won/lost, profit, loss, net) dikhta hai. "Aaj" aapke PC ke local time ke hisaab se hai. (Bot ka daily loss limit aur Telegram daily report UTC din par chalte hain.)

## ATR exits + trailing stop (default ab yahi hai)
Purana 70% / -20% ROI rule backtest mein fail hua (6 saal, profit factor 0.90). Ab default `exit_mode = "atr"`:
- **Stop** = entry se `sl_atr` x ATR door (har coin ki apni volatility). **Target** = `tp_atr` x ATR (0 = koi fixed target nahi, sirf trailing).
- **Trailing stop:** profit `trail_start_atr` x ATR ho jaye to bot stop-loss ko khud aage khiskata hai (long mein upar, short mein neeche). Stop sirf profit ki disha mein khiskata hai, kabhi peeche nahi.
  Yeh sab backend mein chupchap hota hai (Telegram par message nahi), dashboard mein naya SL dikhta rehta hai.
- **Position size:** har trade mein start balance ka `risk_pct` (1%) risk, yani stop lagne par ~1R loss. `margin_pct` size ki upar limit hai.
- Backtest ab fixed-size hai (`compound: false`), aur har trade ka **R-multiple** dikhata hai (`Avg per trade: +0.1 R` = edge).

```powershell
python main.py scalp-sweep --quick               # ATR mode, 16 combos
python main.py scalp-sweep                       # ATR mode, 144 combos
python main.py scalp-sweep --mode roi --quick    # purana ROI rule
python main.py scalp-backtest --source cache --coins 30
```

## Slower timeframe test (1h / 4h)
15m par ATR strategy fail hui (6 saal ke data mein -0.12 R/trade). Slower candles par kam trades hoti hain, to fees ka bojh kam padta hai.
Download dobara nahi karna, 15m cache se 1h/4h candles khud ban jaati hain:
```powershell
python main.py scalp-backtest --source cache --coins 30 --timeframe 1h
python main.py scalp-sweep --quick --timeframe 1h
python main.py scalp-sweep --quick --timeframe 4h
```
Backtest ab fixed-size hai aur account zero hone par ruka nahi, to poori history (har saal) test hoti hai. "-100% se zyada loss" ka matlab hai ki poore data mein is size par chalte to capital se zyada kho dete.

## Validation (kya edge asli hai?)
Sweep ka PASS ab risk-normalized hai (drawdown position size se scale hota hai, isliye sirf absolute dd par fail nahi karte): dono hisson mein profit, R/trade > 0, profit factor > 1.1, return/drawdown >= 1.
PASS ke baad **zaroor** validate chalao:
```powershell
python main.py scalp-validate                       # default: sweep ka best 4h candidate
python main.py scalp-validate --set sl_atr=2.5 --set min_gates=4 --set timeframe=4h
```
Checks: har saal ka PnL, kya sirf top-3 coins ne kamaya, sirf BTC+ETH par result (survivorship bias kam), parameters hilane par result barkarar rehta hai, aur Monte Carlo (worst-case drawdown + suggested risk_pct).

## Validate hua 4h config (ab default `scalp_config.json`)
6 saal ke 30 coins ke backtest mein: +0.095 R/trade, profit factor 1.24, 4557 trades, 6/8 saal profitable, top-3 coins ke bina bhi profitable,
BTC+ETH par bhi profitable, 8/8 nearby settings profitable. **Lekin:** survivorship bias baaki hai, 2026 abhi tak negative hai (-23R), aur edge chhota hai (~0.1R/trade).
`risk_pct 0.004` (0.4%) isliye ki 95% worst-case drawdown ~20% rahe. Bot top-30 liquid coins (`max_coins`) par hi chalta hai, kyunki edge sirf unhi par test hua.
4h candle par scan hota hai (UTC 00, 04, 08, 12, 16, 20 ke baad), to trades kam aur kabhi kabhi din bhar koi signal nahi.


## Telegram sirf proxy se (VPN poore PC par nahi)
Agar aapke network par `api.telegram.org` block hai, to `.env` mein ek line jodo, aur sirf Telegram ka traffic us proxy se jayega (Binance seedha):
```
TELEGRAM_PROXY=socks5h://127.0.0.1:40000
```
`40000` Cloudflare WARP ke "proxy mode" ka default port hai. `pip install -r requirements.txt` (pysocks chahiye). `python main.py telegram-test` se check karo.

Kai proxy ek saath (free proxy aksar mar jaati hain): `TELEGRAM_PROXY=socks5h://1.2.3.4:1080, http://5.6.7.8:8080` — bot ek-ek karke try karta hai aur jo chale use yaad rakhta hai.
Password wali proxy: `socks5h://user:password@host:port`. **Sirf SOCKS5 ya HTTP(S) proxy chalegi.** Telegram app wali MTProto proxy (`tg://proxy?...` link) bot ke liye nahi chalti.

`python main.py telegram-test` ab step-by-step bata deta hai kya galat hai (file mili ya nahi, token ka format, token valid hai ya nahi, chat id, test message). `.env` ki value environment variable se upar rakhi jati hai.
Agar pehle PowerShell mein `$env:TELEGRAM_BOT_TOKEN=...` chalaya tha to wo us window mein bachi rehti hai. Saaf karne ke liye: `Remove-Item Env:TELEGRAM_BOT_TOKEN, Env:TELEGRAM_CHAT_ID -ErrorAction SilentlyContinue`.

## Scan speed
Bot har coin ki closed candles memory mein yaad rakhta hai. Pehli scan mein poori history aati hai, uske baad har scan mein sirf **nayi candle** mangta hai. Coins ke requests parallel (`fetch_workers`, default 5) chalte hain. Har scan ke baad console mein `scan X.Xs` dikhta hai.
Agar bot lamba band raha ho to gap milne par wo apne aap poori history dobara le leta hai. Agar scan par rate-limit/ban jaisa error aaye to `fetch_workers` kam kar do (jaise 3).


## Sirf kuch chune hue coins par (jaise BTC, ETH, SOL, BNB)
`scalp_config.json` mein `"symbols"` khali `[]` hai (default: top-30 liquid coins, jo validate hua). Naam daalne par bot sirf unhi par scan karta hai, jaise `["BTC", "ETH", "SOL", "BNB"]` (volume/`max_coins` ka filter nahi lagta).
```powershell
python main.py scalp-validate --symbols BTC,ETH,SOL,BNB                     # pehle inhi coins par backtest/validate
python main.py scalp-backtest --source cache --timeframe 4h --symbols BTC,ETH,SOL,BNB
python main.py scalp-paper                                                  # config ke symbols par
python main.py scalp-paper --symbols BTC,ETH                                # ya command se override
python main.py scalp-download --symbols BTC,ETH,SOL,BNB                     # data cache mein nahi hai to
```
Dhyan: 4 coins par trades kam hongi (hafte mein ~1-2) aur coins aapas mein correlated hain (BTC girta hai to baaki bhi), isliye `max_open` kam rakhna behtar hai.


## Test trade (pipeline dekhne ke liye)
Asli signal ka intezaar kiye bina ek nakli paper trade kholo (Telegram open/close message aur dashboard dekhne ke liye). Alag files mein chalti hai (`scalp_test_*`), asli paper test ke numbers mein nahi judti:
```powershell
python main.py scalp-test-trade                                   # abhi ki candle ke hisaab se coin aur side khud chune (3 minute baad band)
python main.py scalp-test-trade --symbol BTC --side long --minutes 30   # ya khud chuno
python main.py scalp-dashboard --state scalp_test_state.json --trades scalp_test_trades.csv --port 8051   # test trade dashboard par
```

## Intrabar entry (adhoori candle dekh kar foran entry)
Default `entry_mode: "close"`: signal sirf band hui 4h candle par (yahi validate hua). `"intrabar"`: bot har 15 minute par adhoori 4h candle ko dekhta hai aur signal banate hi entry le leta hai (4 ghante ka intezaar nahi).
Pehle backtest se compare karo (6 saal ka data, same settings):
```powershell
python main.py scalp-validate --entry intrabar          # intrabar (precompute mein kuch minute lagte hain)
python main.py scalp-validate                           # close (purana)
python main.py scalp-validate --entry close15           # band candle par entry, par exit 15m par (fair compare)
```
Jo behtar nikle wahi `scalp_config.json` mein `"entry_mode"` rakho. Intrabar mein signal candle ke beech mein aa ke candle band hone tak hat bhi sakta hai (whipsaw); backtest ye bhi ginta hai.


## Bot ko trade kyun nahi mil rahi? (`scalp-watch`)
```powershell
python main.py scalp-watch
```
Har coin ki abhi ki (adhoori) candle par kitne gates mil rahe hain, kaun se mile aur kaun se baaki hain. 3/4 hone par (aur ATR theek ho) wo coin `TRADE SIGNAL` dikhata hai, aur bot ka agla 15-minute scan us par trade khol deta hai.


## Sizing: equity ka % margin (`sizing_mode`)
- `"risk"` (default, validate hua): stop lagne par `risk_pct` (0.4%) loss. Stop door ho to size chhota, paas ho to bada.
- `"margin"`: har trade mein `margin_pct` (jaise 0.05 = 5%) margin, `leverage` se multiply. Stop kitna bhi door ho, size wahi. **Chauda stop = bada loss.** 4h strategy (stop ~4%) par 5% margin x 10x = ~2% equity risk per trade, 5 guna validate hue risk se zyada.
`compound: true` karne par % current balance ka lagta hai, warna start_balance ka.

## Liquidation price (Liq. Price) door rakhna
Isolated margin mein liquidation entry se lagbhag `1/leverage - 0.5%` door hoti hai: 10x par ~9.5%, 5x par ~19.5%, 3x par ~32.8%.
- `min_liq_distance` (default config mein 0.30): liquidation entry se kam se kam itni door na ho to trade nahi khulti.
- `leverage` 3 rakha hai, isliye ~33% door. Telegram "TRADE OPENED" mein `Liquidation: ... (33% door)` aur dashboard mein `Liq. Price` column.
- `max_atr_pct` 0.04: validate hue backtest mein 10x par bahut volatile coins (ATR 4% se zyada) khud skip ho jate the. Wahi rakha hai taaki trades ka set na badle.
- Ye andaza hai (Binance maintenance margin tier/coin ke hisaab se alag hota hai). Paper account asli liquidation simulate nahi karta; stop-loss hamesha liquidation se pehle lagta hai.

`python main.py scalp-sweep --mode roi30 --timeframe 15m` : 30% ROI profit-book + kam leverage wale combos (36) ko test karta hai.

## Dashboard ka CLOSE button
Har open trade ke saamne `CLOSE` button hai. Dabane par (confirm ke baad) dashboard ek request file (`scalp_state_commands.jsonl`) mein likhta hai, aur bot agle ~10 second mein us trade ko market price par band karta hai (reason `MANUAL`) aur Telegram par "MANUAL CLOSE" bhejta hai.
- Bot chalna zaroori hai (button sirf bot ko bolta hai, khud trade band nahi karta).
- Safety: dashboard sirf aapke PC (127.0.0.1) par chalta hai; dusri website se bheji gayi request reject hoti hai (Host/Origin/custom header check).

Default `max_coins` ab 80 hai (volume ke hisaab se top 80, kam se kam 20M USDT 24h volume). Backtest top-30 par validate hua tha; baaki coins par paper mein dekha ja raha hai. 30 par wapas jaane ke liye `scalp_config.json` mein `"max_coins": 30`.

## Discord alerts (Telegram ke saath ya akele)
1. Discord mein apna server kholo (nahi hai to "Add a Server" -> "Create My Own"). Jis channel mein alerts chahiye: channel ke naam ke saath gear icon -> **Integrations** -> **Webhooks** -> **New Webhook** -> **Copy Webhook URL**.
2. `notepad .env` mein ek line jodo (URL ek secret hai: kisi ko mat dena, chat/screenshot mein mat bhejna):
   ```
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```
   (Discord block ho to: `DISCORD_PROXY=socks5h://127.0.0.1:PORT`.)
3. `python main.py discord-test` -> channel mein "✅ Discord test" aana chahiye.
4. Bot restart karo: ab trade open/close, 12-hour report Telegram aur Discord dono par jayenge. Ek band ho to doosra chalta rahta hai (aur jo message nahi gaye wo baad mein "der se" bheje jaate hain).

Note: `scalp-download` hamesha **15m** candles laata hai (config ka timeframe 4h ho tab bhi). Backtest/validate cache ke 15m files (`*_15m.csv`) se 4h/1h/intrabar banate hain. Purane galti se bane `*_4h.csv` files ko ignore/delete kar sakte ho.


## Ek command / ek double-click
`python main.py scalp-paper` ab dashboard bhi saath mein shuru karta hai (`http://127.0.0.1:8050`, har 3 second mein auto-refresh). Alag `scalp-dashboard` command ki zaroorat nahi.
Windows par `start_bot.bat` ko double-click karo: code update + bot + dashboard (aur browser mein dashboard khul jata hai). Isko Desktop par shortcut bana lo.
PC chalu hote hi apne aap shuru karne ke liye: `Win+R` -> `shell:startup` -> us folder mein `start_bot.bat` ka shortcut rakh do.
Flags: `--no-dashboard` (band), `--dashboard-port 8060`, `--open` (browser khol do).

Browser tab: `--open` ya `start_bot.bat` har baar naya tab **nahi** kholta. Bot shuru hone ke 5 second baad check hota hai ki koi dashboard tab pehle se khula aur refresh ho raha hai ya nahi; khula ho to naya tab nahi khulta (purana tab bot restart ke baad khud jud kar update ho jata hai). Dashboard tab ko ek baar kholkar pin/khula rakho.

**80/69 coins ka validate (intrabar, 4h):** +0.064 R/trade, profit factor 1.15, +163%, drawdown 26%, 2023 negative; 30 coins par +0.095 R, pf 1.24, +204%, dd 20%, 8/8 saal. Naye ~39 coins ne ~-0.07 R/trade diya (kul ~-$4,000), trades sirf +25% badhi. Isliye default `max_coins` wapas 30.

## FREQ bot (zyada trades, alag paper account)
`scalp_config_freq.json`: 2 gates, max 10 open, 3 nayi/scan, risk 0.2% (~5 trades/din, sandbox backtest: +0.044R/trade, +119%, dd 23%; validated bot se risk-adjusted kamzor, ret/dd 5.2 vs 6.9).
`start_bot_freq.bat` double-click (ya `python main.py --scalp-config scalp_config_freq.json scalp-paper --state scalp_state_freq.json --trades scalp_trades_freq.csv --dashboard-port 8060`).
Alag state/trades files aur alag dashboard (`http://127.0.0.1:8060`); Telegram/Discord messages mein "· FREQ" likha aata hai. Validated bot (`start_bot.bat`, port 8050) saath mein chalta rahe.
Aapne ke coins par validate karne ke liye: `python main.py scalp-validate --entry intrabar --set min_gates=2 --set max_open=10 --set max_new_per_scan=3 --set risk_pct=0.002`

12h report mein ab "Bot zinda: N scans, M signals, K skip, aakhri scan ka time, aakhri skip ki wajah" bhi hota hai. Trade na ho tab bhi report aati hai, to mobile par hi pata chal jata hai ki bot chal raha hai (Telegram + Discord dono par). `report_hours` se interval badlo (jaise 6).

## BIG bot (kam trades, badi position, alag paper account)
`scalp_config_big.json`: sab 4 gates, 48h hold, max 5 open, 1 nayi/scan, risk 0.6% (3x par ek trade ~$1,000-1,500 notional, margin cap 5%).
Sandbox backtest (30 coins): ~10.7 trades/hafta, +0.094 R/trade, ~$52/hafta ($10,000 par), +183%, worst drawdown ~35% (validated bot: 18/hafta, +0.063R, $44/hafta, dd 23%).
`start_bot_big.bat` ya `python main.py --scalp-config scalp_config_big.json scalp-paper --state scalp_state_big.json --trades scalp_trades_big.csv --dashboard-port 8070`. Dashboard `http://127.0.0.1:8070`, alerts mein "· BIG".
Apne data par check: `python main.py scalp-validate --entry intrabar --set min_gates=4 --set max_new_per_scan=1 --set risk_pct=0.006`

## SCALP1H (experiment): max 1 ghante hold, ~2-3 trades/ghanta
`scalp_config_1h.json`: 15m candles, hold <= 1 ghanta, 2x leverage, badi position (cap $1,500), trailing stop 1 ATR, trade-alerts band (`notify_trades: false`), report har 6 ghante.
**Backtest (sandbox 30 coins): har variant loss mein**, ~64 trades/din, -0.10 R/trade, ~ -$700/hafta. Sirf paper mein dekhne ke liye; asli paise se mat chalana.
`start_bot_1h.bat`, dashboard `http://127.0.0.1:8080`.
Telegram band karna: `.env` mein TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / TELEGRAM_PROXY lines ke aage `#` laga do, bot restart.
