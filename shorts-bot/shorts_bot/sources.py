"""Mehfooz channels (NASA, US hukumat) aur Creative Commons search se nayi video chunna."""

import urllib.parse
from pathlib import Path

import yaml

from .util import BotError, read_json, say, slug

CC_FILTER = "EgIwAQ%253D%253D"  # YouTube search ka "Creative Commons" filter
MIN_SEC, MAX_SEC = 4 * 60, 3 * 60 * 60  # 4 minute se 3 ghante tak ki videos


def load(base: Path) -> dict:
    out = {}
    for name in ("sources.yaml", "sources.local.yaml"):
        p = base / name
        if p.exists():
            try:
                out.update(yaml.safe_load(p.read_text(encoding="utf-8-sig")) or {})
            except yaml.YAMLError as e:
                raise BotError(f"{name} mein likhne ki galti hai:\n{e}") from e
    return out


def _listing(url: str, limit: int) -> list:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
            "playlistend": limit, "socket_timeout": 60, "retries": 5}
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise BotError(f"Channel/search ki list nahi mili:\n{e}") from e
    return [e for e in (info.get("entries") or []) if e and e.get("id")]


def used_ids(cfg: dict) -> set:
    hist = read_json(cfg["paths"]["output"] / "history.json", {"videos": {}})
    return set(hist.get("videos", {}).keys())


def candidates(cfg: dict, key: str = None, topic: str = None, limit: int = 40) -> tuple:
    """Wapas: (videos ki list [(url, title)], source ka type, note)."""
    if topic:
        url = ("https://www.youtube.com/results?search_query="
               + urllib.parse.quote_plus(topic) + "&sp=" + CC_FILTER)
        kind, note = "cc", "Creative Commons (CC BY) - credit zaroori"
    else:
        srcs = load(cfg["_base"])
        if key not in srcs:
            raise BotError(f"'{key}' naam ka channel sources.yaml mein nahi. /sources dekhein.")
        s = srcs[key]
        url, kind, note = s["url"], s.get("type", "cc"), s.get("note", "")
    used = used_ids(cfg)
    out = []
    for e in _listing(url, limit):
        dur = e.get("duration") or 0
        if dur and not (MIN_SEC <= dur <= MAX_SEC):
            continue
        if e.get("live_status") in ("is_live", "is_upcoming"):
            continue
        if slug(e["id"], 30) in used:
            continue
        out.append((f"https://www.youtube.com/watch?v={e['id']}", e.get("title") or e["id"]))
    if not out:
        say("  Is source mein koi nayi munasib video nahi mili.")
    return out, kind, note
