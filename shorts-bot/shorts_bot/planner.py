"""Claude se viral moments chunwana aur har Short ki script likhwana."""

import json
import os

import anthropic

from . import languages
from .util import BotError, fmt_time, say

# In models par server-side refusal fallback chalta hai
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

SYSTEM_TEMPLATE = """You are the head editor of a fast-growing YouTube Shorts channel that turns long podcasts and interviews into short, high-retention clips with translated captions and a narrator's commentary in the viewer's language.

Your job for each podcast:
1. Find the moments most likely to get millions of views as standalone Shorts: a surprising claim, a strong opinion, a personal story with a twist, a money or success lesson, a funny exchange, an emotional confession, a hot take, or a clear useful tip. The clip must make sense on its own, without the rest of the episode. Start on a line that grabs attention immediately (never on a filler word or mid-thought) and end on a payoff line, not mid-sentence.
2. Translate every spoken line in the clip into the target language, naturally and briefly, the way a native speaker would say it, so it reads well as an on-screen caption. Keep names and brand names as they are.
3. Write a narrator hook and outro in the target language. The narrator is {narrator} talking straight to the viewer, like a friend sharing something they just heard. In languages with grammatical gender (Urdu, Hindi, Arabic, French, ...), use the verb and adjective forms that match a {gender} narrator.
   - Hook (spoken before the clip): one or two short sentences, about 2-4 seconds when spoken. Create curiosity about what the speaker is about to say without giving the punchline away. Do not lie or exaggerate beyond what the clip delivers.
   - Outro (spoken after the clip): two or three short sentences, about 6-10 seconds when spoken. Add real value of your own: the lesson, why it matters, or a sharp opinion, then end with a question that makes viewers comment. This commentary is what makes the channel original, so it must be specific to this clip, never generic.
   - Every hook and outro must use a different opening and structure. Avoid formula phrases you have used before (a list of previous hooks may be given).
4. Write thumbnail_text: 2 to 5 punchy words in the target language that make people tap (a number, a shocking claim or a strong emotion from the clip, e.g. the equivalent of "HE LOST EVERYTHING"). Honest, no fake claims.
5. Write YouTube metadata: a title under 70 characters that is curiosity-driven but honest, a 2-3 line description, and 5-8 relevant hashtags.

Rules:
- Pick clips that do not overlap and come from different parts of the episode when possible.
- Never choose segments that are ads, sponsor reads, intros, or outros of the podcast itself.
- Avoid clips whose main content is hate, harassment, graphic violence, or dangerous medical or financial advice that could hurt viewers; YouTube demonetizes these.
- Write the narrator text exactly as it should be spoken by a text-to-speech voice: no emojis, no hashtags, no stage directions, numbers written the way they are read aloud in the target language."""


NARRATORS = {
    "female": ("a warm, confident young woman", "female"),
    "male": ("a warm, confident young man", "male"),
    "child": ("a cheerful, curious girl of about ten, speaking simply and with wonder", "female"),
}


def _system(cfg: dict) -> str:
    narrator, gender = NARRATORS.get(cfg["voice"].get("gender"), NARRATORS["female"])
    return SYSTEM_TEMPLATE.format(narrator=narrator, gender=gender)


def _schema():
    clip = {
        "type": "object",
        "properties": {
            "start_index": {"type": "integer"},
            "end_index": {"type": "integer"},
            "category": {"type": "string"},
            "why_it_will_go_viral": {"type": "string"},
            "hook_voice": {"type": "string"},
            "hook_on_screen": {"type": "string"},
            "thumbnail_text": {"type": "string"},
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"index": {"type": "integer"}, "text": {"type": "string"}},
                    "required": ["index", "text"],
                    "additionalProperties": False,
                },
            },
            "outro_voice": {"type": "string"},
            "outro_on_screen": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["start_index", "end_index", "category", "why_it_will_go_viral",
                     "hook_voice", "hook_on_screen", "thumbnail_text", "translations", "outro_voice",
                     "outro_on_screen", "title", "description", "hashtags"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "speakers": {"type": "string"},
            "clips": {"type": "array", "items": clip},
        },
        "required": ["speakers", "clips"],
        "additionalProperties": False,
    }


def _title_rule(style: str, target: dict) -> str:
    if style == "english":
        return "Write title and description in English."
    if style == "roman":
        return (f"Write title and description in {target['name'].split(' (')[0]} using Latin "
                "letters (romanized, the way people type it on their phones, e.g. Roman Urdu), "
                "mixing in common English words where natural.")
    return f"Write title and description in {target['name']}."


