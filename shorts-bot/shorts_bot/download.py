"""Video aur us ki maloomat (title, channel, license, subtitles) laana."""

import hashlib
import time
from pathlib import Path

from .util import BotError, read_json, say, slug, write_json


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://", "www."))


def _pick_captions(info: dict, source_lang: str):
    """YouTube ke subtitles mein se sab se behtar (json3) dhoondo."""
    lang = (source_lang if source_lang != "auto" else info.get("language") or "").split("-")[0]
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    def json3(tracks):
        for t in tracks or []:
            if t.get("ext") == "json3" and t.get("url"):
                return t["url"]
        return None

    order = []
    if lang:
        order += [(manual, k) for k in manual if k.split("-")[0] == lang]
        order += [(auto, f"{lang}-orig"), (auto, lang)]
    else:
        # Zubaan maloom nahi: "-orig" wala auto track hamesha video ki asal zubaan hota hai
        order += [(auto, k) for k in auto if k.endswith("-orig")]
        order += [(manual, k) for k in manual if k != "live_chat"]
    for tracks, key in order:
        url = json3(tracks.get(key))
        if url:
            return url, key.replace("-orig", "")
    return None, None


BOT_CHECK = (
    "YouTube ne aap ke computer ko \"bot\" samajh kar rok diya hai (Sign in to confirm you're not a bot).\n"
    "Hal: bot ko YouTube ki cookies dein (README: 'YouTube ne rok diya'):\n"
    "  1. Chrome/Edge mein extension \"Get cookies.txt LOCALLY\" install karein.\n"
    "  2. youtube.com kholein (login hon), extension se cookies.txt download karein.\n"
    "  3. Woh file bot ke folder mein \"cookies.txt\" naam se rakh dein.\n"
    "Phir 10-15 minute baad dobara try karein. Baar baar koshish se rukawat lambi hoti hai."
)


def is_bot_check(err) -> bool:
    t = str(err).lower()
    return "confirm you" in t and "bot" in t or "sign in to confirm" in t


def base_opts(cfg: dict) -> dict:
    """Har yt-dlp call ke liye: cookies (agar hon) taake YouTube \"bot\" na samjhe."""
    opts = {}
    cookies = cfg["_base"] / "cookies.txt"
    browser = (cfg["video"].get("cookies_from_browser") or "").strip().lower()
    if cookies.exists():
        opts["cookiefile"] = str(cookies)
    elif browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def _opts(cfg: dict, **extra) -> dict:
    """yt-dlp settings: kamzor internet par bhi chalne ke liye retries aur resume."""
    height = int(cfg["video"]["max_download_height"])
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/bv*[height<={height}]+ba/b[height<={height}]/b",
        "merge_output_format": "mp4",
        "retries": 15,
        "fragment_retries": 15,
        "file_access_retries": 5,
        "socket_timeout": 60,
        "http_chunk_size": 10 * 1024 * 1024,
        "continuedl": True,
    }
    opts.update(base_opts(cfg))
    opts.update(extra)
    return opts


def _download(url: str, opts: dict, what: str):
    """Download karo; connection toote to ruk kar dobara (adhoori file se aage)."""
    import yt_dlp

    last = None
    for attempt in range(1, 5):
        try:
            with yt_dlp.YoutubeDL(opts) as dl:
                dl.download([url])
            return
        except Exception as e:  # Internet ka masla: thora ruk kar dobara
            last = e
            if is_bot_check(e):  # Dobara koshish se rukawat aur lambi hoti hai
                raise BotError(BOT_CHECK) from e
            if attempt < 4:
                say(f"  Internet ka masla ({what}), {attempt * 10} second baad dobara koshish...")
                time.sleep(attempt * 10)
    raise BotError(f"{what} download nahi hua (4 dafa koshish ki). Internet check karein.\n{last}")


