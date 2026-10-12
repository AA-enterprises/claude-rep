"""Bachon ki kahani, apna cartoon: AI kahani -> AI tasveerein -> awaaz -> video.

Sab kuch naya banta hai (kahani, kirdar, tasveerein, music), is liye copyright ka masla nahi.
Pehle video Microsoft ki awaaz mein banti hai (namoona). Phir user apni awaaz record karke bheje
to wahi tasveerein us ki saaf ki hui awaaz ke saath dobara jorr di jati hain."""

import json
import math
import random
import re
import shutil
import time
import urllib.parse
import wave
from datetime import datetime
from pathlib import Path

from . import planner, voice
from .render import _pick_music
from .util import BotError, duration, ensure_font, ffpath, run, say, slug, step, write_json, read_json

SIZES = {"short": (1080, 1920), "long": (1920, 1080)}
GEN = {"short": (768, 1344), "long": (1344, 768)}  # AI tasveer is size mein (tez), phir bari
FPS = 30
GAP = 0.45  # Har scene ki awaaz ke baad saans


# ------------------------------------------------------------------ tasveerein
def _image(prompt: str, out: Path, size: tuple, seed: int) -> bool:
    """Muft AI tasveer (Pollinations). Kabhi kabhi dheemi hoti hai: dobara koshish."""
    import requests
    w, h = size
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1500])
           + f"?width={w}&height={h}&seed={seed}&nologo=true&model=flux")
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=240)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image") \
                    and len(r.content) > 5000:
                out.write_bytes(r.content)
                return True
            say(f"  ⚠️  Tasveer nahi bani ({r.status_code}), dobara...")
        except requests.RequestException as e:
            say(f"  ⚠️  Tasveer ki service se rabta nahi ({str(e)[:80]}), dobara...")
        time.sleep(6 * (attempt + 1))
    return False


PASTEL = ["0xFFD6A5", "0xCAFFBF", "0x9BF6FF", "0xBDB2FF", "0xFFC6FF", "0xFDFFB6", "0xA0C4FF"]


def _fallback_image(out: Path, size: tuple, k: int):
    """Tasveer na bane to rangeen pastel background (video phir bhi ban jaye)."""
    w, h = size
    c0, c1 = PASTEL[k % len(PASTEL)], PASTEL[(k + 3) % len(PASTEL)]
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"gradients=s={w}x{h}:c0={c0}:c1={c1}:duration=1:speed=0.0001", "-frames:v", "1", out])


def _prompt(story: dict, scene: dict) -> str:
    chars = "; ".join(f"{c['name']}: {c['look']}" for c in story.get("characters", []))
    return (f"{scene['image_prompt']}. Characters (always look exactly like this): {chars}. "
            f"Art style: {story.get('style', 'cute colourful 3D cartoon for children')}. "
            "Bright, cheerful, child-friendly, high detail, full scene, no text, no letters, no words, "
            "no watermark.")


