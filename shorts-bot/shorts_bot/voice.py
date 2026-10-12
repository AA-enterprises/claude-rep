"""AI awaaz banana (Microsoft Edge = muft, ElevenLabs = paid)."""

import asyncio
import base64
import json
import os
import re
import urllib.parse
from pathlib import Path

from . import languages
from .util import BotError, run, say


def pick_voice(cfg: dict) -> str:
    v = cfg["voice"]
    if v.get("edge_voice"):
        return v["edge_voice"]
    lang = languages.narration(cfg)
    female, male = lang["voices"]
    gender = v.get("gender", "female")
    if gender == "child":
        voice = lang.get("child") or female
    else:
        voice = male if gender == "male" else female
    if not voice:
        raise BotError(f"'{lang['key']}' zubaan ki awaaz maloom nahi. config.yaml mein "
                       "voice.edge_voice likhein (list: edge-tts --list-voices).")
    return voice


def _rate_pitch(cfg: dict, voice: str) -> tuple:
    """Bachche ki awaaz: asli child voice na ho to pitch ooncha aur raftar tez."""
    v = cfg["voice"]
    lang = languages.narration(cfg)
    if v.get("gender") == "child" and not v.get("edge_voice") and voice != lang.get("child"):
        return v.get("child_rate", "+8%"), v.get("child_pitch", "+45Hz")
    return v["rate"], v["pitch"]


def _edge(text: str, out: Path, cfg: dict):
    import edge_tts

    async def go():
        voice = pick_voice(cfg)
        rate, pitch = _rate_pitch(cfg, voice)
        com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await com.save(str(out))

    try:
        asyncio.run(go())
    except Exception as e:
        raise BotError(f"Awaaz nahi bani (edge-tts). Internet check karein.\n{e}") from e


def _elevenlabs(text: str, out: Path, cfg: dict):
    import requests

    key = os.environ.get("ELEVENLABS_API_KEY", "")
    gender = cfg["voice"].get("gender", "female")
    voice_id = (cfg["voice"].get("elevenlabs_voices") or {}).get(gender) \
        or cfg["voice"].get("elevenlabs_voice_id", "")
    if not key or not voice_id:
        raise BotError("ElevenLabs ke liye ELEVENLABS_API_KEY aur config mein "
                       f"voice.elevenlabs_voices.{gender} (voice ID) dono chahiye.")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": key, "accept": "audio/mpeg"},
        json={"text": text, "model_id": cfg["voice"]["elevenlabs_model"]},
        timeout=120,
    )
    if r.status_code != 200:
        raise BotError(f"ElevenLabs error {r.status_code}: {r.text[:300]}")
    out.write_bytes(r.content)


GOOGLE_HEADERS = {
    "Referer": "http://translate.google.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
}


def _chunks(text: str, limit: int = 100) -> list:
    """Google ek dafa mein ~100 akhar leta hai. Pehle poore jumle jorro; koi jumla
    khud lamba ho to use alfaaz par toro."""
    sentences = [x for x in re.split(r"(?<=[.!?،۔؟,])\s+", text.strip()) if x]
    pieces = []
    for sent in sentences:
        if len(sent) <= limit:
            pieces.append(sent)
            continue
        cur = ""
        for word in sent.split():
            if cur and len(cur) + len(word) + 1 > limit:
                pieces.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            pieces.append(cur)
    parts, cur = [], ""
    for piece in pieces:
        if cur and len(cur) + len(piece) + 1 > limit:
            parts.append(cur)
            cur = piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        parts.append(cur)
    return parts


def _google(text: str, out: Path, cfg: dict):
    """Google Translate ki muft awaaz (backup). Ek hi awaaz hoti hai; larka/bachcha
    pitch badal kar banta hai (speak() mein)."""
    import requests

    code = languages.narration(cfg)["code"]
    code = {"zh": "zh-CN"}.get(code, code)
    audio = b""
    for part in _chunks(text):
        rpc = [[["jQ1olc", json.dumps([part, code, None, "null"], separators=(",", ":")),
                 None, "generic"]]]
        body = "f.req=" + urllib.parse.quote(json.dumps(rpc, separators=(",", ":"))) + "&"
        try:
            r = requests.post("https://translate.google.com/_/TranslateWebserverUi/data/batchexecute",
                              data=body, headers=GOOGLE_HEADERS, timeout=60)
        except requests.RequestException as e:
            raise BotError(f"Google awaaz se rabta nahi hua: {e}") from e
        m = re.search(r'jQ1olc","\[\\"(.*?)\\"', r.text)
        if r.status_code != 200 or not m:
            raise BotError(f"Google awaaz nahi bani ({r.status_code}). '{code}' zubaan shayad support nahi.")
        audio += base64.b64decode(m.group(1))
    out.write_bytes(audio)


# Ek dafa Microsoft fail ho jaye to baaqi run mein seedha backup (waqt bachta hai)
_edge_failed = False


def _pitch_filter(cfg: dict) -> str:
    """Google ki ek hi (aurat) awaaz ko larke ya bachche jaisa banao."""
    gender = cfg["voice"].get("gender", "female")
    if gender == "male":
        return "aresample=24000,asetrate=19200,aresample=24000,atempo=1.25,"
    if gender == "child":
        return "aresample=24000,asetrate=30000,aresample=24000,atempo=0.85,"
    return "atempo=1.08,"


def speak(text: str, out: Path, cfg: dict) -> Path:
    """Text ko awaaz mein badal kar WAV file banao (48kHz stereo)."""
    global _edge_failed
    mp3 = out.with_suffix(".mp3")
    extra = ""
    engine = cfg["voice"]["engine"]
    if engine == "elevenlabs":
        _elevenlabs(text, mp3, cfg)
    elif engine == "google":
        _google(text, mp3, cfg)
        extra = _pitch_filter(cfg)
    else:
        try:
            if _edge_failed:
                raise BotError("pehle fail ho chuka")
            _edge(text, mp3, cfg)
        except BotError as e:
            if not cfg["voice"].get("fallback_google", True):
                raise
            if not _edge_failed:
                first = str(e).splitlines()[-1][:120]
                say(f"  ⚠️  Microsoft awaaz nahi mili ({first}). Google ki backup awaaz laga raha hoon.")
                _edge_failed = True
            _google(text, mp3, cfg)
            extra = _pitch_filter(cfg)
    wav = out.with_suffix(".wav")
    # Shuru/aakhir ki khamoshi kaato, awaaz barabar karo
    run(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-af",
         extra + "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         "loudnorm=I=-14:TP=-1.5:LRA=11",
         "-ar", "48000", "-ac", "2", wav])
    return wav
