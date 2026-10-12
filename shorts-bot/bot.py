"""
SHORTS BOT: podcast se viral Shorts banane wala bot.

Istemal:
    python bot.py "https://www.youtube.com/watch?v=XXXX"
    python bot.py links.txt                 (har line par ek link)
    python bot.py video.mp4                 (computer par pari video)
    python bot.py LINK --clips 5 --lang french --voice male   (female / male / child)
    python bot.py --check                   (sab kuch theek install hai?)
    python bot.py --test-voice "Assalam o Alaikum"
    python bot.py --telegram-setup          (Shorts phone par Telegram mein mangwayein)
"""

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from shorts_bot import config as config_mod
from shorts_bot import languages
from shorts_bot.util import BotError, console_utf8, read_json, say, slug, step, write_json

HERE = Path(__file__).resolve().parent


def is_creative_commons(src: dict) -> bool:
    return "creative commons" in (src.get("license") or "").lower()


def confirm_permission(src: dict, cfg: dict, assume_yes: bool) -> str:
    if is_creative_commons(src):
        say("  ✅ Ye video Creative Commons hai (credit ke saath reuse allowed).")
        return "Creative Commons (CC BY)"
    if not src.get("url"):
        return "Local file (aap ki apni ya permission wali)"
    if assume_yes or not cfg["safety"]["ask_permission"]:
        return "User ne ijazat confirm ki"
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


def shift_clip(clip: dict, offset: float) -> dict:
    """Sirf clip wala hissa download hua ho to saare waqt us hisse ke hisaab se karo."""
    if not offset:
        return clip
    out = dict(clip, start=clip["start"] - offset, end=clip["end"] - offset)
    out["lines"] = [dict(ln, start=ln["start"] - offset, end=ln["end"] - offset)
                    for ln in clip["lines"]]
    return out


def send_to_telegram(video: Path, title: str, desc: str, thumb, cfg: dict):
    from shorts_bot import telegram

    if not cfg["telegram"]["send"] or not telegram.enabled():
        return
    say("  📲 Telegram par bhej raha hoon...")
    try:
        telegram.send_short(video, title, desc, thumb)
        say("  📲 Telegram par bhej diya.")
    except BotError as e:  # Bhejna fail ho to bhi Short computer par mehfooz hai
        say(f"  ⚠️  Telegram par nahi gaya: {e}")


def process(source: str, cfg: dict, args) -> list:
    from shorts_bot import download, planner, render, transcribe, voice

    step("1/5  Video aur maloomat la raha hoon")
    src = download.fetch(source, cfg)
    say(f"  Title  : {src.get('title', '')[:80]}")
    if src.get("channel"):
        say(f"  Channel: {src['channel']}")
    permission = confirm_permission(src, cfg, args.yes)

    step("2/5  Baat-cheet ko text mein badal raha hoon")
    tr = transcribe.get_transcript(src, cfg)
    say(f"  {len(tr['segments'])} lines mili (zubaan: {tr['language']})")

    step("3/5  AI viral moments chun raha hai")
    hist_path = cfg["paths"]["output"] / "history.json"
    history = read_json(hist_path, {"videos": {}, "hooks": []})
    used = history["videos"].get(src["id"], [])
    plan = planner.make_plan(src, tr, cfg, used, history["hooks"])
    for k, c in enumerate(plan["clips"], 1):
        say(f"  {k}. [{c['category']}] {c['title']}")

    outputs = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for k, clip in enumerate(plan["clips"], 1):
        step(f"4/5  Short {k}/{len(plan['clips'])}: awaaz bana raha hoon")
        cwork = src["dir"] / f"clip-{clip['start_index']}-{clip['end_index']}"
        cwork.mkdir(parents=True, exist_ok=True)
        voices = {}
        if cfg["clips"]["hook"] and clip["hook_voice"].strip():
            voices["hook"] = voice.speak(clip["hook_voice"], cwork / "hook", cfg)
        if cfg["clips"]["outro"] and clip["outro_voice"].strip():
            voices["outro"] = voice.speak(clip["outro_voice"], cwork / "outro", cfg)

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
        say(f"  ✅ Tayyar: {final}")
        outputs.append(final)
        send_to_telegram(final, title, desc, thumb, cfg)

        history["videos"].setdefault(src["id"], []).append([clip["start_index"], clip["end_index"]])
        history["hooks"] = (history["hooks"] + [clip["hook_voice"]])[-60:]
        write_json(hist_path, history)
    return outputs


def check(cfg: dict):
    ok = True
    say(f"Python {sys.version.split()[0]}")
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
    lang = languages.get(cfg["language"]["target"])
    say(f"ℹ️  Zubaan: {lang['key']}  |  Awaaz: {cfg['voice']['gender']}  |  Layout: {cfg['video']['layout']}")
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
    p.add_argument("--clips", type=int, help="Har video se kitne Shorts")
    p.add_argument("--lang", help="Target zubaan: urdu, english, french, german, hindi, arabic ...")
    p.add_argument("--voice", choices=["female", "male", "child"], help="Awaaz: larki, larka ya bachcha")
    p.add_argument("--layout", choices=["blur", "face"], help="Video ka andaaz")
    p.add_argument("--focus", help='Topic, jaise "paisa aur business"')
    p.add_argument("--yes", action="store_true", help="Ijazat ka sawal mat poochho (ijazat pakki ho)")
    p.add_argument("--config", default=str(HERE / "config.yaml"))
    p.add_argument("--check", action="store_true", help="Installation check karo")
    p.add_argument("--test-voice", metavar="TEXT", help="Sirf awaaz test karo")
    p.add_argument("--telegram-setup", action="store_true", help="Telegram jorro (README dekhein)")
    p.add_argument("--no-telegram", action="store_true", help="Is dafa Telegram par mat bhejo")
    args = p.parse_args()

    try:
        cfg = config_mod.load(Path(args.config))
        if args.clips:
            cfg["clips"]["per_video"] = args.clips
        if args.lang:
            cfg["language"]["target"] = args.lang
        if args.voice:
            cfg["voice"]["gender"] = args.voice
            cfg["voice"]["edge_voice"] = ""
        if args.layout:
            cfg["video"]["layout"] = args.layout
        if args.focus:
            cfg["clips"]["focus"] = args.focus

        if args.no_telegram:
            cfg["telegram"]["send"] = False
        if args.check:
            return check(cfg)
        if args.telegram_setup:
            from shorts_bot import telegram
            return telegram.setup(HERE / ".env")
        from shorts_bot.util import require_ffmpeg
        require_ffmpeg()
        if args.test_voice:
            from shorts_bot import voice
            out = cfg["paths"]["output"] / "voice-test"
            out.parent.mkdir(parents=True, exist_ok=True)
            wav = voice.speak(args.test_voice, out, cfg)
            return say(f"✅ Awaaz bani: {wav}  (awaaz: {voice.pick_voice(cfg)})")

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
