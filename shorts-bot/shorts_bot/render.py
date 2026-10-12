"""Video editing: 9:16 banana, captions, hook/outro, music, aakhri Short."""

import random
import re
import shutil
from pathlib import Path

from . import languages
from .util import duration, ensure_font, ffpath, hex_to_ass, run, say, video_size

W, H = 1080, 1920
AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def _video_args(cfg):
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(cfg["video"]["quality"]),
            "-pix_fmt", "yuv420p", "-r", str(cfg["video"]["fps"]),
            "-video_track_timescale", "15360", "-movflags", "+faststart"]


# ----------------------------------------------------------------- layout

def _face_track(video, start, end, sw, sh, cw):
    """Har aadhe second par sab se bara chehra dhoondo, crop ka x wapas karo."""
    import cv2

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video))
    scale = 480 / sw
    samples, t = [], start
    while t <= end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        x = None
        if ok:
            small = cv2.resize(frame, (480, int(sh * scale)))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
            if len(faces):
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                x = (fx + fw / 2) / scale
        samples.append((t - start, x))
        t += 0.5
    cap.release()

    center = sw / 2
    last = next((x for _, x in samples if x is not None), center)
    pieces = []  # (from_time, crop_x)
    cur = last
    pending = 0
    for rel, x in samples:
        x = last if x is None else x
        last = x
        if not pieces:
            pieces.append((0.0, x))
            cur = x
            continue
        if abs(x - cur) > sw * 0.12:
            pending += 1
            if pending >= 2:  # Do dafa naya jagah dikhe tabhi camera hilao
                pieces.append((max(0.0, rel - 0.5), x))
                cur, pending = x, 0
        else:
            pending = 0
    pieces = pieces[:60]
    return [(t, int(min(max(x - cw / 2, 0), sw - cw))) for t, x in pieces]


def build_layout(video, cfg, start, end):
    """9:16 ka filter banao. Wapas: (filter, caption_top_y, x_at(t) for face mode)."""
    sw, sh = video_size(video)
    fps = cfg["video"]["fps"]
    mode = cfg["video"]["layout"]
    cw = int(sh * 9 / 16) // 2 * 2

    if sw / sh < 0.8:  # Video pehle se khari (vertical) hai
        f = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}"
        return (lambda x=None: f), int(H * 0.66)

    if mode == "face" and cw <= sw:
        say("  Chehre dhoond raha hoon (face zoom)...")
        pieces = _face_track(video, start, end, sw, sh, cw)

        def face_filter(static_x=None):
            if static_x is not None:
                xexpr = str(static_x)
            else:
                # if(lt(t,t1),x0,if(lt(t,t2),x1,...)): har piece apne waqt tak
                xexpr = str(pieces[-1][1])
                for i in range(len(pieces) - 2, -1, -1):
                    xexpr = f"if(lt(t,{pieces[i + 1][0]:.2f}),{pieces[i][1]},{xexpr})"
            return f"crop={cw}:{sh}:'{xexpr}':0,scale={W}:{H},setsar=1,fps={fps}"

        face_filter.first_x = pieces[0][1]
        face_filter.last_x = pieces[-1][1]
        return face_filter, int(H * 0.64)

    fg_h = int(sh * W / sw) // 2 * 2
    fg_y = max(260, int(H * 0.40 - fg_h / 2))
    f = (f"split[bgs][fgs];[bgs]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
         f"boxblur=12:2,scale={W}:{H},eq=brightness=-0.18:saturation=1.2[bg];"
         f"[fgs]scale={W}:{fg_h}[fg];[bg][fg]overlay=0:{fg_y},setsar=1,fps={fps}")
    return (lambda x=None: f), fg_y + fg_h + 50


# --------------------------------------------------------------- captions

def _ass_text(s: str) -> str:
    return (s or "").replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


