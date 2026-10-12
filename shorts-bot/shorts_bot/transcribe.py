"""Podcast ki baat-cheet ko waqt (timestamps) ke saath text mein badalna."""

import json
import os
import re
import subprocess
import sys
import time
import types
from pathlib import Path

from .util import BotError, duration, read_json, run, say, write_json

MAX_WORDS = 12      # Ek caption line mein zyada se zyada alfaaz
MAX_SECONDS = 5.5   # Ek caption line zyada se zyada kitni der
PAUSE = 0.6         # Itna ruk jaye to nayi line


def _words_from_json3(path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    events = [e for e in data.get("events", []) if e.get("segs")]
    words = []
    for i, ev in enumerate(events):
        start = ev.get("tStartMs", 0) / 1000
        end = start + ev.get("dDurationMs", 0) / 1000
        nxt = events[i + 1].get("tStartMs", 0) / 1000 if i + 1 < len(events) else end
        segs = ev["segs"]
        for j, seg in enumerate(segs):
            text = (seg.get("utf8") or "").replace("\n", " ").strip()
            if not text or text.startswith("[") and text.endswith("]"):
                continue
            s = start + seg.get("tOffsetMs", 0) / 1000
            e_ = (start + segs[j + 1].get("tOffsetMs", 0) / 1000) if j + 1 < len(segs) else min(max(end, s + 0.2), max(nxt, s + 0.2))
            parts = text.split()
            # Manual subtitles mein poori line ek seg hoti hai: waqt barabar baant do
            step = max((e_ - s) / len(parts), 0.05)
            for k, p in enumerate(parts):
                words.append({"start": s + k * step, "end": s + (k + 1) * step, "text": p})
    words.sort(key=lambda w: w["start"])
    # Ek dusre par charhe hue alfaaz theek karo
    for a, b in zip(words, words[1:]):
        if a["end"] > b["start"]:
            a["end"] = max(a["start"] + 0.05, b["start"])
    return words


CHUNK = 600  # Audio 10-10 minute ke tukron mein suna jata hai


def _audio_chunks(video, total: float):
    """FFmpeg se 16kHz mono audio nikalo, 10 minute ke tukron mein (numpy float32)."""
    import numpy as np

    start = 0.0
    while start < total:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-t", str(CHUNK), "-i", str(video),
             "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise BotError("Video se audio nahi nikla:\n" + proc.stderr.decode("utf-8", "replace")[-500:])
        yield start, np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0
        start += CHUNK


def _import_whisper():
    """faster_whisper load karo. Windows ka Smart App Control 'av' (PyAV) ki DLL rok
    deta hai, lekin audio hum khud FFmpeg se dete hain, is liye 'av' ke baghair bhi chalta hai."""
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except Exception:
        for name in list(sys.modules):
            if name in ("av", "faster_whisper") or name.startswith(("av.", "faster_whisper.")):
                del sys.modules[name]
        sys.modules["av"] = types.ModuleType("av")
        try:
            from faster_whisper import WhisperModel
            return WhisperModel
        except Exception:
            sys.modules.pop("av", None)
            raise


def _vad_available() -> bool:
    try:
        __import__("onnxruntime")
        return True
    except Exception:
        return False


def _words_local(video, total: float, model_size: str, lang: str):
    WhisperModel = _import_whisper()
    say(f"  AI khud sun kar subtitles bana raha hai (Whisper '{model_size}', computer par)...")
    say("  Pehli dafa model download hoga. Lambi video par kaafi waqt lagega.")
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    vad = _vad_available()
    language = None if lang in ("", "auto") else lang
    words = []
    for offset, audio in _audio_chunks(video, total):
        segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=vad,
                                          language=language)
        language = language or info.language  # Pehle tukre ki zubaan baaqi par bhi
        for seg in segments:
            for w in seg.words or []:
                t = w.word.strip()
                if t:
                    words.append({"start": offset + w.start, "end": offset + w.end, "text": t})
        say(f"    ... {min(int((offset + CHUNK) // 60), int(total // 60))}/{int(total // 60)} minute")
    return words, language


