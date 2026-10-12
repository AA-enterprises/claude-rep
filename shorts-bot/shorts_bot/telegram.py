"""Tayyar Shorts aap ke Telegram par bhejna."""

import os
import time
from pathlib import Path

from .util import BotError, duration, say

API = "{base}/bot{token}/{method}"
DEFAULT_BASE = "https://api.telegram.org"


def _base() -> str:
    """Apna Cloudflare relay ho to us ka pata (.env: TELEGRAM_API_URL), warna Telegram."""
    return (os.environ.get("TELEGRAM_API_URL", "").strip() or DEFAULT_BASE).rstrip("/")
MAX_BYTES = 50 * 1024 * 1024  # Telegram bot 50 MB tak ki file bhej sakta hai


def _call(method: str, data=None, files=None, token=None, timeout=60):
    import requests

    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise BotError(".env mein TELEGRAM_BOT_TOKEN nahi. README ka Telegram wala hissa dekhein.")
    proxy = os.environ.get("TELEGRAM_PROXY", "").strip()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    last = None
    for attempt in range(3):  # Connection kabhi kabhi kat jata hai: dobara koshish
        if files:
            for f in files.values():
                f[1].seek(0)
        try:
            r = requests.post(API.format(base=_base(), token=token, method=method), data=data, files=files,
                              timeout=timeout, proxies=proxies)
            break
        except requests.RequestException as e:
            last = e
            time.sleep(3 * (attempt + 1))
    else:
        # Error mein token kabhi na dikhe
        msg = str(last).replace(token, "<TOKEN>")
        raise BotError(
            "Computer se Telegram tak rabta nahi hua. Aksar internet company Telegram ko rok "
            "deti hai (phone app phir bhi chal jati hai).\n"
            "Hal: apna muft Cloudflare relay banayein (README: 'Telegram relay'), ya computer "
            "par VPN chalayein (jaise Cloudflare WARP).\n"
            f"Asal error: {msg[:200]}") from last
    try:
        res = r.json()
    except ValueError:
        res = {}
    if r.status_code == 401 or res.get("error_code") == 401:
        raise BotError("TELEGRAM_BOT_TOKEN ghalat hai. @BotFather se token dobara copy karein.")
    if not res.get("ok"):
        desc = (res.get("description") or r.text[:200]).replace(token, "<TOKEN>")
        raise BotError(f"Telegram error: {desc}")
    return res["result"]


def enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def send_message(text: str, reply_to: int = None) -> list:
    """Message bhejo; wapas: bheje gaye messages ke IDs."""
    ids = []
    for i in range(0, len(text), 4000):  # Telegram ek message mein 4096 akhar tak leta hai
        data = {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[i:i + 4000]}
        if reply_to:
            data["reply_to_message_id"] = reply_to
        ids.append(_call("sendMessage", data=data)["message_id"])
    return ids


def send_document(path: Path, caption: str = "", mime: str = "image/jpeg") -> int:
    with open(path, "rb") as f:
        res = _call("sendDocument", timeout=120,
                    data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": caption[:1000]},
                    files={"document": (path.name, f, mime)})
    return res["message_id"]


def send_short(video: Path, title: str, description: str, thumb: Path = None) -> list:
    """Video + thumbnail + title/description. Wapas: saare messages ke IDs (reply pehchanne ke liye)."""
    size = video.stat().st_size
    if size > MAX_BYTES:
        return send_message(f"⚠️ Short tayyar hai lekin {size // (1024 * 1024)} MB ka hai "
                            f"(Telegram limit 50 MB). Computer par dekhein:\n{video.name}")
    ids = []
    with open(video, "rb") as f:
        res = _call("sendVideo", timeout=600,
                    data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": title[:1000],
                          "supports_streaming": "true", "width": 1080, "height": 1920,
                          "duration": int(duration(video))},
                    files={"video": (video.name, f, "video/mp4")})
        ids.append(res["message_id"])
    if thumb and Path(thumb).exists():  # Document ki shakal mein: quality kharab nahi hoti
        ids.append(send_document(Path(thumb), "🖼️ Thumbnail"))
    ids += send_message(f"📋 TITLE:\n{title}\n\n📋 DESCRIPTION:\n{description}")
    return ids


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
