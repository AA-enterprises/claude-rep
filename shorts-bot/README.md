# 🎬 Shorts Bot

Ye bot ek lambi podcast video ko kai viral **YouTube Shorts** mein badal deta hai. Har Short mein:

1. **Hook:** shuru mein AI awaaz 2-4 second mein curiosity paida karti hai. Awaaz **larki, larke ya bachche** ki ho sakti hai, har zubaan mein (default: larki).
2. **Asal clip:** podcast ka sab se viral hissa 9:16 vertical mein, aap ki zubaan ke **captions** ke saath (neeche chhoti peeli line mein asal English bhi).
3. **Outro:** AI awaaz apni raye/sabaq deti hai aur aakhir mein viewers se sawal poochti hai (comments ke liye).
4. Halka **background music** (agar aap `music` folder mein daalein).
5. Ek **thumbnail (.jpg)**: clip ka sab se achha frame (jahan chehra saaf ho) aur bare akharon mein AI ka likha chubhta hua text.
6. Saath mein ek **.txt file** jis mein title, description (credit ke saath) aur hashtags tayyar hote hain.

**Zubaanein:** urdu, english, hindi, arabic, french, german, spanish, turkish, portuguese, italian, indonesian, bengali, russian, japanese, korean, chinese. Podcast kisi bhi zubaan mein ho sakta hai: English se Urdu, Urdu se English, English se French, sab chalta hai.

---

## ⚙️ Pehli dafa setup (sirf ek baar, ~20 minute)

### Step 1: Python install karein
- https://www.python.org/downloads/ se Python 3.11 ya naya download karein.
- Install karte waqt **"Add Python to PATH"** ka box ✅ zaroor tick karein.

### Step 2: FFmpeg install karein (video editing ka engine)
**Windows:** Start menu mein "PowerShell" kholein aur ye likhein:
```
winget install Gyan.FFmpeg
```
**Mac:** `brew install ffmpeg`

Install ke baad PowerShell **band karke dobara kholein**.

### Step 3: Bot download karein aur packages install karein
1. GitHub par is repo ka **Code → Download ZIP** karein aur unzip karein.
2. `shorts-bot` folder kholein. Upar address bar mein `powershell` likh kar Enter dabayein (wahin terminal khul jayega).
3. Ye command chalayein:
```
pip install -r requirements.txt
```

### Step 4: AI ki key (script likhne wala AI)
1. https://console.anthropic.com par account banayein.
2. **Billing** mein $5-10 credit daalein (ek podcast ka kharcha taqreeban $0.30-0.60).
3. **API Keys → Create Key**, aur key copy karein.
4. `shorts-bot` folder mein `env.example` file ko Notepad se kholein, key paste karein, phir **"Save As"** karke naam `.env` rakhein.

### Step 5: Check karein
```
python bot.py --check
```
Sab ✅ hon to bot tayyar hai.

---

## 🔄 Khud-ba-khud update (ek dafa setup)

Is ke baad bot mein jo bhi tabdeeli ho, aap ko ZIP download nahi karni parti. `start.bat` har dafa chalne se pehle khud naya version le aata hai (ya `update.bat` par double-click karein).

1. PowerShell mein Git install karein, phir PowerShell band karke dobara kholein:
   ```
   winget install Git.Git
   ```
2. Bot GitHub se download karein:
   ```
   cd $env:USERPROFILE
   git clone -b claude/stoic-meitner-emwbfo https://github.com/AA-enterprises/claude-rep.git
   ```
   Browser mein GitHub login ka page khulega. Login karke "Authorize" karein.
3. Bot ab yahan hai: `%USERPROFILE%\claude-rep\shorts-bot`. Purane folder se apni **`.env`** file copy karke is naye folder mein paste karein.
4. Naye folder mein PowerShell kholein aur apni settings ki file banayein:
   ```
   copy config.local.example.yaml config.local.yaml
   notepad config.local.yaml
   ```
   Is mein channel ka naam aur `D:/YT Backup` pehle se likha hai. Jo badalna ho badlein, phir Ctrl+S.
5. `python bot.py --check` chalayein. Upar **Bot version** nazar aayega.