def _words_groq(video, total: float, lang: str, work: Path):
    """Groq (internet) se transcription: computer par kuch nahi chalta."""
    import requests

    key = os.environ.get("GROQ_API_KEY", "")
    say("  Groq (internet) se subtitles ban rahe hain...")
    words, language = [], None if lang in ("", "auto") else lang
    start = 0.0
    while start < total:
        part = work / f"groq-{int(start)}.mp3"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", str(CHUNK), "-i", video,
             "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", part])
        data = {"model": "whisper-large-v3-turbo", "response_format": "verbose_json",
                "timestamp_granularities[]": ["word", "segment"]}
        if language:
            data["language"] = language
        for attempt in range(8):
            with open(part, "rb") as f:
                r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
                                  headers={"Authorization": f"Bearer {key}"},
                                  data=data, files={"file": (part.name, f, "audio/mpeg")},
                                  timeout=300)
            if r.status_code == 429:  # Free plan ki limit: ruk kar dobara
                wait = min(float(r.headers.get("retry-after") or 30), 300)
                say(f"    Groq limit: {int(wait)} second ruk raha hoon...")
                time.sleep(wait)
                continue
            break
        if r.status_code == 401:
            raise BotError("GROQ_API_KEY ghalat hai. console.groq.com se nayi key lein.")
        if r.status_code != 200:
            raise BotError(f"Groq error {r.status_code}: {r.text[:300]}")
        res = r.json()
        language = language or _lang_code(res.get("language"))
        got = res.get("words") or []
        if got:
            for w in got:
                t = (w.get("word") or "").strip()
                if t:
                    words.append({"start": start + w["start"], "end": start + w["end"], "text": t})
        else:  # Sirf segments mile: har segment ka waqt alfaaz mein baant do
            for seg in res.get("segments") or []:
                parts = (seg.get("text") or "").split()
                if not parts:
                    continue
                step = max((seg["end"] - seg["start"]) / len(parts), 0.05)
                for k, p in enumerate(parts):
                    s0 = start + seg["start"] + k * step
                    words.append({"start": s0, "end": s0 + step, "text": p})
        part.unlink(missing_ok=True)
        say(f"    ... {min(int((start + CHUNK) // 60), int(total // 60))}/{int(total // 60)} minute")
        start += CHUNK
    return words, language


def _lang_code(name):
    """Groq 'english' jaisa naam bhi de sakta hai: code mein badlo."""
    if not name:
        return None
    from . import languages
    return languages.get(name)["code"]


NO_LISTENER = (
    "Is video ke YouTube subtitles nahi hain, aur bot ise khud nahi sun saka:\n  {err}\n"
    "Hal (koi ek):\n"
    "  1. Muft: console.groq.com par account bana kar API key lein aur .env mein\n"
    "     GROQ_API_KEY=... likhein. Phir bot internet se subtitles bana lega.\n"
    "  2. README ka 'Whisper nahi chalta' wala hissa dekhein."
)


def _words_from_audio(src: dict, cfg: dict):
    tcfg = cfg["transcript"]
    engine = tcfg.get("engine", "auto")
    lang = cfg["language"]["source"]
    from .download import audio_for_listening
    media = audio_for_listening(src, cfg)
    total = duration(media)
    has_groq = bool(os.environ.get("GROQ_API_KEY"))
    if engine == "groq":
        if not has_groq:
            raise BotError("config mein transcript.engine: groq hai, lekin .env mein GROQ_API_KEY nahi.")
        return _words_groq(media, total, lang, src["dir"])
    try:
        return _words_local(media, total, tcfg["whisper_model"], lang)
    except BotError:
        raise
    except Exception as e:
        first = (str(e).strip().splitlines() or [type(e).__name__])[0][:200]
        if engine == "auto" and has_groq:
            say(f"  Computer par Whisper nahi chala ({first[:80]}). Groq istemal kar raha hoon.")
            return _words_groq(media, total, lang, src["dir"])
        raise BotError(NO_LISTENER.format(err=first)) from e


def _group(words: list) -> list:
    """Alfaaz ko chhoti caption lines mein jorna."""
    segs, cur = [], []
    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            too_long = w["end"] - cur[0]["start"] > MAX_SECONDS or len(cur) >= MAX_WORDS
            sentence_end = re.search(r"[.?!]$", cur[-1]["text"]) and len(cur) >= 4
            if gap > PAUSE or too_long or sentence_end:
                segs.append(cur)
                cur = []
        cur.append(w)
    if cur:
        segs.append(cur)
    out = []
    for i, ws in enumerate(segs):
        out.append({
            "i": i,
            "start": round(ws[0]["start"], 2),
            "end": round(ws[-1]["end"], 2),
            "text": " ".join(w["text"] for w in ws),
        })
    return out


def get_transcript(src: dict, cfg: dict) -> dict:
    cache = src["dir"] / "transcript.json"
    data = read_json(cache)
    if data and data.get("segments"):
        say("  Transcript pehle se bana hua hai.")
        return data
    words, lang = [], src.get("caption_lang")
    if src.get("captions"):
        say("  YouTube subtitles istemal ho rahe hain.")
        words = _words_from_json3(src["captions"])
    if len(words) < 30:
        words, lang = _words_from_audio(src, cfg)
    if len(words) < 30:
        raise BotError("Is video mein baat-cheet nahi mili (transcript khaali hai).")
    data = {"language": lang or "en", "segments": _group(words)}
    write_json(cache, data)
    return data
