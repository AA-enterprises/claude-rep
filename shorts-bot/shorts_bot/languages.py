"""Har zubaan ki settings: voice, font aur likhne ki direction.

Nayi zubaan add karni ho to LANGUAGES mein ek entry aur FONTS mein us ka
font daal dein.
"""

NF = "https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/"
CJK = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/"
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"

# font key -> (family name inside the file, file name, download url)
# Sirf "static" fonts: variable aur Nastaliq fonts video mein dabbe (boxes) bana dete
# hain, is liye Urdu ke liye Naskh (saaf, parhne mein aasaan) istemal hota hai.
FONTS = {
    "latin": ("Poppins", "Poppins-Bold.ttf", GF + "poppins/Poppins-Bold.ttf"),
    "noto": ("Noto Sans", "NotoSans-Bold.ttf", NF + "NotoSans/hinted/ttf/NotoSans-Bold.ttf"),
    "naskh": ("Noto Naskh Arabic", "NotoNaskhArabic-Bold.ttf", NF + "NotoNaskhArabic/hinted/ttf/NotoNaskhArabic-Bold.ttf"),
    "devanagari": ("Noto Sans Devanagari", "NotoSansDevanagari-Bold.ttf", NF + "NotoSansDevanagari/hinted/ttf/NotoSansDevanagari-Bold.ttf"),
    "bengali": ("Noto Sans Bengali", "NotoSansBengali-Bold.ttf", NF + "NotoSansBengali/hinted/ttf/NotoSansBengali-Bold.ttf"),
    "jp": ("Noto Sans CJK JP", "NotoSansCJKjp-Bold.otf", CJK + "Japanese/NotoSansCJKjp-Bold.otf"),
    "kr": ("Noto Sans CJK KR", "NotoSansCJKkr-Bold.otf", CJK + "Korean/NotoSansCJKkr-Bold.otf"),
    "sc": ("Noto Sans CJK SC", "NotoSansCJKsc-Bold.otf", CJK + "SimplifiedChinese/NotoSansCJKsc-Bold.otf"),
}

# name -> code, display name (for the AI), font key, edge voices (female, male)
# "child": asli bachche ki awaaz jahan Microsoft deta hai. Baaqi zubaanon mein larki
# ki awaaz ki pitch ooncha karke bachche jaisi awaaz banti hai (voice.py dekhein).
LANGUAGES = {
    "urdu": {"code": "ur", "name": "Urdu (Pakistani, Urdu script)", "font": "naskh",
             "voices": ("ur-PK-UzmaNeural", "ur-PK-AsadNeural")},
    "roman": {"code": "ur-latn",
              "name": "Roman Urdu (Urdu written in English/Latin letters, the casual way Pakistanis type on their phones, e.g. 'Mars ka raaz', 'Ye kya hua?')",
              "font": "latin", "voices": ("ur-PK-UzmaNeural", "ur-PK-AsadNeural")},
    "english": {"code": "en", "name": "English", "font": "latin",
                "voices": ("en-US-JennyNeural", "en-US-GuyNeural"), "child": "en-US-AnaNeural"},
    "hindi": {"code": "hi", "name": "Hindi (Devanagari script)", "font": "devanagari",
              "voices": ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural")},
    "arabic": {"code": "ar", "name": "Arabic (Modern Standard)", "font": "naskh",
               "voices": ("ar-SA-ZariyahNeural", "ar-SA-HamedNeural")},
    "french": {"code": "fr", "name": "French", "font": "latin",
               "voices": ("fr-FR-DeniseNeural", "fr-FR-HenriNeural")},
    "german": {"code": "de", "name": "German", "font": "latin",
               "voices": ("de-DE-KatjaNeural", "de-DE-ConradNeural")},
    "spanish": {"code": "es", "name": "Spanish", "font": "latin",
                "voices": ("es-ES-ElviraNeural", "es-ES-AlvaroNeural")},
    "turkish": {"code": "tr", "name": "Turkish", "font": "latin",
                "voices": ("tr-TR-EmelNeural", "tr-TR-AhmetNeural")},
    "portuguese": {"code": "pt", "name": "Portuguese (Brazil)", "font": "latin",
                   "voices": ("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural")},
    "italian": {"code": "it", "name": "Italian", "font": "latin",
                "voices": ("it-IT-ElsaNeural", "it-IT-DiegoNeural")},
    "indonesian": {"code": "id", "name": "Indonesian", "font": "latin",
                   "voices": ("id-ID-GadisNeural", "id-ID-ArdiNeural")},
    "bengali": {"code": "bn", "name": "Bengali", "font": "bengali",
                "voices": ("bn-BD-NabanitaNeural", "bn-BD-PradeepNeural")},
    "russian": {"code": "ru", "name": "Russian", "font": "noto",
                "voices": ("ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural")},
    "japanese": {"code": "ja", "name": "Japanese", "font": "jp",
                 "voices": ("ja-JP-NanamiNeural", "ja-JP-KeitaNeural")},
    "korean": {"code": "ko", "name": "Korean", "font": "kr",
               "voices": ("ko-KR-SunHiNeural", "ko-KR-InJoonNeural")},
    "chinese": {"code": "zh", "name": "Chinese (Simplified)", "font": "sc",
                "voices": ("zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural")},
}

_BY_CODE = {v["code"]: k for k, v in LANGUAGES.items()}


def get(name_or_code: str) -> dict:
    """Zubaan ka naam ("urdu") ya code ("ur", "en-US") dein, settings wapas milengi."""
    key = (name_or_code or "english").strip().lower()
    key = {"roman urdu": "roman", "roman-urdu": "roman", "urdu roman": "roman"}.get(key, key)
    if key in LANGUAGES:
        return {"key": key, **LANGUAGES[key]}
    if key in _BY_CODE:  # Poora code pehle (jaise "ur-latn" = Roman Urdu)
        k = _BY_CODE[key]
        return {"key": k, **LANGUAGES[k]}
    short = key.split("-")[0].split("_")[0]
    if short in _BY_CODE:
        k = _BY_CODE[short]
        return {"key": k, **LANGUAGES[k]}
    # Na-maloom zubaan: AI phir bhi likh dega, font Noto Sans, voice config se.
    return {"key": key, "code": short, "name": key.title(), "font": "noto", "voices": ("", "")}


def narration(cfg: dict) -> dict:
    """Awaaz, screen ka text, title, thumbnail kis zubaan mein (language.narration).
    "same" ya khaali = captions wali zubaan (language.target)."""
    n = (cfg["language"].get("narration") or "same").strip().lower()
    return get(cfg["language"]["target"] if n in ("same", "") else n)


def thumbnail(cfg: dict) -> dict:
    """Thumbnail ka text kis zubaan mein (thumbnail.language). "same" = narration wali."""
    t = (cfg.get("thumbnail", {}).get("language") or "same").strip().lower()
    return narration(cfg) if t in ("same", "") else get(t)