**Apni settings hamesha `config.local.yaml` mein likhein**, `config.yaml` mein nahi. Update `config.local.yaml` aur `.env` ko kabhi nahi chhuta.

## ▶️ Roz ka istemal

**Sab se aasaan tareeqa:** `start.bat` par double-click karein (Mac: `start.sh`). Bot pehle khud update hoga, phir link poochega. Link paste karein aur Enter dabayein.

**Ya terminal se:**
```
python bot.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```

**Kai videos ek saath:** `links.txt` mein har line par ek link likhein, phir:
```
python bot.py links.txt
```

**Ek dafa ke liye kuch badalna ho:**
```
python bot.py LINK --clips 5              (5 Shorts banao)
python bot.py LINK --lang french          (French mein)
python bot.py LINK --voice male           (larke ki awaaz)
python bot.py LINK --voice child          (bachche ki awaaz)
python bot.py LINK --layout face          (chehre par zoom)
python bot.py LINK --focus "paisa aur business"
python bot.py LINK --lang english --no-voice   (Vyro jaisi campaigns: English, AI awaaz ke baghair)
python bot.py --test-voice "Assalam o Alaikum, aaj ki baat suniye"
```

**Poori video download nahi hoti.** Bot pehle sirf subtitles (ya zaroorat ho to sirf audio) laata hai, AI viral moments chunta hai, phir sirf un clips ke chhote hisse download hote hain. 1 ghante ki video ho ya 3 ghante ki, download chand MB hi hota hai.

**D drive (ya kisi bhi folder) mein save karna:** `config.yaml` mein sab se neeche `paths:` ke andar likhein:
```
  output: D:/Shorts
```
(Folder na ho to bot khud bana dega.)

Tayyar Shorts **`output`** folder mein (ya jo folder aap ne chuna) milenge: har `.mp4` ke saath us ki `.txt` upload sheet hogi.

> Ek hi video dobara chalayein to bot **naye moments** chunega. Pehle wale clips `output/history.json` mein yaad rehte hain.

---

## 📲 Shorts phone par Telegram mein mangwana

Har Short tayyar hote hi aap ke Telegram par video aur alag message mein title/description aa jayenge. Phone se copy karke seedha YouTube app par upload kar sakte hain, ya WhatsApp par forward.

1. Phone par Telegram mein **@BotFather** search karein aur kholein → **START**.
2. Likhein `/newbot`. Bot ka naam likhein (jaise `Mere Shorts`), phir username likhein jo `bot` par khatam ho (jaise `hamza_shorts_bot`).
3. BotFather ek **token** dega (`123456789:ABC...`). Use copy karein. ⚠️ Ye kisi ko na dein.
4. Computer par `notepad .env` kholein, nayi line likhein: `TELEGRAM_BOT_TOKEN=yahan-token` aur Ctrl+S.
5. Telegram mein **apna naya bot** kholein (BotFather ke message mein link hota hai) aur **START** dabayein.
6. Computer par chalayein:
   ```
   python bot.py --telegram-setup
   ```
   Telegram par "✅ Shorts Bot jur gaya!" aa jaye to kaam ho gaya.

