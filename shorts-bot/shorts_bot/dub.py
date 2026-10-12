"""Dubbing: asal (English) baat ki jagah har line Urdu awaaz mein, usi waqt par.

Har caption line ka tarjuma alag se bolwaya jata hai (bolne wale jaisi awaaz), line ke waqt
mein fit kiya jata hai (zaroorat ho to thora tez), aur asal awaaz peeche halki rehti hai."""

import copy
from pathlib import Path

from . import voice
from .util import duration, run, say

MAX_SPEEDUP = 1.25  # Is se zyada tez awaaz samajh nahi aati


def _dub_cfg(cfg: dict) -> dict:
    d = copy.deepcopy(cfg)
    d["voice"]["edge_voice"] = ""
    d["language"]["voice"] = cfg["language"]["target"]  # Tarjume ki zubaan mein bolo
    return d


def _style(ln: dict, cfg: dict) -> str:
    """Line kis awaaz mein: AI ne bataya (buddha/jawan/aurat/narrator), warna config."""
    if cfg["dub"].get("match_speaker", True) and ln.get("voice") in voice.STYLES:
        return ln["voice"]
    return cfg["dub"].get("gender", "male")


def make_track(video: Path, clip: dict, cfg: dict, work: Path, start: float, dur: float) -> Path:
    """Clip ke liye poora dub audio (WAV) banao: asal awaaz halki + har line ki Urdu awaaz."""
    dcfg = _dub_cfg(cfg)
    lines = clip["lines"]
    # Gemini (insaan jaisi awaaz): ek hi bande ki lagataar lines ek saath bolwao. Awaaz
    # qudrati behti hai (voice-over jaisi) aur muft had bhi kam kharch hoti hai.
    mode = cfg["dub"].get("mode", "auto")
    together = mode == "voiceover" or (mode == "auto" and voice.engine_name(dcfg) == "gemini")
    units = []  # (pehli line ka index, aakhri line ka index, andaaz)
    for i, ln in enumerate(lines):
        st = _style(ln, cfg)
        if together and units and units[-1][2] == st:
            units[-1][1] = i
        else:
            units.append([i, i, st])
    say(f"  Dubbing: {len(units)} hisse Urdu awaaz mein bolwa raha hoon...")
    items = []
    free_at = 0.0  # Pichhli line kab khatam hui: lines kabhi ek doosre par na charhein
    for k, (a, b, st) in enumerate(units):
        text = " ".join((ln.get("translated") or "").strip() or ln["original"] for ln in lines[a:b + 1])
        rel = max(0.0, lines[a]["start"] - start, free_at)
        nxt = (lines[b + 1]["start"] - start) if b + 1 < len(lines) else dur
        window = max(0.6, nxt - rel - 0.05)
        wav = voice.speak(text, work / f"dub_{k:02d}", voice.styled(dcfg, st))
        tempo = min(max(duration(wav) / window, 1.0), MAX_SPEEDUP)
        items.append((wav, rel, tempo))
        free_at = rel + duration(wav) / tempo + 0.08

    # Aakhri Urdu line clip ke baad tak jaye to video thora lamba karo (awaaz kabhi na kate)
    extra = min(max(0.0, free_at - dur + 0.15), 3.0)
    total = dur + extra
    orig = work / "dub_orig.wav"
    vol = float(cfg["dub"].get("original_volume", 0.05))
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", video,
         "-vn", "-af", f"aresample=48000,volume={vol},apad=whole_dur={total:.3f}", "-ac", "2", orig])

    # Jo line waqt ke andar shuru hi na ho sake use chhoro (beech se kati awaaz se behtar)
    items = [it for it in items if it[1] < total - 0.8]
    inputs = ["-i", orig]
    chains, labels = [], ["[0:a]"]
    for k, (wav, rel, tempo) in enumerate(items, 1):
        inputs += ["-i", wav]
        ms = int(rel * 1000)
        chains.append(f"[{k}:a]atempo={tempo:.3f},adelay={ms}|{ms}[v{k}]")
        labels.append(f"[v{k}]")
    fc = ";".join(chains + [f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=first,"
                            f"atrim=0:{total:.3f}[a]"])
    out = work / "dub_track.wav"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[a]",
         "-ar", "48000", "-ac", "2", out])
    return out, extra