def fetch(source: str, cfg: dict) -> dict:
    """Video ki maloomat aur subtitles lao. Video khud abhi download nahi hoti:
    AI ke moments chunne ke baad sirf wohi hisse aate hain (clip_media)."""
    work = cfg["paths"]["work"]
    if not _is_url(source):
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise BotError(f"File nahi mili: {source}")
        vid = "local-" + hashlib.md5(str(path).encode()).hexdigest()[:10]
        d = work / vid
        d.mkdir(parents=True, exist_ok=True)
        return {"id": vid, "dir": d, "video": path, "title": path.stem, "channel": "",
                "url": "", "license": "", "captions": None, "caption_lang": None}

    import yt_dlp

    if source.startswith("www."):
        source = "https://" + source
    with yt_dlp.YoutubeDL(_opts(cfg)) as ydl:
        info = None
        for attempt in range(1, 4):
            try:
                info = ydl.extract_info(source, download=False)
                break
            except Exception as e:
                if is_bot_check(e):
                    raise BotError(BOT_CHECK) from e
                if attempt == 3 or "unsupported url" in str(e).lower() or "private" in str(e).lower():
                    raise BotError(f"Video ki maloomat nahi mili. Link sahi hai?\n{e}") from e
                time.sleep(5)
        if info.get("_type") == "playlist":
            raise BotError("Ye playlist ka link hai. Ek video ka link dein (ya links.txt use karein).")

        vid = slug(info["id"], 30)
        d = work / vid
        d.mkdir(parents=True, exist_ok=True)
        meta_path = d / "meta.json"
        meta = read_json(meta_path)
        if not meta:
            meta = {
                "id": vid,
                "title": info.get("title", ""),
                "channel": info.get("channel") or info.get("uploader") or "",
                "url": info.get("webpage_url") or source,
                "license": info.get("license") or "",
                "duration": info.get("duration") or 0,
                "caption_lang": None,
            }
            if cfg["transcript"]["prefer_youtube_captions"]:
                cap_url, cap_lang = _pick_captions(info, cfg["language"]["source"])
                if cap_url:
                    try:
                        data = ydl.urlopen(cap_url).read()
                        (d / "captions.json3").write_bytes(data)
                        meta["caption_lang"] = cap_lang
                    except Exception:
                        say("  YouTube subtitles nahi mile, AI khud sunega (Whisper).")
            write_json(meta_path, meta)

    full = d / "video.mp4"
    video = full if full.exists() else None
    if video is None and cfg["video"].get("download") == "full":
        say(f"  Poori video download ho rahi hai: {meta['title'][:60]}")
        _download(meta["url"], _opts(cfg, outtmpl=str(d / "video.%(ext)s")), "Video")
        video = full if full.exists() else next(
            (f for f in sorted(d.glob("video.*")) if f.suffix in (".mp4", ".mkv", ".webm")), None)
        if video is None:
            raise BotError("Video download ke baad file nahi mili.")
    cap = d / "captions.json3"
    return {**meta, "dir": d, "video": video,
            "captions": cap if cap.exists() and meta.get("caption_lang") else None}


def audio_for_listening(src: dict, cfg: dict) -> Path:
    """Whisper ke liye sirf audio (video se kai guna chhota)."""
    if src.get("video"):
        return src["video"]
    d = src["dir"]
    found = [f for f in d.glob("audio.*") if f.suffix != ".part"]
    if found:
        return found[0]
    say("  Sirf audio download ho raha hai (subtitles banane ke liye)...")
    _download(src["url"], _opts(cfg, format="ba[ext=m4a]/ba/b", outtmpl=str(d / "audio.%(ext)s"),
                                merge_output_format=None), "Audio")
    found = [f for f in d.glob("audio.*") if f.suffix != ".part"]
    if not found:
        raise BotError("Audio download ke baad file nahi mili.")
    return found[0]


def clip_media(src: dict, clip: dict, cfg: dict):
    """Clip ke liye video. Wapas: (file, offset). offset = file ka 0 asal video ka kaunsa second."""
    if src.get("video"):
        return src["video"], 0.0
    from yt_dlp.utils import download_range_func

    a = max(0.0, round(clip["start"] - 1.5, 2))
    b = round(clip["end"] + 1.5, 2)
    out = src["dir"] / f"part-{int(a * 100)}-{int(b * 100)}.mp4"
    if out.exists():
        return out, a
    say(f"  Sirf clip wala hissa download ho raha hai ({int(b - a)} second)...")
    _download(src["url"], _opts(cfg, outtmpl=str(out.with_suffix(".%(ext)s")),
                                download_ranges=download_range_func(None, [(a, b)]),
                                force_keyframes_at_cuts=True), "Clip")
    if not out.exists():
        alt = [f for f in out.parent.glob(out.stem + ".*") if f.suffix in (".mkv", ".webm")]
        if not alt:
            raise BotError("Clip download ke baad file nahi mili.")
        return alt[0], a
    return out, a
