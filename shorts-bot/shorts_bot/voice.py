"""AI awaaz banana (Microsoft Edge = muft, ElevenLabs = paid)."""

import asyncio
import os
from pathlib import Path

from . import languages
from .util import BotError, run


def pick_voice(cfg: dict) -> str:
    v = cfg["voice"]
    if v.get("edge_voice"):
        return v["edge_voice"]
    lang = languages.get(cfg["language"]["target"])
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
    lang = languages.get(cfg["language"]["target"])
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


def speak(text: str, out: Path, cfg: dict) -> Path:
    """Text ko awaaz mein badal kar WAV file banao (48kHz stereo)."""
    mp3 = out.with_suffix(".mp3")
    if cfg["voice"]["engine"] == "elevenlabs":
        _elevenlabs(text, mp3, cfg)
    else:
        _edge(text, mp3, cfg)
    wav = out.with_suffix(".wav")
    # Shuru/aakhir ki khamoshi kaato, awaaz barabar karo
    run(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-af",
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         "loudnorm=I=-14:TP=-1.5:LRA=11",
         "-ar", "48000", "-ac", "2", wav])
    return wav