def ask_claude(cfg: dict, system: str, prompt: str, schema: dict, effort: str = "high") -> dict:
    """Claude se JSON jawab lo (structured output). Saari ghaltiyan Urdu BotError mein."""
    model = cfg["ai"]["model"]
    kwargs = dict(
        model=model,
        max_tokens=64000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if model in FALLBACK_MODELS:
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise BotError("ANTHROPIC_API_KEY set nahi. README ka Step 4 dekhein (.env file).")
    try:
        client = anthropic.Anthropic()
        if "betas" in kwargs:
            with client.beta.messages.stream(**kwargs) as stream:
                resp = stream.get_final_message()
        else:
            with client.messages.stream(**kwargs) as stream:
                resp = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise BotError("ANTHROPIC_API_KEY ghalat hai ya set nahi. README ka Step 4 dekhein.") from e
    except anthropic.PermissionDeniedError as e:
        raise BotError(f"API key ko is model ki ijazat nahi: {e}") from e
    except anthropic.RateLimitError as e:
        raise BotError("AI ki limit poori ho gayi. Thori der baad dobara chalayein "
                       "(ya console.anthropic.com par credit check karein).") from e
    except anthropic.BadRequestError as e:
        if "credit" in str(e).lower():
            raise BotError("Anthropic account mein credit khatam. console.anthropic.com > Billing.") from e
        raise BotError(f"AI ne request qubool nahi ki: {e}") from e
    except anthropic.APIStatusError as e:
        raise BotError(f"AI server ka masla ({e.status_code}). Thori der baad chalayein.") from e
    except anthropic.APIConnectionError as e:
        raise BotError("Internet ka masla: AI se rabta nahi hua.") from e

    if resp.stop_reason == "refusal":
        raise BotError("AI ne is kaam se inkaar kiya (content policy). Doosri video/baat try karein.")
    if resp.stop_reason == "max_tokens":
        raise BotError("AI ka jawab adhoora reh gaya. clips.per_video kam karke dobara chalayein.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise BotError("AI ka jawab samajh nahi aaya. Dobara chalayein.") from e


EDIT_SYSTEM = """You help a YouTube Shorts creator polish one Short's metadata. You get the current title, description and thumbnail text, plus the creator's request (often in Roman Urdu or Urdu). Apply exactly what they ask and keep everything else unchanged. Keep titles under 70 characters, curiosity-driven but honest. Thumbnail text: 2-5 punchy words. Keep the same language and script as the current text unless the creator asks otherwise. Never remove the credit line or hashtags from the description unless asked. In 'reply', tell the creator in one short Roman Urdu sentence what you changed."""


def edit_metadata(cfg: dict, current: dict, request: str) -> dict:
    """Telegram par user ki baat ('title zyada chatpata karo') ke mutabiq title/description/thumbnail badlo."""
    schema = {
        "type": "object",
        "properties": {k: {"type": "string"} for k in ("title", "description", "thumbnail_text", "reply")},
        "required": ["title", "description", "thumbnail_text", "reply"],
        "additionalProperties": False,
    }
    prompt = (f"Current title:\n{current['title']}\n\nCurrent description:\n{current['description']}\n\n"
              f"Current thumbnail text:\n{current['thumbnail_text']}\n\nCreator's request:\n{request}")
    return ask_claude(cfg, EDIT_SYSTEM, prompt, schema, effort="low")


def make_plan(src: dict, transcript: dict, cfg: dict, used: list, recent_hooks: list) -> dict:
    target = languages.get(cfg["language"]["target"])
    source = languages.get(transcript.get("language") or "en")
    c = cfg["clips"]
    segs = transcript["segments"]
    lines = "\n".join(f"[{s['i']}] ({fmt_time(s['start'])}-{fmt_time(s['end'])}) {s['text']}" for s in segs)

    parts = [
        f"Podcast: {src.get('title') or 'unknown'}",
        f"Channel: {src.get('channel') or 'unknown'}",
        f"Spoken language: {source['name']}",
        f"Target language for captions, narrator hook and outro: {target['name']}",
        _title_rule(cfg["language"]["title_style"], target),
        f"Number of clips: {c['per_video']}",
        f"Each clip (from the start of segment start_index to the end of segment end_index) "
        f"must last between {c['min_seconds']} and {c['max_seconds']} seconds. Check the timestamps.",
        "Give a translation for every segment index from start_index to end_index, inclusive.",
    ]
    if target["code"] == source["code"]:
        parts.append("The target language is the spoken language, so 'translations' should be "
                     "the cleaned-up original text (fix spelling and punctuation only).")
    if c.get("focus"):
        parts.append(f"Prefer clips about: {c['focus']}")
    if used:
        parts.append("These segment ranges were already used for earlier Shorts. Do not reuse or "
                     "overlap them: " + ", ".join(f"{a}-{b}" for a, b in used))
    if recent_hooks:
        parts.append("Recent hooks already published on the channel (do not repeat their wording "
                     "or structure):\n- " + "\n- ".join(recent_hooks[-25:]))
    parts.append("Transcript (segment index, time, text):\n" + lines)
    prompt = "\n\n".join(parts)

    say(f"  AI ({cfg['ai']['model']}) best moments dhoond raha hai aur script likh raha hai...")
    plan = ask_claude(cfg, _system(cfg), prompt, _schema(), effort=cfg["ai"]["effort"])
    plan["clips"] = _validate(plan.get("clips", []), segs, c, used)
    if not plan["clips"]:
        raise BotError("Is video mein munasib clips nahi mile.")
    return plan


def _validate(clips: list, segs: list, c: dict, used: list) -> list:
    """AI ke chune hue hisson ko check aur theek karo."""
    n = len(segs)
    lo, hi = c["min_seconds"], c["max_seconds"]
    taken = [tuple(u) for u in used]
    good = []
    for clip in clips:
        a = max(0, min(int(clip["start_index"]), n - 1))
        b = max(a, min(int(clip["end_index"]), n - 1))
        # Bohot lamba: aakhir se segment hatao
        while b > a and segs[b]["end"] - segs[a]["start"] > hi:
            b -= 1
        # Bohot chhota: aage segment jorro
        while b + 1 < n and segs[b]["end"] - segs[a]["start"] < lo:
            b += 1
        if segs[b]["end"] - segs[a]["start"] < lo * 0.6:
            continue
        if any(not (b < x or a > y) for x, y in taken):
            continue
        taken.append((a, b))
        tr = {int(t["index"]): t["text"].strip() for t in clip.get("translations", [])}
        clip["start_index"], clip["end_index"] = a, b
        clip["lines"] = [
            {"start": segs[i]["start"], "end": segs[i]["end"], "original": segs[i]["text"],
             "translated": tr.get(i) or segs[i]["text"]}
            for i in range(a, b + 1)
        ]
        clip["start"] = segs[a]["start"]
        clip["end"] = segs[b]["end"]
        good.append(clip)
    return good
