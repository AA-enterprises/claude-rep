"""AI awaaz banana (Microsoft Edge = muft, ElevenLabs = paid)."""

import asyncio
import base64
import collections
import json
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

from . import languages
from .util import BotError, run, say


# Awaaz ke andaaz: (gender, rate, pitch, Google backup ke liye pitch factor).
# Video mein jaisa banda bol raha hai (buddha, jawan, aurat...) waisi awaaz; kahani /
# documentary ke liye "narrator" = bhaari, thehri hui mard ki awaaz.
STYLES = {
    "narrator": ("male", "-4%", "-10Hz", 0.84),
    "man": ("male", "+2%", "-3Hz", 0.88),
    "young_man": ("male", "+6%", "+4Hz", 0.92),
    "old_man": ("male", "-6%", "-14Hz", 0.84),
    "woman": ("female", "+0%", "+0Hz", 1.0),
    "girl": ("female", "+6%", "+14Hz", 1.12),
    "boy": ("child", "+8%", "+45Hz", 1.25),
}
GENDER_STYLE = {"male": "narrator", "female": "woman", "child": "boy"}

# Studio jaisa asar (TV/story channels ki awaaz aise hi process hoti hai):
# documentary = bhaari bass + saaf alfaaz + dabi hui (compressed) awaaz + halki goonj
FX = {
    "documentary": ("highpass=f=70,bass=g=5:f=120:w=0.8,equalizer=f=2800:t=q:w=1.2:g=2.5,"
                    "acompressor=threshold=0.1:ratio=3:attack=10:release=120:makeup=2,"
                    "aecho=0.85:0.5:35|70:0.10|0.06,"),
    "warm": "bass=g=3:f=130:w=0.8,acompressor=threshold=0.1:ratio=2.5:attack=10:release=120,",
    "none": "",
}
STYLE_FX = {"narrator": "documentary", "man": "warm", "old_man": "warm", "young_man": "warm"}


def styled(cfg: dict, style: str) -> dict:
    """Is andaaz (ya gender: male/female/child) ki awaaz wali cfg copy."""
    style = GENDER_STYLE.get(style, style)
    custom = (cfg.get("dub", {}).get("styles") or {}).get(style) or {}
    gender, rate, pitch, shift = STYLES.get(style, STYLES["man"])
    v = dict(cfg["voice"], gender=custom.get("gender", gender), rate=custom.get("rate", rate),
             pitch=custom.get("pitch", pitch), google_shift=float(custom.get("google_shift", shift)),
             child_rate=custom.get("rate", cfg["voice"].get("child_rate", "+8%")),
             child_pitch=custom.get("pitch", cfg["voice"].get("child_pitch", "+45Hz")),
             fx=custom.get("fx", STYLE_FX.get(style, "none") if cfg["voice"].get("studio_fx", True) else "none"))
    if custom.get("voice"):  # Misal: narrator: {voice: ur-IN-SalmanNeural}
        v["edge_voice"] = custom["voice"]
    return dict(cfg, voice=v)


def pick_voice(cfg: dict) -> str:
    v = cfg["voice"]
    if v.get("edge_voice"):
        return v["edge_voice"]
    lang = languages.voice(cfg)
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
    lang = languages.voice(cfg)
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

    code = languages.voice(cfg)["code"]
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


# Microsoft baar baar fail ho to thori der seedha backup (waqt bachta hai)
_edge_skip_until = 0.0
_edge_fails = 0
USED = collections.Counter()   # Kis engine ne kitni lines boleen (report ke liye)
LAST_EDGE_ERROR = ""
_rubberband = None


def _has_rubberband() -> bool:
    """FFmpeg mein 'rubberband' ho to awaaz bhaari karte waqt bhi saaf rehti hai."""
    global _rubberband
    if _rubberband is None:
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True,
                                 text=True, timeout=20).stdout
            _rubberband = " rubberband " in out
        except Exception:
            _rubberband = False
    return _rubberband


def _pitch_filter(cfg: dict) -> str:
    """Google ki ek hi (aurat) awaaz ko larke ya bachche jaisa banao."""
    v = cfg["voice"]
    gender = v.get("gender", "female")
    default = {"male": 0.8, "child": 1.25}.get(gender, 1.0)
    shift = float(v.get("google_shift") or default)
    if abs(shift - 1.0) < 0.01:
        return "atempo=1.08,"
    if _has_rubberband():  # Pitch badlo lekin awaaz ki "shakal" (formant) wahi: saaf rehti hai
        return f"rubberband=pitch={shift:.3f}:formant=preserved:tempo=1.05,"
    # Purana tareeqa: zyada badlo to awaaz bigarti hai, is liye halka sa
    shift = min(max(shift, 0.9), 1.25)
    return (f"aresample=24000,asetrate={int(24000 * shift)},aresample=24000,"
            f"atempo={min(2.0, max(0.5, 1.05 / shift)):.3f},")


