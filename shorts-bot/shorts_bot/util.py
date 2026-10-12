import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import languages


class BotError(Exception):
    """Aisi galti jo user ko saaf alfaaz mein dikhani hai."""


def say(msg: str):
    print(msg, flush=True)


STEP_HOOK = None  # Telegram ka "video ban rahi hai" message har qadam par badalne ke liye


def step(msg: str):
    print(f"\n▶ {msg}", flush=True)
    if STEP_HOOK:
        try:
            STEP_HOOK(msg)
        except Exception:
            pass


def run(cmd: list, cwd=None) -> str:
    """Command chalao; fail ho to aakhri error lines dikhao."""
    proc = subprocess.run(
        [str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        tail = "\n".join(err[-15:])
        raise BotError(f"Command fail hui: {Path(str(cmd[0])).name}\n{tail}")
    return proc.stdout.decode("utf-8", "replace")


def require_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise BotError(
                f"'{tool}' nahi mila. README ke Step 2 ke mutabiq FFmpeg install karein "
                "(Windows: winget install Gyan.FFmpeg) aur naya terminal kholein."
            )


def duration(path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path])
    return float(out.strip() or 0)


def video_size(path) -> tuple:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height", "-of", "csv=p=0:s=x", path])
    w, h = out.strip().splitlines()[0].split("x")[:2]
    return int(w), int(h)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def slug(text: str, limit=40) -> str:
    s = re.sub(r"[^\w\-]+", "-", text, flags=re.UNICODE).strip("-")
    return (s[:limit].strip("-") or "video").lower()


def fmt_time(sec: float) -> str:
    sec = max(0, int(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def ensure_font(fonts_dir: Path, key: str) -> str:
    """Font folder mein na ho to download karo. Font family ka naam wapas karo."""
    family, filename, url = languages.FONTS[key]
    fonts_dir.mkdir(parents=True, exist_ok=True)
    target = fonts_dir / filename
    if not target.exists() or target.stat().st_size < 10_000:
        say(f"  Font download ho raha hai: {family}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "shorts-bot"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except Exception as e:  # network ka masla
            raise BotError(f"Font download nahi hua ({family}): {e}") from e
        target.write_bytes(data)
    return family


def hex_to_ass(color: str) -> str:
    """#RRGGBB -> ASS ka &H00BBGGRR."""
    c = color.lstrip("#")
    if len(c) != 6:
        c = "FFFFFF"
    return f"&H00{c[4:6]}{c[2:4]}{c[0:2]}".upper()


def ffpath(path: Path, cwd: Path) -> str:
    """ffmpeg filter ke andar file ka rasta (Windows par bhi chale)."""
    try:
        rel = os.path.relpath(path, cwd)
    except ValueError:  # Windows: alag drive
        rel = str(path)
    rel = rel.replace("\\", "/")
    return rel.replace(":", r"\:").replace("'", r"\'")


def console_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
