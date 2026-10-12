from pathlib import Path

import yaml

from .util import BotError

DEFAULTS = {
    "channel": {"name": "My Channel", "show_name_on_video": True},
    "language": {"target": "urdu", "source": "auto", "title_style": "roman"},
    "voice": {"engine": "edge", "fallback_google": True, "gender": "female", "edge_voice": "", "rate": "+5%",
              "pitch": "+0Hz", "child_rate": "+8%", "child_pitch": "+45Hz",
              "elevenlabs_voices": {"female": "", "male": "", "child": ""},
              "elevenlabs_voice_id": "", "elevenlabs_model": "eleven_v3"},
    "ai": {"model": "claude-opus-5-5", "effort": "high"},
    "clips": {"per_video": 3, "min_seconds": 20, "max_seconds": 50, "hook": True,
              "outro": True, "focus": ""},
    "video": {"layout": "blur", "download": "parts", "max_download_height": 1080, "fps": 30, "quality": 20},
    "captions": {"show_translation": True, "show_original": True, "translation_size": 84,
                 "original_size": 50, "hook_size": 96, "highlight_color": "#FFD60A"},
    "music": {"enabled": True, "folder": "music", "volume": 0.10},
    "transcript": {"prefer_youtube_captions": True, "engine": "auto", "whisper_model": "small"},
    "safety": {"ask_permission": True},
    "telegram": {"send": True},
    "thumbnail": {"make": True},
    "paths": {"output": "output", "work": "work"},
}


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
    except FileNotFoundError:
        user = {}
    except yaml.YAMLError as e:
        raise BotError(f"config.yaml mein likhne ki galti hai:\n{e}") from e
    cfg = _merge(DEFAULTS, user)
    # Aap ki apni settings (update se kabhi nahi badalti): config.local.yaml
    local_path = Path(path).with_name("config.local.yaml")
    if local_path.exists():
        try:
            with open(local_path, encoding="utf-8-sig") as f:
                cfg = _merge(cfg, yaml.safe_load(f) or {})
        except yaml.YAMLError as e:
            raise BotError(f"config.local.yaml mein likhne ki galti hai:\n{e}") from e
    base = Path(path).resolve().parent
    cfg["_base"] = base
    for key in ("output", "work"):
        cfg["paths"][key] = (base / cfg["paths"][key]).resolve()
    cfg["music"]["folder"] = (base / cfg["music"]["folder"]).resolve()
    cfg["_fonts"] = base / "fonts"
    try:  # Jaise "D:/Shorts": folder na ho to bana do
        cfg["paths"]["output"].mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BotError(f"Shorts save karne ka folder nahi ban saka: {cfg['paths']['output']}\n"
                       f"config.yaml mein paths.output check karein (drive mojood hai?). {e}") from e
    c = cfg["clips"]
    if c["min_seconds"] >= c["max_seconds"]:
        raise BotError("config.yaml: clips.min_seconds, max_seconds se chhota hona chahiye.")
    return cfg