# ---------------------------------------------------------------------- music
def soft_music(seconds: float, out: Path, seed: int = 0) -> Path:
    """Bot ki apni banayi halki music (music box + narm chords). Copyright ka sawal hi nahi."""
    import numpy as np
    sr = 44100
    rng = random.Random(seed)
    n = int(sr * (seconds + 1))
    t = np.arange(n) / sr
    keys = [261.63, 293.66, 329.63, 349.23, 392.0, 440.0, 493.88]  # C major
    prog = [[0, 2, 4], [5, 0, 2], [3, 5, 0], [4, 6, 1]]            # C Am F G
    beat = 0.5
    bar = beat * 8
    pad = np.zeros(n)
    box = np.zeros(n)
    for b in range(int(seconds / bar) + 2):
        chord = prog[b % 4]
        s0 = int(b * bar * sr)
        s1 = min(n, int((b + 1) * bar * sr))
        if s0 >= n:
            break
        tt = t[s0:s1] - b * bar
        env = np.minimum(1, tt / 0.8) * np.minimum(1, (bar - tt) / 0.8)
        for d in chord:
            f = keys[d] / 2
            pad[s0:s1] += env * (np.sin(2 * math.pi * f * tt) + 0.3 * np.sin(4 * math.pi * f * tt))
        for i in range(8):  # Music box arpeggio
            if rng.random() < 0.18:
                continue
            note = keys[chord[i % 3]] * (2 if i % 4 == 3 else 1) * 2
            a = s0 + int(i * beat * sr)
            z = min(n, a + int(1.2 * sr))
            if a >= n:
                break
            nt = t[a:z] - t[a]
            box[a:z] += np.exp(-nt * 4.5) * (np.sin(2 * math.pi * note * nt) + 0.25 * np.sin(6 * math.pi * note * nt))
    mix = 0.10 * pad / 3 + 0.18 * box
    mix *= np.minimum(1, t / 2) * np.minimum(1, (t[-1] - t) / 2)  # Shuru/aakhir mein dheere
    data = (np.clip(mix, -1, 1) * 32767 * 0.8).astype("<i2")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return out


def _music_for(cfg: dict, seconds: float, work: Path, seed: int) -> Path:
    own = _pick_music(cfg)  # User ne music folder mein apni (muft/apni) music rakhi ho to wohi
    return Path(own) if own else soft_music(seconds, work / "music.wav", seed)


# ---------------------------------------------------------------- awaaz saaf
def clean_voice(src: Path, out: Path) -> Path:
    """User ki recording: shor (hum, pankha, gaariyan) kaato, awaaz saaf aur barabar karo."""
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-af",
         "highpass=f=80,lowpass=f=12000,"
         "afftdn=nf=-28:nr=18:tn=1,"                   # Background shor ka andaza laga kar kaato
         "agate=threshold=0.012:ratio=2:attack=5:release=180,"  # Khamoshi mein bacha shor dabao
         "equalizer=f=200:t=q:w=1:g=-2,equalizer=f=3200:t=q:w=1.2:g=3,"  # Bhaari-pan kam, alfaaz saaf
         "acompressor=threshold=0.08:ratio=3:attack=8:release=150:makeup=2,"
         "silenceremove=start_periods=1:start_threshold=-40dB,areverse,"
         "silenceremove=start_periods=1:start_threshold=-40dB,areverse,"
         "loudnorm=I=-16:TP=-1.5:LRA=9",
         "-ar", "48000", "-ac", "2", out])
    return out


