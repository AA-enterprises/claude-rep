"""
SHORTS BOT: podcast se viral Shorts banane wala bot.

Istemal:
    python bot.py "https://www.youtube.com/watch?v=XXXX"
    python bot.py links.txt                 (har line par ek link)
    python bot.py video.mp4                 (computer par pari video)
    python bot.py LINK --series 3           (ek scene: Part 1, 2, 3 - har ek ~50 second)
    python bot.py LINK --clips 5 --lang french --voice male   (female / male / child)
    python bot.py --check                   (sab kuch theek install hai?)
    python bot.py --test-voice "Assalam o Alaikum"
    python bot.py --telegram-setup          (Shorts phone par Telegram mein mangwayein)
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from shorts_bot import config as config_mod
from shorts_bot import languages
from shorts_bot.util import BotError, console_utf8, duration, read_json, say, slug, step, write_json

HERE = Path(__file__).resolve().parent


def is_creative_commons(src: dict) -> bool:
    return "creative commons" in (src.get("license") or "").lower()


def confirm_permission(src: dict, cfg: dict, assume_yes: bool, strict: bool = False) -> str:
    if is_creative_commons(src):
        say("  ✅ Ye video Creative Commons hai (credit ke saath reuse allowed).")
        return "Creative Commons (CC BY)"
    if not src.get("url"):
        return "Local file (aap ki apni ya permission wali)"
    if assume_yes or not cfg["safety"]["ask_permission"]:
        return "User ne ijazat confirm ki"
    if strict:  # Telegram se: poochh nahi sakte, is liye sirf CC chalao
        raise BotError("Ye video Creative Commons nahi, is liye chhor di.")
    say("\n  ⚠️  Ye video Creative Commons NAHI hai.")
    say(f"     Channel: {src.get('channel')}")
    say("     Bina ijazat clips lagane se copyright strike aa sakti hai.")
    ans = input("     Kya aap ke paas is ki ijazat hai (Whop campaign / email / DM)? [haan/nahi]: ")
    if ans.strip().lower() not in ("haan", "han", "h", "yes", "y", "ha", "ji"):
        raise BotError("Theek hai, ye video chhor di. Sirf ijazat wali videos use karein.")
    return "User ne ijazat confirm ki"


def write_upload_sheet(path: Path, clip: dict, src: dict, permission: str, cfg: dict):
    tags = " ".join(h if h.startswith("#") else f"#{h}" for h in clip.get("hashtags", []))
    credit = f"Credit: {src.get('channel') or 'Original creator'}"
    if src.get("url"):
        credit += f" - {src['url']}"
    desc = f"{clip['description'].strip()}\n\n{credit}\n{tags}\n#shorts"
    text = f"""========== UPLOAD SHEET ==========
TITLE (copy karein):
{clip['title'].strip()}

DESCRIPTION (copy karein):
{desc}

---------- Sirf aap ke liye ----------
Category      : {clip.get('category', '')}
Viral kyun    : {clip.get('why_it_will_go_viral', '')}
Original video: {src.get('title', '')}
Clip ka waqt  : {clip['start']:.1f}s - {clip['end']:.1f}s
Ijazat        : {permission}
Bana          : {datetime.now():%Y-%m-%d %H:%M}

