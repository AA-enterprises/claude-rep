"""Tayyar Shorts aap ke Telegram par bhejna."""

import os
from pathlib import Path

from .util import BotError, duration, say

API = "https://api.telegram.org/bot{token}/{method}"
MAX_BYTES = 50 * 1024 * 1024  # Telegram bot 50 MB tak ki file bhej sakta hai


def _call(method: str, data=None, files=None, token=None, timeout=60):
    import requests

    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise BotError(".env mein TELEGRAM_BOT_TOKEN nahi. README ka Telegram wala hissa dekhein.")
    try:
        r = requests.post(API.format(token=token, method=method), data=data, files=files,
                          timeout=timeout)
    except requests.RequestException as e:
        raise BotError(f"Telegram se rabta nahi hua (internet?): {e}") from e
    try:
        res = r.json()
    except ValueError:
        res = {}
    if r.status_code == 401 or res.get("error_code") == 401:
        raise BotError("TELEGRAM_BOT_TOKEN ghalat hai. @BotFather se token dobara copy karein.")
    if not res.get("ok"):
        raise BotError(f"Telegram error: {res.get('description') or r.text[:200]}")
    return res["result"]


def enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def send_message(text: str):
    # Telegram ek message mein 4096 akhar tak leta hai
    for i in range(0, len(text), 4000):
        _call("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                                   "text": text[i:i + 4000]})


def send_short(video: Path, title: str, description: str, thumb: Path = None):
    """Video + title, phir description alag message mein (copy karne ke liye)."""
    size = video.stat().st_size
    if size > MAX_BYTES:
        send_message(f"⚠️ Short tayyar hai lekin {size // (1024 * 1024)} MB ka hai "
                     f"(Telegram limit 50 MB). Computer par dekhein:\n{video.name}")
        return
    with open(video, "rb") as f:
        _call("sendVideo", timeout=600,
              data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": title[:1000],
                    "supports_streaming": "true", "width": 1080, "height": 1920,
                    "duration": int(duration(video))},
              files={"video": (video.name, f, "video/mp4")})
    if thumb and thumb.exists():  # Document ki shakal mein: quality kharab nahi hoti
        with open(thumb, "rb") as f:
            _call("sendDocument", timeout=120,
                  data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": "🖼️ Thumbnail"},
                  files={"document": (thumb.name, f, "image/jpeg")})
    send_message(f"📋 TITLE:\n{title}\n\n📋 DESCRIPTION:\n{description}")


def setup(env_path: Path):
    """Token se bot dhoondo, user ki chat ID .env mein likho, test message bhejo."""
    me = _call("getMe")
    say(f"✅ Telegram bot mil gaya: @{me.get('username')}")
    updates = _call("getUpdates")
    chats = [u["message"]["chat"] for u in updates if "message" in u]
    if not chats:
        raise BotError(f"Pehle Telegram mein apne bot @{me.get('username')} ko kholein, "
                       "START dabayein (ya 'hi' likhein), phir ye command dobara chalayein.")
    chat = chats[-1]
    chat_id = str(chat["id"])
    _write_env(env_path, "TELEGRAM_CHAT_ID", chat_id)
    os.environ["TELEGRAM_CHAT_ID"] = chat_id
    name = chat.get("first_name") or chat.get("title") or chat_id
    send_message("✅ Shorts Bot jur gaya! Ab har tayyar Short yahan aayega.")
    say(f"✅ Chat mil gayi ({name}). Telegram par test message bhej diya.")


def _write_env(env_path: Path, key: str, value: str):
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