def _silences(audio: Path) -> list:
    """Recording mein ruk (pause) kahan hain: [(beech ka waqt), ...]"""
    import subprocess
    r = subprocess.run(["ffmpeg", "-i", str(audio), "-af", "silencedetect=n=-38dB:d=0.22", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return [(a + b) / 2 for a, b in zip(starts, ends)]


def align(scenes: list, total: float, audio: Path) -> list:
    """User ki poori recording ko scenes mein baanto: alfaaz ke hisaab se andaza, phir qareebi
    ruk (pause) par kaato. Wapas: har scene ka (shuru, lambai)."""
    chars = [max(1, len(re.sub(r"\s+", "", s["narration"]))) for s in scenes]
    tot = sum(chars)
    pauses = _silences(audio)
    cuts, acc = [0.0], 0
    for c in chars[:-1]:
        acc += c
        guess = total * acc / tot
        near = [p for p in pauses if abs(p - guess) <= 1.8 and p > cuts[-1] + 0.8]
        cuts.append(min(near, key=lambda p: abs(p - guess)) if near else guess)
    cuts.append(total)
    return [(cuts[i], max(1.2, cuts[i + 1] - cuts[i])) for i in range(len(scenes))]


# -------------------------------------------------------------------- render
def _ass(path: Path, story: dict, timeline: list, size: tuple, fonts: Path):
    w, h = size
    tf = ensure_font(fonts, "latin")  # Awaaz Urdu, subtitles sirf English
    big = 74 if w < h else 64
    head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            # Kaali patti (box) ke upar safed bare alfaaz: har tasveer par parhe ja sakein
            f"Style: Line,{tf},{big},&H00FFFFFF,&H00FFFFFF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,3,16,0,2,60,60,"
            f"{int(h * (0.12 if w < h else 0.07))},-1",
            f"Style: Title,{tf},{int(big * 1.45)},&H0000E5FF,&H00FFFFFF,&H00301000,&H90000000,-1,0,0,0,100,100,0,0,1,9,3,8,60,60,"
            f"{int(h * (0.08 if w < h else 0.06))},-1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    def ts(x):
        cs = int(round(x * 100))
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

    def clean(s):
        return (s or "").replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ").strip()

    body = []
    pop = r"{\fad(150,100)\fscx90\fscy90\t(0,160,\fscx100\fscy100)}"
    title_end = min(3.5, timeline[0][1]) if timeline else 3
    title = story.get("title_english") or story.get("title_roman") or story["title"]
    body.append(f"Dialogue: 2,{ts(0.1)},{ts(title_end)},Title,,0,0,0,,{pop}{clean(title)}")
    for sc, (a, d) in zip(story["scenes"], timeline):
        text = sc.get("english") or sc["narration"]
        body.append(f"Dialogue: 1,{ts(a + 0.05)},{ts(a + d - 0.1)},Line,,0,0,0,,{pop}{clean(text)}")
    path.write_text("\n".join(head + body) + "\n", encoding="utf-8-sig")


def _scene_clip(img: Path, out: Path, secs: float, size: tuple, k: int):
    """Ek tasveer -> chalti video (dheere zoom ya ek taraf sarakna), halka fade."""
    w, h = size
    frames = max(2, int(secs * FPS))
    moves = [("min(zoom+0.0009,1.14)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
             ("1.12", f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"),
             ("max(1.14-0.0009*on,1.0)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
             ("1.12", f"(iw-iw/zoom)*(1-on/{frames})", "(ih-ih/zoom)/2")]
    z, x, y = moves[k % len(moves)]
    vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={FPS},"
          f"eq=saturation=1.12,fade=t=in:d=0.25,fade=t=out:st={max(0, secs - 0.25):.2f}:d=0.25,format=yuv420p")
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", img, "-vf", vf, "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), out])


def render(story: dict, sdir: Path, voice_track: Path, timeline: list, out: Path, cfg: dict):
    """Tasveerein + awaaz + subtitles + halki music = video."""
    size = SIZES[story["length"]]
    clips = []
    # Video 0 se shuru: pehla manzar shuru se, har agla apni awaaz ke waqt par
    starts = [0.0] + [a for a, _ in timeline[1:]]
    end = timeline[-1][0] + timeline[-1][1]
    for k in range(len(timeline)):
        secs = max(1.2, (starts[k + 1] if k + 1 < len(starts) else end) - starts[k])
        c = sdir / f"clip_{k:02d}.mp4"
        _scene_clip(sdir / f"scene_{k:02d}.jpg", c, secs, size, k)
        clips.append(c)
    lst = sdir / "clips.txt"
    lst.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    joined = sdir / "joined.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy",
         joined.name], cwd=sdir)
    total = duration(joined)
    ass = sdir / "subs.ass"
    _ass(ass, story, timeline, size, cfg["_fonts"])
    music = _music_for(cfg, total, sdir, story.get("seed", 0))
    vol = float(cfg["music"].get("volume", 0.12)) if _pick_music(cfg) else 0.9
    fc = (f"[0:v]subtitles=filename='{ffpath(ass, sdir)}':fontsdir='{ffpath(cfg['_fonts'], sdir)}'[v];"
          f"[1:a]aresample=48000,apad,atrim=0:{total:.3f},asplit=2[vo][vos];"
          f"[2:a]aresample=48000,volume={vol},atrim=0:{total:.3f},"
          f"afade=t=out:st={max(0, total - 2):.2f}:d=2[mu];"
          # Awaaz ke waqt music khud dheemi ho jaye (ducking), awaaz saaf rahe
          f"[mu][vos]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck];"
          f"[vo][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-15:TP=-1.5:LRA=11[a]")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = sdir / "final.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", joined.name, "-i", voice_track, "-stream_loop", "-1", "-i", music,
         "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}",
         "-movflags", "+faststart", tmp.name], cwd=sdir)
    shutil.copyfile(tmp, out)
    return out


