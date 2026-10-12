"""Podcast ki baat-cheet ko waqt (timestamps) ke saath text mein badalna."""

import json
import re

from .util import BotError, read_json, say, write_json

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


WHISPER_BLOCKED = (
    "Is video ke YouTube subtitles nahi mile, aur AI se sunne wala hissa (Whisper) "
    "aap ke computer par nahi chal raha:\n  {err}\n"
    "Hal: koi aisi video lein jis ke subtitles hon (YouTube par CC wala nishaan), "
    "ya README ka 'Whisper nahi chalta' wala hissa dekhein."
)


def _words_from_whisper(video, model_size: str, lang: str):
    try:
        from faster_whisper import WhisperModel
    except Exception as e:  # Windows Smart App Control DLL rok deta hai
        first = (str(e).strip().splitlines() or [type(e).__name__])[0]
        raise BotError(WHISPER_BLOCKED.format(err=first[:200])) from e

    say(f"  AI sun raha hai (Whisper '{model_size}'). Lambi video par kaafi waqt lagega...")
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, info = model.transcribe(
        str(video), word_timestamps=True, vad_filter=True,
        language=None if lang in ("", "auto") else lang,
    )
    words = []
    last = 0
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append({"start": w.start, "end": w.end, "text": t})
        if seg.end - last > 300:
            last = seg.end
            say(f"    ... {int(seg.end // 60)} minute ho gaye")
    return words, info.language


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
        words, lang = _words_from_whisper(src["video"], cfg["transcript"]["whisper_model"],
                                          cfg["language"]["source"])
    if len(words) < 30:
        raise BotError("Is video mein baat-cheet nahi mili (transcript khaali hai).")
    data = {"language": lang or "en", "segments": _group(words)}
    write_json(cache, data)
    return data