def speak(text: str, out: Path, cfg: dict) -> Path:
    """Text ko awaaz mein badal kar WAV file banao (48kHz stereo)."""
    global _edge_skip_until, _edge_fails, LAST_EDGE_ERROR
    mp3 = out.with_suffix(".mp3")
    extra = ""
    engine = cfg["voice"]["engine"]
    if engine == "elevenlabs":
        _elevenlabs(text, mp3, cfg)
        USED["elevenlabs"] += 1
    elif engine == "google":
        _google(text, mp3, cfg)
        extra = _pitch_filter(cfg)
        USED["google"] += 1
    else:
        err = None
        if time.time() >= _edge_skip_until:
            for attempt in range(3):  # Microsoft kabhi kabhi ek dafa ruk jata hai: dobara try
                try:
                    _edge(text, mp3, cfg)
                    err, _edge_fails = None, 0
                    USED["microsoft"] += 1
                    break
                except BotError as e:
                    err = e
                    time.sleep(1.5 * (attempt + 1))
        else:
            err = BotError("Microsoft abhi band")
        if err:
            if not cfg["voice"].get("fallback_google", True):
                raise err
            _edge_fails += 1
            if time.time() >= _edge_skip_until:  # Asal ghalti yaad rakho (skip wali nahi)
                LAST_EDGE_ERROR = str(err).splitlines()[-1][:150]
            if _edge_fails >= 2:  # Lagataar fail: 5 minute backup, phir Microsoft dobara
                _edge_skip_until = time.time() + 300
            if _edge_fails == 1:
                first = str(err).splitlines()[-1][:120]
                say(f"  ⚠️  Microsoft awaaz nahi mili ({first}). Google ki backup awaaz laga raha hoon.")
            _google(text, mp3, cfg)
            extra = _pitch_filter(cfg)
            USED["google"] += 1
    wav = out.with_suffix(".wav")
    # Shuru/aakhir ki khamoshi kaato, awaaz barabar karo
    run(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-af",
         extra + "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
         + FX.get(cfg["voice"].get("fx") or "none", "") +
         "loudnorm=I=-14:TP=-1.5:LRA=11",
         "-ar", "48000", "-ac", "2", wav])
    return wav


def fit(wav: Path, max_sec: float) -> Path:
    """Awaaz max_sec se lambi ho to thora tez karo (zyada se zyada 1.2x, taake saaf rahe)."""
    from .util import duration
    d = duration(wav)
    if d <= max_sec + 0.2:
        return wav
    tempo = min(d / max_sec, 1.2)
    out = wav.with_name(wav.stem + "_fit.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-af", f"atempo={tempo:.3f}",
         "-ar", "48000", "-ac", "2", out])
    return out


def report() -> str:
    """Is dafa kaunsi awaaz lagi: user ko seedha batao."""
    ms, gg, el = USED["microsoft"], USED["google"], USED["elevenlabs"]
    if el:
        return f"🎙️ Awaaz: ElevenLabs ({el} lines) ✅"
    if ms and not gg:
        return f"🎙️ Awaaz: Microsoft (asli Urdu awaaz) ✅  {ms} lines"
    if gg and not ms:
        return ("⚠️ Awaaz: sirf Google ki BACKUP awaaz lagi (saaf nahi hoti). Microsoft nahi chali: "
                f"{LAST_EDGE_ERROR or 'wajah maloom nahi'}")
    if gg:
        return (f"⚠️ Awaaz: Microsoft {ms} lines, Google backup {gg} lines. Microsoft beech mein ruki: "
                f"{LAST_EDGE_ERROR or 'wajah maloom nahi'}")
    return ""


# /awaaz par namoone: pehle 4 = intro/outro/kahani wali (narrator) awaaz ke option,
# baaqi = video ke bandon ki awaazein (sirf sunne ke liye).
SAMPLES = [
    ("Bhaari narrator (Asad) + studio asar", "narrator", {}),
    ("Bhaari narrator (Salman) + studio asar", "narrator", {"voice": "ur-IN-SalmanNeural"}),
    ("Bohot bhaari, dheemi (Asad)", "narrator", {"pitch": "-18Hz", "rate": "-10%"}),
    ("Saada narrator (Asad, studio asar ke baghair)", "narrator", {"fx": "none", "pitch": "-4Hz", "rate": "+0%"}),
    ("Video mein buddha banda", "old_man", None),
    ("Video mein jawan banda", "young_man", None),
    ("Video mein aurat", "woman", None),
]
NARRATOR_CHOICES = 4


def sample_cfg(cfg: dict, idx: int) -> dict:
    label, style, over = SAMPLES[idx]
    c = dict(cfg, dub=dict(cfg.get("dub", {})))
    if over is not None:  # Narrator option: config ki purani pasand ki jagah ye
        c["dub"]["styles"] = dict(c["dub"].get("styles") or {}, narrator=over)
    return styled(c, style)