def thumbnail(story: dict, sdir: Path, out: Path, cfg: dict):
    w, h = SIZES[story["length"]]
    if w > h:
        w, h = 1280, 720
    lf = ensure_font(cfg["_fonts"], "latin")
    ass = sdir / "thumb.ass"
    text = (story.get("thumbnail_text") or story.get("title_roman") or "").upper()
    ass.write_text("\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: T,{lf},{int(min(w, h) * 0.13)},&H0000E5FF,&H00FFFFFF,&H00301000,&H90000000,-1,0,0,0,100,100,0,0,1,"
        f"{int(min(w, h) * 0.012)},4,2,40,40,{int(h * 0.06)},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 1,0:00:00.00,0:00:05.00,T,,0,0,0,,{text}"]) + "\n", encoding="utf-8-sig")
    run(["ffmpeg", "-y", "-v", "error", "-i", "scene_00.jpg", "-vf",
         f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},eq=saturation=1.2:contrast=1.05,"
         f"subtitles=filename='{ffpath(ass, sdir)}':fontsdir='{ffpath(cfg['_fonts'], sdir)}'",
         "-frames:v", "1", "-q:v", "2", out], cwd=sdir)
    return out


# ------------------------------------------------------------------ bara kaam
def _sheet(story: dict) -> tuple:
    tags = " ".join("#" + re.sub(r"\s+", "", t.lstrip("#")) for t in story.get("hashtags", []))
    desc = f"{story.get('description', '').strip()}\n\n{tags}".strip()
    return story.get("yt_title") or story.get("title_roman") or story["title"], desc


def recording_script(story: dict) -> str:
    lines = [f"🎙️ Apni awaaz mein record karne ka tareeqa ({story['title']}):",
             "1. Neeche wali kahani ek dafa dil mein parh lein.",
             "2. Khamosh kamre mein, phone munh se ek baalisht (~20 cm) door rakhein.",
             "3. Isi message (ya video) par REPLY karein aur mic 🎤 dabaye rakh kar poori kahani "
             "ek saath parhein. Har number ke baad 1 second ruk jayein.",
             "4. Aaram se, pyaar se, jaise bachon ko kahani sunate hain. Ghalti ho jaye to ruk kar wahi "
             "jumla dobara parh lein, ya poori dobara bhej dein.",
             "Bot shor kaat kar, awaaz saaf karke, halki music ke saath video bana dega.", ""]
    for i, s in enumerate(story["scenes"], 1):
        lines.append(f"{i}. {s['narration']}")
    return "\n".join(lines)


