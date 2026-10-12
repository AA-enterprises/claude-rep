"""Claude se viral moments chunwana aur har Short ki script likhwana."""

import json
import os
import re

import anthropic

from . import languages
from .util import BotError, fmt_time, say

# In models par server-side refusal fallback chalta hai
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

SYSTEM_TEMPLATE = """You are the head editor of a fast-growing YouTube Shorts channel that turns long podcasts and interviews into short, high-retention clips with translated captions and a narrator's commentary in the viewer's language.

Your job for each podcast:
1. Find the moments most likely to get millions of views as standalone Shorts: a surprising claim, a strong opinion, a personal story with a twist, a money or success lesson, a funny exchange, an emotional confession, a hot take, or a clear useful tip. The clip must make sense on its own, without the rest of the episode. Start on a line that grabs attention immediately (never on a filler word or mid-thought) and end on a payoff line, not mid-sentence.
2. Translate the spoken lines in the clip into the caption language, naturally and briefly, the way a native speaker would say it, so it reads well as an on-screen caption. Keep names and brand names as they are.
3. Write a narrator hook and outro in the spoken narrator language. The narrator is {narrator} talking straight to the viewer, like a friend sharing something they just heard. In languages with grammatical gender (Urdu, Hindi, Arabic, French, ...), use the verb and adjective forms that match a {gender} narrator.
   - Hook (spoken before the clip over fast action footage): ONE punchy sentence of 6 to 12 words, at most 3 seconds when spoken. A striking question or a bold, specific fact from the clip that stops a scrolling viewer, ending on a tease. Never give the punchline away. Do not lie or exaggerate beyond what the clip delivers.
   - Outro (spoken after the clip): one or two very short sentences, at most 4 seconds when spoken: a sharp takeaway specific to this clip and a question that makes viewers comment. Never generic.
   - Every hook and outro must use a different opening and structure. Avoid formula phrases you have used before (a list of previous hooks may be given).
4. Write thumbnail_text: 2 to 5 punchy words in the thumbnail language that make people tap (a number, a shocking claim or a strong emotion from the clip, e.g. the equivalent of "HE LOST EVERYTHING"). Honest, no fake claims.
5. Write YouTube metadata: a title under 70 characters that is curiosity-driven but honest, a 2-3 line description, and 5-8 relevant hashtags.

Rules:
- Pick clips that do not overlap and come from different parts of the episode when possible.
- Never choose segments that are ads, sponsor reads, intros, or outros of the podcast itself.
- Avoid clips whose main content is hate, harassment, graphic violence, or dangerous medical or financial advice that could hurt viewers; YouTube demonetizes these.
- Write the narrator text exactly as it should be spoken by a text-to-speech voice: no emojis, no hashtags, no stage directions, numbers written the way they are read aloud in the spoken narrator language."""


NARRATORS = {
    "female": ("a warm, confident young woman", "female"),
    "male": ("a deep-voiced, serious male storyteller, like the narrator of a popular Urdu mystery and documentary channel: calm, heavy and gripping", "male"),
    "child": ("a cheerful, curious girl of about ten, speaking simply and with wonder", "female"),
}


def _system(cfg: dict) -> str:
    narrator, gender = NARRATORS.get(cfg["voice"].get("gender"), NARRATORS["female"])
    return SYSTEM_TEMPLATE.format(narrator=narrator, gender=gender)


VOICE_KINDS = ["narrator", "man", "young_man", "old_man", "woman", "girl", "boy"]


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
                    "properties": {"index": {"type": "integer"}, "text": {"type": "string"},
                                   "voice": {"type": "string", "enum": VOICE_KINDS}},
                    "required": ["index", "text", "voice"],
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


ROUTER_SYSTEM = """You are the command router of a Telegram bot that makes YouTube Shorts. The user writes casually, often in Roman Urdu or Urdu, sometimes starting with "/". Decide what they want and return exactly one action:
- "source": make Shorts from one of the listed safe channels. Put the channel key in "source". Pick the channel whose topic best fits (e.g. Mars, robots, rovers -> jpl; Earth, Sun, galaxies -> goddard; general space -> nasa).
- "cc": make Shorts from a Creative Commons YouTube search. Put a short English search phrase in "topic" (e.g. "business podcast").
- "link": they gave a YouTube link. Put it in "url". Set "permission" true only if they clearly say they have permission.
- "edit": they want to change the title, description or thumbnail of a Short they already got.
- "help": they ask for the list of commands or what the bot can do.
- "chat": anything else: greetings, small talk, how are you, jokes, questions about YouTube, Shorts, views, titles, niches, the channel, or any general question. Answer it yourself in "reply".
- "unknown": only if the message is empty or meaningless.
For "source", "cc" and "link" also fill in the shape of what they want (use 0 / "default" when they don't say):
- "mode": "single" if they want separate stand-alone Shorts (e.g. "ek video bana do", "1 short 30 sec ka"); "series" if they want one longer scene split into consecutive parts (e.g. "2 minute ki video ke 3-4 clips", "part 1 part 2"); else "default".
- "count": how many Shorts or parts (max 5). "3 ya 4" -> pick the one that fits the length best.
- "seconds": length of each Short or part in seconds, at most 60. If they give a total scene length and a number of parts, divide it (e.g. 2 minutes in 3 parts -> 40). "1 minute se andar" -> 55.
In "reply", write one short friendly Roman Urdu sentence telling them exactly what you will make (how many, how long).
For "chat": you are the friendly assistant of the YouTube channel "Lakhon Ki Baat" (Shorts about space, science and stories, from NASA, US government and Creative Commons videos, dubbed in Urdu). Talk like a helpful Pakistani friend: casual Roman Urdu, warm, a little humour, 1 to 4 short sentences, practical YouTube growth advice when asked. Never invent things the bot can't do; if they seem to want a Short, suggest an example command like "mars ki 1 video 30 sec ki". Use the recent conversation for context."""


