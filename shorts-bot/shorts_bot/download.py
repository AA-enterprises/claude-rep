"""Video aur us ki maloomat (title, channel, license, subtitles) laana."""

import hashlib
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


def fetch(source: str, cfg: dict) -> dict:
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
    height = int(cfg["video"]["max_download_height"])
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/bv*[height<={height}]+ba/b[height<={height}]/b",
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(source, download=False)
        except Exception as e:
            raise BotError(f"Video ki maloomat nahi mili. Link sahi hai?\n{e}") from e
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

        video = d / "video.mp4"
        if not video.exists():
            say(f"  Download: {meta['title'][:70]}")
            dl_opts = dict(opts, outtmpl=str(d / "video.%(ext)s"), quiet=True, noprogress=False)
            with yt_dlp.YoutubeDL(dl_opts) as dl:
                try:
                    dl.download([meta["url"]])
                except Exception as e:
                    raise BotError(f"Video download nahi hui:\n{e}") from e
            if not video.exists():
                found = sorted(d.glob("video.*"))
                found = [f for f in found if f.suffix in (".mp4", ".mkv", ".webm")]
                if not found:
                    raise BotError("Video download ke baad file nahi mili.")
                video = found[0]
        else:
            say("  Video pehle se download hai.")

    cap = d / "captions.json3"
    return {**meta, "dir": d, "video": video,
            "captions": cap if cap.exists() and meta.get("caption_lang") else None}