def make_story(cfg: dict, topic: str, length: str = "short") -> dict:
    """Nayi kahani: script -> tasveerein -> Microsoft ki awaaz (namoona) -> video. Wapas: info."""
    length = "long" if length == "long" else "short"
    step("1/5  Kahani likh raha hoon (AI)")
    story = planner.write_story(cfg, topic, length)
    story["length"] = length
    story["seed"] = random.randint(1, 10 ** 6)
    sid = datetime.now().strftime("%Y%m%d-%H%M%S") + "_" + slug(story.get("title_roman") or "kahani", 30)
    sdir = Path(cfg["paths"]["work"]) / "stories" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    say(f"  📖 {story.get('title_roman')}  ({len(story['scenes'])} scenes) — seekh: {story.get('moral', '')[:80]}")

    step(f"2/5  Cartoon tasveerein bana raha hoon (0/{len(story['scenes'])})")
    made = 0
    for k, sc in enumerate(story["scenes"]):
        img = sdir / f"scene_{k:02d}.jpg"
        if _image(_prompt(story, sc), img, GEN[length], story["seed"]):
            made += 1
        else:
            _fallback_image(img, GEN[length], k)
        step(f"2/5  Cartoon tasveerein bana raha hoon ({k + 1}/{len(story['scenes'])})")
    story["images_ok"] = made

    step("3/5  Namoone ki awaaz (Microsoft) bana raha hoon")
    vcfg = dict(cfg, voice=dict(cfg["voice"], engine="edge"))  # User ne Microsoft wali kaha
    voice.USED.clear()
    parts, timeline, t = [], [], 0.3
    for k, sc in enumerate(story["scenes"]):
        wav = voice.speak(sc["narration"], sdir / f"v_{k:02d}", voice.styled(vcfg, "narrator"))
        d = duration(wav) + GAP
        parts.append((wav, t))
        timeline.append((t, d))
        t += d
    track = sdir / "guide_voice.wav"
    inputs, chains, labels = [], [], []
    for k, (wav, at) in enumerate(parts):
        inputs += ["-i", wav]
        ms = int(at * 1000)
        chains.append(f"[{k}:a]adelay={ms}|{ms}[a{k}]")
        labels.append(f"[a{k}]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex",
         ";".join(chains) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad,atrim=0:{t + 0.6:.3f}[a]",
         "-map", "[a]", "-ar", "48000", "-ac", "2", track])
    story["voice_note"] = voice.report()

    step("4/5  Video jorr raha hoon (tasveerein + awaaz + music)")
    name = f"kahani_{sid}"
    out = Path(cfg["paths"]["output"]) / f"{name}.mp4"
    render(story, sdir, track, timeline, out, cfg)
    step("5/5  Thumbnail aur title")
    thumb = thumbnail(story, sdir, out.with_suffix(".jpg"), cfg)
    title, desc = _sheet(story)
    (out.with_suffix(".txt")).write_text(
        f"TITLE:\n{title}\n\nDESCRIPTION:\n{desc}\n\nYouTube par: 'Yes, it's made for kids' zaroor chunein.\n",
        encoding="utf-8")
    write_json(sdir / "story.json", story)
    return {"id": sid, "dir": str(sdir), "video": str(out), "thumb": str(thumb), "title": title,
            "description": desc, "story": story}


def apply_recording(cfg: dict, sdir: Path, recording: Path) -> dict:
    """User ki awaaz: saaf karo, scenes mein baanto, wahi tasveerein + halki music = nayi video."""
    story = read_json(sdir / "story.json", None)
    if not story:
        raise BotError("Is kahani ki files nahi milin (shayad mita di gayin).")
    step("1/3  Aap ki awaaz saaf kar raha hoon (shor kaat raha hoon)")
    clean = clean_voice(recording, sdir / "my_voice.wav")
    total = duration(clean)
    if total < 3:
        raise BotError("Recording bohot chhoti hai. Poori kahani parh kar bhejein.")
    step("2/3  Awaaz ko tasveeron ke saath mila raha hoon")
    timeline = align(story["scenes"], total, clean)
    track = sdir / "my_voice_track.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", clean, "-af", f"adelay=300|300,apad,atrim=0:{total + 0.9:.3f}",
         "-ar", "48000", "-ac", "2", track])
    timeline = [(a + 0.3, d) for a, d in timeline]
    step("3/3  Video bana raha hoon (aap ki awaaz + halki music)")
    out = Path(cfg["paths"]["output"]) / f"kahani_{sdir.name}_meri-awaaz.mp4"
    render(story, sdir, track, timeline, out, cfg)
    title, desc = _sheet(story)
    return {"video": str(out), "title": title, "description": desc, "seconds": round(total)}


def save_note(sdir: Path, info: dict):
    (Path(sdir) / "telegram.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