def route_message(cfg: dict, text: str, source_names: dict, has_short: bool, history: list = None) -> dict:
    """Telegram par aam baat ko command mein badlo."""
    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["source", "cc", "link", "edit", "help", "chat", "unknown"]},
            "source": {"type": "string"}, "count": {"type": "integer"}, "topic": {"type": "string"},
            "mode": {"type": "string", "enum": ["single", "series", "default"]},
            "seconds": {"type": "integer"},
            "url": {"type": "string"}, "permission": {"type": "boolean"}, "reply": {"type": "string"},
        },
        "required": ["action", "source", "count", "topic", "url", "permission", "mode", "seconds", "reply"],
        "additionalProperties": False,
    }
    channels = "\n".join(f"- {k}: {v}" for k, v in source_names.items())
    prompt = (f"Safe channels:\n{channels}\n\nThe user has {'already received a Short' if has_short else 'not received any Short yet'}."
              + ("\n\nRecent conversation:\n" + "\n".join(history[-8:]) if history else "")
              + f"\n\nMessage:\n{text}")
    return ask_claude(cfg, ROUTER_SYSTEM, prompt, schema, effort="low")


def make_plan(src: dict, transcript: dict, cfg: dict, used: list, recent_hooks: list) -> dict:
    target = languages.get(cfg["language"]["target"])
    narr = languages.narration(cfg)
    thumb = languages.thumbnail(cfg)
    spoken = languages.voice(cfg)
    source = languages.get(transcript.get("language") or "en")
    c = cfg["clips"]
    segs = transcript["segments"]
    lines = "\n".join(f"[{s['i']}] ({fmt_time(s['start'])}-{fmt_time(s['end'])}) {s['text']}" for s in segs)

    parts = [
        f"Podcast: {src.get('title') or 'unknown'}",
        f"Channel: {src.get('channel') or 'unknown'}",
        f"Spoken language: {source['name']}",
        f"Caption translation language: {target['name']}",
        f"Language for the spoken narrator hook_voice and outro_voice: {spoken['name']}",
        f"Language for hook_on_screen and outro_on_screen: {narr['name']}",
        f"Language for thumbnail_text: {thumb['name']} (keep the word PART and its number in English letters)",
        _title_rule(cfg["language"]["title_style"], narr if narr["code"] != target["code"] else target),
    ]
    series = c.get("mode") == "series"
    if series:
        n, sec = int(c.get("parts", 3)), int(c.get("part_seconds", 50))
        # part_seconds = poora part (intro + clip + outro); clip ko ~7 second kam
        sec_clip = max(10, sec - 7)
        lo, hi = max(8, sec_clip - 7), sec_clip + 2
        parts += [
            SERIES_RULES.format(n=n, sec=sec_clip, lo=lo, hi=hi, total=n * sec_clip),
            "Give a translation for every segment index from start_index to end_index, inclusive.",
        ]
    else:
        parts += [
            f"Number of clips: {c['per_video']}",
            f"Each clip (from the start of segment start_index to the end of segment end_index) "
            f"must last between {c['min_seconds']} and {c['max_seconds']} seconds. Check the timestamps.",
            "Give a translation for every segment index from start_index to end_index, inclusive.",
        ]
    dub = cfg.get("dub", {}).get("enabled") and target["code"] != source["code"]
    if dub:
        parts.append(
            "DUBBING: every translation will be spoken by a voice actor over the video at the same "
            "time as the original line, replacing it. So translate EVERY segment (never leave one empty), "
            "in natural spoken everyday language (not bookish), and keep each translation about as short "
            "as the original so it fits the same seconds. Write numbers as words.\n"
            "For every translation also set 'voice' to match WHO is speaking that segment, so the dub "
            "sounds like the person on screen: old_man (an elderly man, e.g. a retired astronaut "
            "interviewed decades later), young_man, man (adult man, middle-aged), woman, girl, boy, "
            "or narrator (an off-screen documentary or story narrator, e.g. a NASA video explaining the "
            "Moon). Use the names, dates and context in the transcript to judge age. Keep the same "
            "voice for the same person throughout.")
    hook_g = "female" if cfg["voice"].get("gender") != "male" else "male"
    outro_g = "male" if (cfg["voice"].get("outro_gender") or hook_g) == "male" else "female"
    parts.append(f"hook_voice is spoken by a {hook_g} narrator and outro_voice by a {outro_g} narrator: "
                 "use the matching grammatical gender in each.")
    if cfg["captions"].get("smart_translation", True) and target["code"] != source["code"] and not dub:
        parts.append(
            "Captions show the original line and, under it, the translation. For each segment decide if "
            "the translation is really needed for a viewer who knows basic English: for very simple or "
            "universally understood lines (e.g. 'Wow!', 'Thank you', 'Yes, exactly', names, numbers) give "
            "an empty string as the translation so only the original shows; translate everything whose "
            "meaning matters for the story.")
    if target["code"] == source["code"]:
        parts.append("The caption language is the spoken language, so 'translations' should be "
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
    if series:
        plan["clips"] = _series(plan.get("clips", []), segs, {"min_seconds": lo, "max_seconds": hi}, used)
    else:
        plan["clips"] = _validate(plan.get("clips", []), segs, c, used)
    if not plan["clips"]:
        raise BotError("Is video mein munasib clips nahi mile.")
    for clip in plan["clips"]:
        clip["dub"] = bool(dub)  # Video pehle hi Urdu mein ho to dubbing nahi
    return plan


SERIES_RULES = """SERIES MODE: Instead of separate moments, choose ONE continuous, gripping scene or story from the video (about {total} seconds in total) and split it into exactly {n} consecutive parts, returned in order in "clips" as Part 1 to Part {n}.
- Part k+1 must start at the segment right after Part k ends: no gaps, no overlap, so viewers see the whole scene across the parts.
- Each part must last between {lo} and {hi} seconds (aim for {sec}). Cut each part on a line that leaves the viewer wanting more (a question, a reveal about to happen, a tense pause), never mid-word.
- hook_voice: one short sentence (at most 3 seconds). Part 1 builds suspense about what is coming without spoiling it. Later parts give a few-word recap and raise the tension again. Speak in the spoken narrator language.
- outro_voice: at most 4 seconds. Every part except the last ends on a cliffhanger and tells viewers to watch the next part (e.g. the equivalent of "What happened next? Watch Part 2."). The last part gives the payoff and asks viewers a question.
- title: the same series name for all parts plus "| Part k", e.g. "Mars par aakhri 7 minute | Part 1".
- thumbnail_text: 2-5 words and must include "PART k".
- hook_on_screen and outro_on_screen follow the same idea, short."""


def _series(clips: list, segs: list, c: dict, used: list) -> list:
    """Series ke parts: tarteeb se aur lagataar. Har part pichle part ke khatam hone ke
    agle segment se shuru hota hai; lambai theek ki jati hai. Scene toote to wahin ruk jao."""
    n = len(segs)
    lo, hi = c["min_seconds"], c["max_seconds"]
    taken = [tuple(u) for u in used]
    good = []
    for k, clip in enumerate(sorted(clips, key=lambda x: int(x.get("start_index", 0))), 1):
        a = good[-1]["end_index"] + 1 if good else max(0, min(int(clip["start_index"]), n - 1))
        if a >= n:
            break
        b = max(a, min(int(clip["end_index"]), n - 1))
        while b > a and segs[b]["end"] - segs[a]["start"] > hi:
            b -= 1
        while b + 1 < n and segs[b]["end"] - segs[a]["start"] < lo:
            b += 1
        if segs[b]["end"] - segs[a]["start"] < lo * 0.6:
            break
        if any(not (b < x or a > y) for x, y in taken):
            break
        clip = _finish(clip, a, b, segs)
        clip["part"] = k
        tag = f"Part {k}"
        if tag.lower() not in clip["title"].lower():
            clip["title"] = f"{clip['title']} | {tag}"
        if f"part {k}" not in clip.get("thumbnail_text", "").lower():
            clip["thumbnail_text"] = f"{clip.get('thumbnail_text', '')}\nPART {k}".strip()
        good.append(clip)
    for clip in good:
        clip["parts_total"] = len(good)
    return good


def _plain(text: str) -> str:
    """YouTube captions ke <b>, <i>, <font> jaise tags hatao."""
    return re.sub(r"</?[a-zA-Z][^>]*>", "", text or "").strip()


def _finish(clip: dict, a: int, b: int, segs: list) -> dict:
    """Clip ke segments, captions (translation na ho to asal text) aur waqt bharo."""
    tr = {int(t["index"]): t["text"].strip() for t in clip.get("translations", [])}
    vo = {int(t["index"]): t.get("voice", "") for t in clip.get("translations", [])}
    clip["start_index"], clip["end_index"] = a, b
    clip["lines"] = [
        {"start": segs[i]["start"], "end": segs[i]["end"], "original": _plain(segs[i]["text"]),
         # Khaali = AI ke mutabiq tarjume ki zaroorat nahi (sirf English dikhegi)
         "translated": tr.get(i, segs[i]["text"]), "voice": vo.get(i, "")}
        for i in range(a, b + 1)
    ]
    clip["start"] = segs[a]["start"]
    clip["end"] = segs[b]["end"]
    return clip


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
        good.append(_finish(clip, a, b, segs))
    return good