Upload se pehle check:
[ ] Video poori dekhi, captions aur awaaz theek hain
[ ] Title aur description paste kiye
[ ] Audience: "No, it's not made for kids"
"""
    path.write_text(text, encoding="utf-8")
    return clip["title"].strip(), desc


def fit_length(clip: dict, cfg: dict, voices: dict) -> dict:
    """User ne "30 sec" kaha to poori video (intro + clip + outro) ~30 second ki ho:
    clip zyada lamba ho to aakhri lines kaato."""
    c = cfg["clips"]
    total = c.get("total_seconds") or (c["part_seconds"] if c["mode"] == "series" else 0)
    if not total:
        return clip
    extra = sum(duration(v) + 0.35 for v in voices.values() if v)
    budget = total + 1.5 - extra
    lines = list(clip["lines"])
    while len(lines) > 2 and lines[-1]["end"] + 0.35 - clip["start"] > budget:
        lines.pop()
    if len(lines) == len(clip["lines"]):
        return clip
    say(f"  Lambai {total} second ke andar rakhne ke liye clip chhota kiya.")
    return dict(clip, lines=lines, end=lines[-1]["end"])


def shift_clip(clip: dict, offset: float) -> dict:
    """Sirf clip wala hissa download hua ho to saare waqt us hisse ke hisaab se karo."""
    if not offset:
        return clip
    out = dict(clip, start=clip["start"] - offset, end=clip["end"] - offset)
    out["lines"] = [dict(ln, start=ln["start"] - offset, end=ln["end"] - offset)
                    for ln in clip["lines"]]
    return out


def log_short(cfg: dict, video: Path, title: str, src: dict, permission: str):
    """Har Short ka record: kis creator ki kis video se bana. Kabhi kisi creator ki
    shikayat aaye to unhi ke saare Shorts foran dhoond kar hata sakein."""
    import csv

    path = cfg["paths"]["output"] / "shorts-log.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["Date", "Short file", "Title", "Source channel", "Source video",
                        "Source link", "Ijazat"])
        w.writerow([f"{datetime.now():%Y-%m-%d %H:%M}", video.name, title,
                    src.get("channel", ""), src.get("title", ""), src.get("url", ""), permission])


def send_to_telegram(video: Path, title: str, desc: str, thumb, cfg: dict, note: str = ""):
    from shorts_bot import telegram

    if not cfg["telegram"]["send"] or not telegram.enabled():
        return
    say("  📲 Telegram par bhej raha hoon...")
    try:
        telegram.send_short(video, title, desc, thumb)
        if note:
            telegram.send_message(note)
        say("  📲 Telegram par bhej diya.")
    except BotError as e:  # Bhejna fail ho to bhi Short computer par mehfooz hai
        say(f"  ⚠️  Telegram par nahi gaya: {e}")


def process(source: str, cfg: dict, args, on_short=None, permission: str = None) -> list:
    from shorts_bot import download, planner, render, transcribe, voice

    step("1/5  Video aur maloomat la raha hoon")
    src = download.fetch(source, cfg)
    say(f"  Title  : {src.get('title', '')[:80]}")
    if src.get("channel"):
        say(f"  Channel: {src['channel']}")
    if not permission:
        permission = confirm_permission(src, cfg, args.yes, strict=getattr(args, "strict", False))

    step("2/5  Baat-cheet ko text mein badal raha hoon")
    tr = transcribe.get_transcript(src, cfg)
    say(f"  {len(tr['segments'])} lines mili (zubaan: {tr['language']})")

    step("3/5  AI viral moments chun raha hai")
    hist_path = cfg["paths"]["output"] / "history.json"
    history = read_json(hist_path, {"videos": {}, "hooks": []})
    used = history["videos"].get(src["id"], [])
    # Pichhli dafa AI ne plan bana diya tha lekin baad mein kuch fail hua: wahi plan
    # dobara use karo (AI ke paise dobara nahi lagte). Mukammal hone par mit jata hai.
    c = cfg["clips"]
    shape = (f"series{c['parts']}x{c['part_seconds']}" if c["mode"] == "series"
             else f"single{c['per_video']}x{c['min_seconds']}-{c['max_seconds']}")
    lang = cfg["language"]
    key = (f"{lang['target']}-{lang.get('voice')}-{lang.get('narration')}-{cfg['thumbnail'].get('language')}"
           f"-{cfg['voice']['gender']}-{shape}-{c['focus']}" + ("-dub2" if cfg["dub"]["enabled"] else ""))
    plan_path = src["dir"] / f"plan-{slug(key, 60)}.json"
    plan = read_json(plan_path)
    if plan and plan.get("clips"):
        plan["clips"] = [c for c in plan["clips"]
                         if [c["start_index"], c["end_index"]] not in used]
    if plan and plan.get("clips"):
        say("  Pichhli dafa ka AI plan mil gaya (dobara paise nahi lagenge).")
    else:
        plan = planner.make_plan(src, tr, cfg, used, history["hooks"])
        write_json(plan_path, plan)
    for k, c in enumerate(plan["clips"], 1):
        say(f"  {k}. [{c['category']}] {c['title']}")

    outputs = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for k, clip in enumerate(plan["clips"], 1):
        step(f"4/5  Short {k}/{len(plan['clips'])}: awaaz bana raha hoon")
        cwork = src["dir"] / f"clip-{clip['start_index']}-{clip['end_index']}"
        cwork.mkdir(parents=True, exist_ok=True)
        voices = {}
        voice.USED.clear()
        if cfg["clips"]["hook"] and clip["hook_voice"].strip():
            voices["hook"] = voice.speak(clip["hook_voice"], cwork / "hook",
                                         voice.styled(cfg, cfg["voice"]["gender"]))
        if cfg["clips"]["outro"] and clip["outro_voice"].strip():
            og = cfg["voice"].get("outro_gender") or cfg["voice"]["gender"]
            voices["outro"] = voice.speak(clip["outro_voice"], cwork / "outro", voice.styled(cfg, og))
        for key, cap in (("hook", 3.5), ("outro", 4.5)):  # Intro/outro lambe na hon
            if voices.get(key):
                voices[key] = voice.fit(voices[key], cap)
        clip = fit_length(clip, cfg, voices)

        step(f"5/5  Short {k}/{len(plan['clips'])}: video edit ho rahi hai")
        media, offset = download.clip_media(src, clip, cfg)
        csrc, cclip = dict(src, video=media), shift_clip(clip, offset)
        name = f"{stamp}_{slug(src.get('title', 'video'), 25)}_{k}"
        final = cfg["paths"]["output"] / f"{name}.mp4"
        render.render_short(csrc, cclip, voices, cfg, cwork, final, tr["language"])
        title, desc = write_upload_sheet(final.with_suffix(".txt"), clip, src, permission, cfg)
        thumb = None
        if cfg["thumbnail"]["make"]:
            say("  Thumbnail bana raha hoon...")
            thumb = render.make_thumbnail(csrc, cclip, cfg, cwork, final.with_suffix(".jpg"),
                                          tr["language"])
        note = voice.report()
        if note:
            say("  " + note)
        say(f"  ✅ Tayyar: {final}")
        outputs.append(final)
        log_short(cfg, final, title, src, permission)
        if on_short:
            on_short({"video": str(final), "txt": str(final.with_suffix(".txt")),
                      "thumb": str(thumb) if thumb else "", "title": title, "description": desc,
                      "thumbnail_text": clip.get("thumbnail_text") or clip["hook_on_screen"],
                      "media": str(media), "clip": cclip, "lang": tr["language"],
                      "cwork": str(cwork), "source": src.get("title", ""), "voice_note": note})
        else:
            send_to_telegram(final, title, desc, thumb, cfg, note)

        history["videos"].setdefault(src["id"], []).append([clip["start_index"], clip["end_index"]])
        history["hooks"] = (history["hooks"] + [clip["hook_voice"]])[-60:]
        write_json(hist_path, history)
    plan_path.unlink(missing_ok=True)
    return outputs


def git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def version_text() -> str:
    if not shutil.which("git"):
        return "version maloom nahi (Git install nahi)"
    r = git("log", "-1", "--format=%h (%cd)", "--date=format:%d-%m-%Y %H:%M")
    return r.stdout.strip() if r.returncode == 0 else "version maloom nahi (Git se download nahi hua)"


def self_update(quiet: bool = False):
    """GitHub se naya code lao (git pull) aur naye packages install karo."""
    if not shutil.which("git"):
        if not quiet:
            say("❌ Git install nahi hai. README ka 'Khud-ba-khud update' hissa dekhein.")
        return
    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        if not quiet:
            say("❌ Ye folder Git se download nahi hua. README ka 'Khud-ba-khud update' hissa dekhein.")
        return None
    before = git("rev-parse", "HEAD").stdout.strip()
    say("🔄 Naya version check ho raha hai...")
    # YouTube har hafte badalta hai: yt-dlp hamesha sab se naya rakho
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp[default]", "edge-tts"],
                   capture_output=True)
    r = git("pull", "--ff-only", "-q")
    if r.returncode != 0:
        say("⚠️  Update nahi hua (internet?). Purane version se chal raha hai.")
        if not quiet:
            say(r.stderr.strip()[-500:])
        return None
    after = git("rev-parse", "HEAD").stdout.strip()
    if before == after:
        say(f"✅ Bot pehle se naya hai: {version_text()}")
        return ""
    say("📦 Naye packages check ho rahe hain...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(HERE / "requirements.txt")])
    say(f"✅ Update ho gaya! Naya version: {version_text()}")
    log = git("log", "--format=  • %s", f"{before}..{after}")
    if log.stdout.strip():
        say("Kya naya hai:\n" + log.stdout.rstrip())
    return log.stdout.rstrip() or "naya version"


def update_available() -> bool:
    """GitHub par naya version hai? (sirf dekhta hai, kuch badalta nahi)"""
    if not shutil.which("git") or git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return False
    if git("fetch", "-q").returncode != 0:
        return False
    r = git("rev-list", "--count", "HEAD..@{u}")
    return r.returncode == 0 and r.stdout.strip() not in ("", "0")


def check(cfg: dict):
    ok = True
    say(f"Python {sys.version.split()[0]}  |  Bot version: {version_text()}")
    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        say(f"{'✅' if found else '❌'} {tool}: {found or 'NAHI MILA (README Step 2)'}")
        ok &= bool(found)
    from shorts_bot.transcribe import _import_whisper
    try:
        _import_whisper()
        say("✅ Whisper (subtitles na hon to bot computer par khud sun kar banayega)")
        whisper_ok = True
    except Exception as e:
        first = (str(e).strip().splitlines() or [type(e).__name__])[0]
        say(f"⚠️  Whisper computer par nahi chal raha: {first[:150]}")
        whisper_ok = False
    deno = shutil.which("deno")
    say(f"{'✅' if deno else '⚠️ '} Deno {'mil gaya' if deno else 'nahi mila (YouTube ke liye zaroori ho sakta hai): winget install DenoLand.Deno'}")
    cookies = HERE / "cookies.txt"
    say(f"{'✅' if cookies.exists() else 'ℹ️ '} cookies.txt {'mil gayi' if cookies.exists() else 'nahi (sirf YouTube rokne par zaroori)'}")
    for mod in ("anthropic", "yt_dlp", "edge_tts", "cv2", "yaml"):
        try:
            __import__(mod)
            say(f"✅ {mod}")
        except Exception as e:  # ImportError, ya Windows par DLL ka masla (OSError)
            first = (str(e).strip().splitlines() or [type(e).__name__])[0]
            say(f"❌ {mod}: {first[:200]}")
            if "dll" in str(e).lower() or isinstance(e, OSError):
                say("   Hal: winget install Microsoft.VCRedist.2015+.x64  (phir naya terminal kholein)")
            else:
                say("   Hal: python -m pip install -r requirements.txt")
            ok = False
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key.startswith("sk-ant-") and "yahan" not in key:
        say(f"✅ ANTHROPIC_API_KEY set hai (sk-ant-...{key[-4:]})")
    else:
        ok = False
        if not key:
            say("❌ ANTHROPIC_API_KEY nahi mili.")
        elif "yahan" in key:
            say("❌ ANTHROPIC_API_KEY: .env mein abhi tak namoona text hai, asli key paste karke Ctrl+S karein.")
        else:
            say("❌ ANTHROPIC_API_KEY ajeeb hai (sk-ant-... se shuru honi chahiye).")
        say(f"   {describe_env()}")
        say('   Hal: "notepad .env" chalayein, ek line likhein: ANTHROPIC_API_KEY=sk-ant-... aur Ctrl+S.')
    groq = os.environ.get("GROQ_API_KEY", "")
    if groq:
        say("✅ GROQ_API_KEY set hai (backup subtitles)")
    elif whisper_ok:
        say("ℹ️  GROQ_API_KEY nahi (zaroori nahi, sirf backup subtitles ke liye)")
    else:
        say("⚠️  GROQ_API_KEY bhi nahi: jin videos ke YouTube subtitles na hon, un ke subtitles nahi banenge.")
        say("   Hal: console.groq.com se muft key lein aur .env mein GROQ_API_KEY=... likhein (README).")
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        say("✅ Telegram jura hua hai (Shorts phone par aayenge)")
    elif os.environ.get("TELEGRAM_BOT_TOKEN"):
        say("⚠️  Telegram token hai, lekin chat nahi jurri. Chalayein: python bot.py --telegram-setup")
    else:
        say("ℹ️  Telegram nahi jura (zaroori nahi). README ka Telegram wala hissa dekhein.")
    say(f"ℹ️  Shorts yahan save honge: {cfg['paths']['output']}")
    lang = languages.get(cfg["language"]["target"])
    narr = languages.narration(cfg)
    say(f"ℹ️  Subtitles: {lang['key']} + asal  |  Awaaz: {languages.voice(cfg)['key']}  |  Title/text: {narr['key']}  |  "
        f"Thumbnail: {languages.thumbnail(cfg)['key']}  |  "
        f"Awaaz kis ki: {cfg['voice']['gender']}  |  Style: {cfg['clips']['mode']}")
    say("\nSab theek hai! ✅" if ok else "\nUpar ❌ wali cheezein theek karein.")


def env_files() -> list:
    """.env ke saath Notepad ki ghalti se bani '.env.txt' bhi dekho."""
    return [p for p in (HERE / ".env", HERE / ".env.txt") if p.exists()]


def read_env_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):  # Notepad "UTF-16" mein save hui ho
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", "replace")


def load_env_file():
    """.env se API keys parho (KEY=value), agar pehle se set na hon."""
    for path in env_files():
        for line in read_env_text(path).splitlines():
            line = line.strip().removeprefix("export ").strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
            elif line.startswith("sk-ant-"):  # Sirf key paste hui, naam mit gaya
                k, v = "ANTHROPIC_API_KEY", line
            else:
                continue
            k, v = k.strip(), v.strip().strip('"').strip("'").strip()
            if k and v and not os.environ.get(k):
                os.environ[k] = v


def describe_env() -> str:
    """Key dikhaye baghair batao ke .env mein kya mila."""
    files = env_files()
    if not files:
        return f".env file nahi mili. Is folder mein honi chahiye: {HERE}"
    path = files[0]
    lines = [ln.strip() for ln in read_env_text(path).splitlines() if ln.strip() and not ln.strip().startswith("#")]
    names = [ln.split("=", 1)[0].strip() for ln in lines if "=" in ln]
    return f"{path.name} mili ({len(lines)} line), is mein ye naam hain: {', '.join(names) or 'koi nahi'}"


def main():
    console_utf8()
    load_env_file()
    p = argparse.ArgumentParser(description="Podcast se Shorts banane wala bot")
    p.add_argument("sources", nargs="*", help="YouTube link, video file, ya links.txt")
    p.add_argument("--clips", type=int, help="Har video se kitne Shorts (alag alag moments)")
    p.add_argument("--series", type=int, metavar="N", help="Ek scene ke N parts (Part 1, 2, 3...)")
    p.add_argument("--seconds", type=int, help="Series mein har part kitne second ka (jaise 50)")
    p.add_argument("--lang", help="Subtitles ki zubaan: urdu, english, french, german, hindi, arabic ...")
    p.add_argument("--narration", help="Awaaz/title/thumbnail ki zubaan (english, urdu, same ...)")
    p.add_argument("--voice", choices=["female", "male", "child"], help="Awaaz: larki, larka ya bachcha")
    p.add_argument("--layout", choices=["blur", "face"], help="Video ka andaaz")
    p.add_argument("--focus", help='Topic, jaise "paisa aur business"')
    p.add_argument("--no-dub", action="store_true", help="Asal awaaz rakho, Urdu dubbing mat karo")
    p.add_argument("--no-voice", action="store_true",
                   help="AI awaaz (hook/outro) ke baghair, sirf clip + captions (jaise Vyro briefs)")
    p.add_argument("--yes", action="store_true", help="Ijazat ka sawal mat poochho (ijazat pakki ho)")
    p.add_argument("--config", default=str(HERE / "config.yaml"))
    p.add_argument("--check", action="store_true", help="Installation check karo")
    p.add_argument("--test-voice", metavar="TEXT", help="Sirf awaaz test karo")
    p.add_argument("--telegram-setup", action="store_true", help="Telegram jorro (README dekhein)")
    p.add_argument("--no-telegram", action="store_true", help="Is dafa Telegram par mat bhejo")
    p.add_argument("--update", action="store_true", help="GitHub se naya version lao")
    p.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--gemini-key", metavar="KEY", help="Insaan jaisi awaaz (Gemini) ki key .env mein rakho")
    p.add_argument("--chirp-key", metavar="KEY", help="Chirp 3 HD (Google Cloud Text-to-Speech) ki key .env mein rakho")
    p.add_argument("--ask", action="store_true", help="Link poochho (start.bat ke liye)")
    p.add_argument("--version", action="store_true", help="Bot ka version dikhao")
    p.add_argument("--telegram", action="store_true",
                   help="Telegram se commands suno (/nasa, /cc, /link, /title ...)")
    args = p.parse_args()
    if args.update:
        return self_update(args.quiet)
    if args.version:
        return say(f"Bot version: {version_text()}")
    if args.ask and not args.sources:
        say("=" * 46 + "\n           SHORTS BOT\n" + "=" * 46)
        link = input("YouTube link paste karein (ya links.txt) aur Enter dabayein: ").strip().strip('"')
        if not link:
            return
        args.sources = [link]

    try:
        cfg = config_mod.load(Path(args.config))
        if args.clips:
            cfg["clips"]["per_video"] = args.clips
            cfg["clips"]["mode"] = "single"
        if args.series:
            cfg["clips"]["parts"] = args.series
            cfg["clips"]["mode"] = "series"
        if args.seconds:
            cfg["clips"]["part_seconds"] = cfg["clips"]["total_seconds"] = args.seconds
        if args.lang:
            cfg["language"]["target"] = args.lang
        if args.narration:
            cfg["language"]["narration"] = args.narration
        if args.voice:
            cfg["voice"]["gender"] = cfg["voice"]["outro_gender"] = args.voice
            cfg["voice"]["edge_voice"] = ""
        if args.layout:
            cfg["video"]["layout"] = args.layout
        if args.focus:
            cfg["clips"]["focus"] = args.focus
        if args.no_dub:
            cfg["dub"]["enabled"] = False
        if args.no_voice:
            cfg["dub"]["enabled"] = False
            cfg["clips"]["hook"] = False
            cfg["clips"]["outro"] = False

        if args.no_telegram:
            cfg["telegram"]["send"] = False
        if args.check:
            return check(cfg)
        if args.chirp_key:
            from shorts_bot import telegram as _tg
            from shorts_bot import voice as _v
            key = args.chirp_key.strip().strip('"').strip("'")
            res = _v.check_google_key(key)
            if res.get("chirp") is not True:
                return say(f"❌ Chirp key nahi chali: {res.get('chirp')}")
            _tg._write_env(HERE / ".env", "GOOGLE_TTS_API_KEY", key)
            return say("✅ Chirp key .env mein rakh di. Ab: python bot.py --telegram  (phir Telegram par /awaaz)")
        if args.gemini_key:
            from shorts_bot import telegram as _tg
            key = args.gemini_key.strip().strip('"').strip("'")
            _tg._write_env(HERE / ".env", "GEMINI_API_KEY", key)
            os.environ["GEMINI_API_KEY"] = key
            return say("✅ Gemini key .env mein rakh di. Ab: python bot.py --telegram  (phir Telegram par /awaaz)")
        if args.telegram_setup:
            from shorts_bot import telegram
            return telegram.setup(HERE / ".env")
        if args.telegram:
            from shorts_bot.util import require_ffmpeg as _rf
            from shorts_bot import tgbot
            _rf()
            if tgbot.run(cfg, process, self_update, update_available) == "restart":
                # Naya code: bot dobara chalao (isi window mein)
                raise SystemExit(subprocess.call([sys.executable, str(HERE / "bot.py"), "--telegram"]))
            return
        from shorts_bot.util import require_ffmpeg
        require_ffmpeg()
        if args.test_voice:
            from shorts_bot import voice
            out = cfg["paths"]["output"] / "voice-test"
            out.parent.mkdir(parents=True, exist_ok=True)
            wav = voice.speak(args.test_voice, out, voice.styled(cfg, cfg["voice"]["gender"]))
            return say(f"✅ Awaaz bani: {wav}\n{voice.report()}")

        sources = []
        for s in args.sources:
            if s.lower().endswith(".txt") and Path(s).exists():
                sources += [ln.strip() for ln in Path(s).read_text(encoding="utf-8").splitlines()
                            if ln.strip() and not ln.strip().startswith("#")]
            else:
                sources.append(s)
        if not sources:
            p.print_help()
            return
        cfg["paths"]["output"].mkdir(parents=True, exist_ok=True)
    except BotError as e:
        say(f"\n❌ {e}")
        sys.exit(1)

    made, failed = [], []
    for s in sources:
        say(f"\n{'=' * 60}\n🎬 {s}\n{'=' * 60}")
        try:
            made += process(s, cfg, args)
        except BotError as e:
            say(f"\n❌ {e}")
            failed.append(s)
        except Exception as e:  # Ghair-mutawaqqa ghalti: poori tafseel file mein, agli video jaari
            import traceback
            log = cfg["paths"]["work"] / "error-log.txt"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M} {s}\n{traceback.format_exc()}")
            say(f"\n❌ Bot mein ghalti: {type(e).__name__}: {str(e)[:300]}")
            say(f"   Poori tafseel: {log}  (ye file developer ko bhejein)")
            failed.append(s)
        except KeyboardInterrupt:
            say("\nRok diya gaya.")
            break
    say(f"\n{'=' * 60}")
    say(f"🎉 {len(made)} Shorts tayyar. Folder: {cfg['paths']['output']}")
    say("Har Short ke saath .txt file mein title/description hai. Upload se pehle video zaroor dekhein.")
    if failed:
        say(f"⚠️  {len(failed)} video(s) mein masla aaya: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