class Captions:
    def __init__(self, cfg, src_lang_code):
        fonts = cfg["_fonts"]
        cap = cfg["captions"]
        tgt = languages.get(cfg["language"]["target"])
        src = languages.get(src_lang_code)
        self.tfont = ensure_font(fonts, tgt["font"])
        self.nfont = ensure_font(fonts, languages.narration(cfg)["font"])
        self.thfont = ensure_font(fonts, languages.thumbnail(cfg)["font"])
        self.ofont = ensure_font(fonts, src["font"])
        self.lfont = ensure_font(fonts, "latin")
        self.cfg = cfg
        hi = hex_to_ass(cap["highlight_color"])
        self.styles = [
            # name, font, size, primary, outline colour, back, bold, borderstyle, outline, shadow, align, marginv
            ("Trans", self.tfont, cap["translation_size"], "&H00FFFFFF", "&H00000000", "&H96000000", -1, 1, 5, 2, 8, 0),
            ("Orig", self.ofont, cap["original_size"], hi, "&H00000000", "&H96000000", -1, 1, 3, 1, 8, 0),
            # Jis line ka tarjuma zaroori nahi: sirf asal (English) line, bari aur safed
            ("OrigBig", self.ofont, int(cap["translation_size"] * 0.82), "&H00FFFFFF", "&H00000000", "&H96000000", -1, 1, 5, 2, 8, 0),
            ("Hook", self.nfont, cap["hook_size"], "&H00FFFFFF", "&H40000000", "&H00000000", -1, 3, 22, 0, 5, 0),
            ("HookHi", self.nfont, cap["hook_size"], hi, "&H40000000", "&H00000000", -1, 3, 22, 0, 5, 0),
            ("Thumb", self.thfont, 128, hi, "&H00000000", "&HA0000000", -1, 1, 9, 4, 8, 0),
            ("Brand", self.lfont, 42, "&H40FFFFFF", "&H80000000", "&H00000000", -1, 1, 2, 0, 8, 110),
        ]

    def write(self, path: Path, events: list):
        head = [
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
            "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        ]
        # Aakhri "-1" (Encoding): libass khud direction pehchane, taake Urdu/Arabic mein
        # numbers aur English alfaaz sahi jagah aayein.
        for n, font, size, prim, outc, back, bold, bs, ol, sh, al, mv in self.styles:
            head.append(f"Style: {n},{font},{size},{prim},&H000000FF,{outc},{back},{bold},0,0,0,"
                        f"100,100,0,0,{bs},{ol},{sh},{al},80,80,{mv},-1")
        head += ["", "[Events]",
                 "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        body = [f"Dialogue: {layer},{_ts(a)},{_ts(b)},{style},,0,0,{mv},,{text}"
                for layer, a, b, style, mv, text in events]
        path.write_text("\n".join(head + body) + "\n", encoding="utf-8-sig")

    def brand(self, dur):
        ch = self.cfg["channel"]
        if not ch.get("show_name_on_video") or not ch.get("name"):
            return []
        return [(0, 0, dur, "Brand", 0, _ass_text(ch["name"]))]

    def main_events(self, lines, offset, top_y, dur):
        cap = self.cfg["captions"]
        pop = r"{\fad(60,0)\fscx88\fscy88\t(0,110,\fscx100\fscy100)}"
        ev = []
        for i, ln in enumerate(lines):
            a = ln["start"] - offset
            b = (lines[i + 1]["start"] - offset) if i + 1 < len(lines) else min(ln["end"] - offset + 0.6, dur)
            b = max(b, a + 0.4)
            translated = (ln.get("translated") or "").strip()
            needs_tr = cap["show_translation"] and translated and translated != ln["original"]
            parts = []
            if needs_tr:
                parts.append(_ass_text(translated))
            if cap["show_original"] or not needs_tr:
                prefix = r"\N{\rOrig}" if parts else ""
                parts.append(prefix + _ass_text(ln["original"]))
            if parts:
                style = "Trans" if needs_tr else ("OrigBig" if cap["show_original"] or not cap["show_translation"] else "Orig")
                ev.append((1, a, b, style, top_y, pop + "".join(parts)))
        return ev + self.brand(dur)

    def thumb_events(self, text):
        lines = []
        for x in (text or "").splitlines():
            if not x.strip():
                continue
            x = _ass_text(x).upper()
            if re.fullmatch(r"PART \d+", x):  # "PART 1" English font mein (Urdu font ke number chhote)
                x = "{\\fn" + self.lfont + "}" + x
            lines.append(x)
        return [(1, 0, 5, "Thumb", 230, r"\N".join(lines))] + self.brand(5)

    def card_events(self, text, dur, highlight=False):
        style = "HookHi" if highlight else "Hook"
        anim = r"{\fad(120,0)\fscx70\fscy70\t(0,180,\fscx104\fscy104)\t(180,260,\fscx100\fscy100)}"
        return [(1, 0.05, dur, style, 0, anim + _ass_text(text))] + self.brand(dur)


# ----------------------------------------------------------------- render

def _subs_filter(ass: Path, cwd: Path, fonts: Path) -> str:
    return f"subtitles=filename='{ffpath(ass, cwd)}':fontsdir='{ffpath(fonts, cwd)}'"


def _frame(video, t, layout_f, out_png, cwd):
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", video,
         "-filter_complex", f"[0:v]{layout_f}[v]", "-map", "[v]", "-frames:v", "1", out_png], cwd=cwd)


def _card(png, wav, text, out, caps, cfg, cwd, highlight):
    dur = duration(wav) + 0.35
    ass = out.with_suffix(".ass")
    caps.write(ass, caps.card_events(text, dur, highlight))
    fps = cfg["video"]["fps"]
    frames = int(dur * fps) + 1
    vf = (f"[0:v]scale={W * 2}:{H * 2},zoompan=z='min(zoom+0.0009,1.10)':"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={fps},"
          f"eq=brightness=-0.10,{_subs_filter(ass, cwd, cfg['_fonts'])}[v];"
          f"[1:a]apad,atrim=0:{dur:.3f}[a]")
    run(["ffmpeg", "-y", "-v", "error", "-i", png, "-i", wav, "-filter_complex", vf,
         "-map", "[v]", "-map", "[a]", "-frames:v", str(frames), "-t", f"{dur:.3f}",
         *_video_args(cfg), *AUDIO, out], cwd=cwd)
    return out