**"Computer se Telegram tak rabta nahi hua" aaye to:** Pakistan mein kai internet companies computer par Telegram rok deti hain (phone ki app phir bhi chalti hai). Hal:
- **Behtareen (ek dafa, muft, VPN ke baghair): apna Telegram relay.** Neeche "Telegram relay" dekhein.
- **Ya:** computer par muft **Cloudflare WARP** (https://one.one.one.one) install karke **Connect** karein, phir bot chalayein.
- Ya agar aap ke paas proxy hai: `.env` mein `TELEGRAM_PROXY=socks5h://127.0.0.1:1080` (apne proxy ka pata) likhein.
- Check: browser mein https://api.telegram.org kholein. Page khul jaye to bot bhi chal jayega.

Kisi dafa Telegram par na bhejna ho: `python bot.py LINK --no-telegram`. Hamesha band karna ho: `config.yaml` mein `telegram.send: false`.

### Telegram relay (apna muft Cloudflare Worker)
Ye aap ka apna chhota sa server hai jo bot ke messages Telegram tak pahunchata hai. Koi aur is ke beech nahi hota.
1. https://dash.cloudflare.com/sign-up par muft account banayein (email se).
2. Baayen menu mein **Workers & Pages** → **Create** → **Create Worker** (ya "Start with Hello World").
3. Naam rakhein, jaise `tg-relay` → **Deploy**.
4. **Edit code** dabayein. Wahan likha saara code mita dein aur is repo ki file `telegram-relay/worker.js` ka poora code paste karein → **Deploy**.
5. Upar aap ke Worker ka pata likha hoga, jaise `https://tg-relay.aapkanaam.workers.dev`. Use browser mein kholein: "Shorts Bot relay chal raha hai." aana chahiye.
6. `notepad .env` mein nayi line likhein:
   ```
   TELEGRAM_API_URL=https://tg-relay.aapkanaam.workers.dev
   ```
   Ctrl+S karein, phir `python bot.py --telegram-setup` chalayein.

## 📱 Telegram se bot chalana (phone se commands)

Computer par **`telegram.bat`** par double-click karein aur window khuli rehne dein. Ab phone ke Telegram se:

| Command | Kaam |
|---|---|
| `/nasa` | NASA ki nayi video se Short (`/nasa 3` = 3 Shorts) |
| `/jpl` `/goddard` `/whitehouse` | Doosre mehfooz (public domain) channels |
| `/cc business podcast` | Creative Commons videos mein se, topic ke hisaab se |
| `/link https://...` | Apna link (sirf Creative Commons) |
| `/link https://... ijazat` | Ijazat wali video (zimmedari aap ki) |
| `/sources` | Channels ki list |
| `/help` | Saari commands |

**Short badalna:** Short ke kisi message par **reply** karein (reply na karein to aakhri Short badlega):
- `/title naya title`, `/desc nayi description`, `/thumb naya thumbnail text`
- Ya seedha likhein: *"title aur chatpata karo"*, *"thumbnail par SHOCKING likho"*. AI khud badal dega.

Channels `sources.yaml` mein hain. Apne channels `sources.local.yaml` mein add karein (update se nahi badalti).
⚠️ Computer on aur `telegram.bat` chalti honi chahiye. Sirf aap ki Telegram chat ke messages mane jate hain.

## 🛡️ Copyright strike se bachao

- Bot har Short ka record **`shorts-log.csv`** (output folder mein, Excel mein khulta hai) mein rakhta hai: kis channel ki kis video se bana. Agar kisi creator ki shikayat aaye, to unhi ke saare Shorts foran dhoond kar YouTube se hata sakte hain.
- YouTube kabhi kabhi **"scheduled takedown"** bhejta hai, jis mein **7 din** milte hain. In 7 din mein video delete kar dein to **strike nahi lagti**. Is liye YouTube ki email aur YouTube Studio → **Copyright** wala hissa roz dekhein.
- Phone par YouTube Studio app install karke notifications on rakhein.

## 🛠️ Settings badalna (`config.yaml`)

`config.yaml` ko Notepad se kholein. Har setting ke saath Urdu mein samjhaya gaya hai. Aam settings:

| Kya badalna hai | Setting |
|---|---|
| Channel ka naam | `channel.name` |
| Zubaan | `language.target: urdu` → `english`, `french`, `german` ... |
| Title kis tarah likha jaye | `language.title_style: roman` / `target` / `english` |
| Larki / larka / bachche ki awaaz | `voice.gender: female` / `male` / `child` |
| Bachche ki awaaz kitni patli ho | `voice.child_pitch: "+45Hz"` |
| Awaaz ki raftar | `voice.rate: "+5%"` |
| Har video se kitne Shorts | `clips.per_video: 3` |
| Clip ki lambai | `clips.min_seconds` / `clips.max_seconds` |
| Video ka andaaz | `video.layout: blur` (2-3 log) / `face` (1 banda) |
| Captions ka size/rang | `captions.*` |
| Music ki awaaz | `music.volume` |

### Behtar awaaz (ElevenLabs, paid)
1. https://elevenlabs.io par account banayein. Voice Library se larki, larke aur bachche ki pasand ki awaazon ke **Voice ID** copy karein.
2. `.env` mein `ELEVENLABS_API_KEY=...` likhein.
3. `config.yaml` mein `voice.engine: elevenlabs` likhein, aur `voice.elevenlabs_voices` ke neeche `female`, `male`, `child` ke saamne IDs paste karein.

> **Bachche ki awaaz ke baare mein:** muft (Edge) engine mein asli bachche ki awaaz sirf English mein hai. Baaqi zubaanon mein bot larki ki awaaz ko patla aur thora tez karke bachche jaisi awaaz banata hai. Bilkul asli bachche ki awaaz chahiye to ElevenLabs mein child voice ka ID daal dein.

---

## ✅ Strike se bachao aur monetization: zaroori qawaid

- Bot sirf **ijazat wali** videos ke liye hai. Creative Commons video ho to bot khud pehchan leta hai. Warna aap se poochta hai ke ijazat hai ya nahi. Ijazat ke saboot (Whop campaign, email, DM ka screenshot) sambhal kar rakhein.
- `music` folder mein **sirf copyright-free** music daalein (YouTube Studio → Audio Library).
- Upload se pehle **har Short khud dekhein**. AI kabhi kabhi translation mein galti kar sakta hai.
- Roz **2-3 Shorts** kaafi hain. Bahut zyada ek jaisi videos "mass-produced" lag sakti hain.
- Kabhi kabhi apni **asli awaaz** mein bhi hook/outro record karein. Is se channel zyada original lagta hai.

---

## ❓ Masle aur hal

| Masla | Hal |
|---|---|
| `Awaaz nahi bani (edge-tts) ... 403` | Microsoft ki muft awaaz kabhi kabhi ruk jati hai. Bot khud Google ki backup awaaz laga deta hai. Microsoft wali hi chahiye to: `python -m pip install -U edge-tts`, aur computer ka waqt/date sahi karein (Settings → Time → Sync now) |
| `ffmpeg nahi mila` | Step 2 dobara karein, phir terminal band karke kholein |
| `ANTHROPIC_API_KEY ... set nahi` | `.env` file ka naam check karein (`.env.txt` nahi hona chahiye) |
| `credit khatam` | console.anthropic.com → Billing |
| Video download nahi hoti | `pip install -U yt-dlp` chalayein (YouTube aksar badalta rehta hai) |
| Captions mein dabbe (□□□) dikhte hain | `fonts` folder delete karein, bot dobara download karega |
| Video ke subtitles nahi hain | Bot khud sun kar subtitles banata hai (Whisper). Computer par na chale to Groq se, neeche "Subtitles kaise bante hain" dekhein |
| Bahut dheema hai | Video ke YouTube subtitles na hon to Whisper chalta hai. `transcript.whisper_model: base` kar dein |

---

### Subtitles kaise bante hain
1. Video ke **YouTube subtitles** hon to bot wohi le leta hai (sab se tez).
2. Na hon to bot **khud sunta hai (Whisper)**, aap ke computer par, muft. Pehli dafa model download hota hai, aur lambi video mein waqt lagta hai.
3. Agar Whisper computer par na chale (jaise Windows ka "Smart App Control" rok de), to bot **Groq** (internet service) se subtitles banwata hai:
   - https://console.groq.com par muft account banayein → **API Keys → Create API Key**.
   - `notepad .env` kholein, nayi line likhein: `GROQ_API_KEY=gsk_...` aur Ctrl+S.
   - Free plan mein ghante ki limit hai. Lambi video par bot khud ruk ruk kar poora kar leta hai.

`config.yaml` mein `transcript.engine` se chun sakte hain: `auto` (default), `local` ya `groq`.

## 🧩 Bot ke hisse (badalne ke liye)

| File | Kaam |
|---|---|
| `bot.py` | Shuru se aakhir tak sab chalata hai |
| `shorts_bot/download.py` | Video, title, channel, license, YouTube subtitles |
| `shorts_bot/transcribe.py` | Baat-cheet ko text mein badalna (YouTube subtitles ya Whisper) |
| `shorts_bot/planner.py` | AI se viral moments chunwana, translation, hook/outro script, title |
| `shorts_bot/voice.py` | AI awaaz (Edge muft / ElevenLabs) |
| `shorts_bot/render.py` | Video editing: 9:16, captions, hook/outro, music |
| `shorts_bot/languages.py` | Zubaanein, awaazein, fonts. Nayi zubaan yahan add hoti hai |