def render_short(src: dict, clip: dict, voices: dict, cfg: dict, work: Path, final: Path,
                 src_lang: str) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    cwd = work
    video = src["video"]
    start = max(0.0, clip["start"] - 0.15)
    end = clip["end"] + 0.35
    dur = end - start
    caps = Captions(cfg, src_lang)
    layout, top_y = build_layout(video, cfg, start, end)
    parts = []

    if voices.get("hook"):
        say("  Hook bana raha hoon...")
        png = work / "first.png"
        _frame(video, start, layout(getattr(layout, "first_x", None)), png, cwd)
        parts.append(_card(png, voices["hook"], clip["hook_on_screen"], work / "1_hook.mp4",
                           caps, cfg, cwd, highlight=True))

    say("  Asal clip edit ho raha hai (captions ke saath)...")
    ass = work / "main.ass"
    caps.write(ass, caps.main_events(clip["lines"], start, top_y, dur))
    extra_in, audio_in = [], "[0:a]"
    if cfg.get("dub", {}).get("enabled") and clip.get("dub", True):  # Asal baat ki jagah Urdu dubbing
        from .dub import make_track
        extra_in, audio_in = ["-i", make_track(video, clip, cfg, work, start, dur)], "[1:a]"
    fc = (f"[0:v]{layout()},{_subs_filter(ass, cwd, cfg['_fonts'])}[v];"
          f"{audio_in}aresample=48000,loudnorm=I=-14:TP=-1.5:LRA=11,"
          f"afade=t=in:d=0.08,afade=t=out:st={dur - 0.25:.3f}:d=0.25[a]")
    main = work / "2_main.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", video,
         *extra_in, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *_video_args(cfg), *AUDIO,
         main], cwd=cwd)
    parts.append(main)

    if voices.get("outro"):
        say("  Outro bana raha hoon...")
        png = work / "last.png"
        _frame(video, end - 0.1, layout(getattr(layout, "last_x", None)), png, cwd)
        parts.append(_card(png, voices["outro"], clip["outro_on_screen"], work / "3_outro.mp4",
                           caps, cfg, cwd, highlight=False))

    lst = work / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst.name,
         "-c", "copy", joined.name], cwd=cwd)

    music = _pick_music(cfg)
    final.parent.mkdir(parents=True, exist_ok=True)
    if music:
        total = duration(joined)
        vol = float(cfg["music"]["volume"])
        run(["ffmpeg", "-y", "-v", "error", "-i", joined, "-stream_loop", "-1", "-i", music,
             "-filter_complex",
             f"[1:a]aresample=48000,volume={vol},afade=t=in:d=1,"
             f"afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[m];"
             f"[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", *AUDIO, "-t", f"{total:.3f}",
             "-movflags", "+faststart", final])
    else:
        shutil.move(str(joined), str(final))  # replace() alag drive (C: -> D:) par nahi chalta
    return final


def _best_frame_time(video, start, end):
    """Clip mein woh lamha dhoondo jahan chehra sab se bara ho (thumbnail ke liye)."""
    try:
        import cv2
    except Exception:
        return start + (end - start) * 0.4
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video))
    best_t, best_area = start + (end - start) * 0.4, 0
    for k in range(1, 13):
        t = start + (end - start) * k / 13
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (480, int(h * 480 / w)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 6, minSize=(40, 40))
        area = max((fw * fh for _, _, fw, fh in faces), default=0)
        sharp = cv2.Laplacian(gray, cv2.CV_64F).var()  # Dhundla frame na ho
        score = area * min(sharp / 100, 1.5)
        if score > best_area:
            best_t, best_area = t, score
    cap.release()
    return best_t


def make_thumbnail(src: dict, clip: dict, cfg: dict, work: Path, out: Path, src_lang: str) -> Path:
    """9:16 thumbnail: sab se achha frame + bara text."""
    work.mkdir(parents=True, exist_ok=True)
    video = src["video"]
    t = _best_frame_time(video, clip["start"], clip["end"])
    layout, _ = build_layout(video, cfg, t, t + 0.5)
    png = work / "thumb_frame.png"
    _frame(video, t, layout(getattr(layout, "first_x", None)), png, work)
    caps = Captions(cfg, src_lang)
    ass = work / "thumb.ass"
    caps.write(ass, caps.thumb_events(clip.get("thumbnail_text") or clip["hook_on_screen"]))
    vf = (f"eq=contrast=1.12:saturation=1.25:brightness=-0.03,vignette=PI/5,"
          f"{_subs_filter(ass, work, cfg['_fonts'])}")
    run(["ffmpeg", "-y", "-v", "error", "-i", png, "-vf", vf, "-frames:v", "1", "-q:v", "2",
         out], cwd=work)
    return out


def _pick_music(cfg):
    m = cfg["music"]
    if not m.get("enabled"):
        return None
    folder = Path(m["folder"])
    files = [p for p in folder.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")] \
        if folder.exists() else []
    return random.choice(files) if files else None
