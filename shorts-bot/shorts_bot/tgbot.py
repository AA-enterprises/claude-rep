"""Telegram se bot chalana: /nasa, /cc, /link se Shorts mangwana, aur reply se
title / description / thumbnail badalna.

Sirf aap ki chat (TELEGRAM_CHAT_ID) ke messages mane jate hain."""

import copy
import os
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from . import planner, render, sources, telegram
from .util import BotError, read_json, say, write_json

HELP = """🤖 Shorts Bot commands

📥 Short mangwana:
/nasa  → NASA ki nayi video se series (Part 1, 2, 3)
/nasa 4  → 4 parts ki series
/jpl  /goddard  /whitehouse  → doosre mehfooz channels
/cc business podcast  → Creative Commons videos mein se (topic likhein)
/link https://youtube.com/...  → apna link (sirf Creative Commons)
/link https://... ijazat  → ijazat wali video (aap zimmedar)
/sources  → saare channels ki list

✏️ Short badalna (Short ke kisi message par REPLY karein; reply na karein to aakhri Short badlega):
/title naya title
/desc nayi description
/thumb naya thumbnail text
Ya seedha likhein, jaise: "title aur chatpata karo" ya "thumbnail par SHOCKING likho"

💬 Commands yaad na hon to apni zubaan mein likh dein, jaise:
"mars wali video ka short bana do", "space ke 2 short bhejo", "business podcast ka short chahiye"

/help  → ye list"""


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = read_json(path, {"offset": 0, "shorts": {}, "msg": {}, "last": None})

    def save(self):
        write_json(self.path, self.data)

    def add_short(self, info: dict, msg_ids: list):
        key = Path(info["video"]).stem
        self.data["shorts"][key] = info
        for m in msg_ids:
            self.data["msg"][str(m)] = key
        self.data["last"] = key
        # Purane record (200 se zyada) hata do
        if len(self.data["shorts"]) > 200:
            for old in list(self.data["shorts"])[:-200]:
                self.data["shorts"].pop(old, None)
        self.save()

    def target(self, reply_to: int):
        key = self.data["msg"].get(str(reply_to)) if reply_to else None
        key = key or self.data.get("last")
        return key, self.data["shorts"].get(key) if key else None


def _rewrite_sheet(txt: Path, title: str, desc: str):
    """Upload sheet (.txt) mein title aur description badlo, baaqi waisa hi."""
    if not txt.exists():
        return
    s = txt.read_text(encoding="utf-8")
    s = re.sub(r"(TITLE \(copy karein\):\n).*?(\n\nDESCRIPTION \(copy karein\):\n)",
               lambda m: m.group(1) + title + m.group(2), s, count=1, flags=re.S)
    s = re.sub(r"(DESCRIPTION \(copy karein\):\n).*?(\n\n---------- Sirf)",
               lambda m: m.group(1) + desc + m.group(2), s, count=1, flags=re.S)
    txt.write_text(s, encoding="utf-8")


class TelegramBot:
    def __init__(self, cfg: dict, process):
        self.cfg = cfg
        self.process = process
        self.chat = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
        self.state = State(cfg["paths"]["output"] / "telegram-state.json")

    # ------------------------------------------------------------ helpers
    def reply(self, text: str, to: int = None) -> list:
        try:
            return telegram.send_message(text, reply_to=to)
        except BotError as e:
            say(f"  ⚠️  Telegram jawab nahi gaya: {e}")
            return []

    def on_short(self, info: dict):
        say("  📲 Telegram par bhej raha hoon...")
        try:
            ids = telegram.send_short(Path(info["video"]), info["title"], info["description"],
                                      Path(info["thumb"]) if info.get("thumb") else None)
        except BotError as e:
            say(f"  ⚠️  Telegram par nahi gaya: {e}")
            ids = []
        self.state.add_short(info, ids)

    def _args(self, strict: bool):
        return SimpleNamespace(yes=False, strict=strict)

    def _cfg(self, count: int = None):
        """count = series ke parts (series mode) ya alag Shorts (single mode)."""
        cfg = copy.deepcopy(self.cfg)
        if count:
            key = "parts" if cfg["clips"]["mode"] == "series" else "per_video"
            cfg["clips"][key] = count
        return cfg

    # ----------------------------------------------------------- commands
    def make_from_source(self, key: str = None, topic: str = None, count: int = None, to: int = None):
        what = f"'{topic}' (Creative Commons)" if topic else key
        self.reply(f"⏳ {what}: nayi video dhoond raha hoon...", to)
        vids, kind, note = sources.candidates(self.cfg, key=key, topic=topic)
        if not vids:
            self.reply("😕 Koi nayi munasib video nahi mili. Doosra channel/topic try karein.", to)
            return
        made = 0
        for url, title in vids[:6]:  # CC search mein kuch videos CC nahi niklti: agli try karo
            self.reply(f"🎬 Video: {title[:80]}\n{url}\n⏳ Short ban raha hai (5-15 minute)...", to)
            try:
                permission = f"Public domain: {note}" if kind == "public_domain" else None
                out = self.process(url, self._cfg(count), self._args(strict=True),
                                   on_short=self.on_short, permission=permission)
                made += len(out)
                break
            except BotError as e:
                if "bot\" samajh" in str(e):  # YouTube ne roka: agli video bhi ruk jayegi
                    self.reply("❌ " + str(e), to)
                    return
                self.reply(f"⚠️ Ye video nahi chali: {str(e)[:300]}\nAgli try kar raha hoon...", to)
        if not made:
            self.reply("😕 Short nahi ban saka. Computer ki screen par tafseel dekhein.", to)

    def make_from_link(self, url: str, allowed: bool, to: int = None):
        self.reply("⏳ Short ban raha hai (5-15 minute)...", to)
        permission = "User ne Telegram par ijazat confirm ki" if allowed else None
        try:
            out = self.process(url, self._cfg(),
                               self._args(strict=not allowed),
                               on_short=self.on_short, permission=permission)
            if not out:
                self.reply("😕 Short nahi bana.", to)
        except BotError as e:
            hint = ("\nAgar is video ki ijazat aap ke paas hai to likhein:\n/link " + url + " ijazat"
                    if "Creative Commons nahi" in str(e) else "")
            self.reply(f"❌ {str(e)[:400]}{hint}", to)

    def edit(self, msg: dict, field: str = None, value: str = None, request: str = None):
        to = msg["message_id"]
        reply_to = (msg.get("reply_to_message") or {}).get("message_id")
        key, info = self.state.target(reply_to)
        if not info:
            self.reply("Abhi koi Short nahi bana jise badla ja sake. Pehle /nasa ya /cc chalayein.", to)
            return
        new = {k: info[k] for k in ("title", "description", "thumbnail_text")}
        if field:
            new[field] = value
            note = "✅ Badal diya."
        else:
            self.reply("⏳ AI aap ki baat samajh kar badal raha hai...", to)
            res = planner.edit_metadata(self.cfg, new, request)
            note = "✅ " + res.pop("reply", "Badal diya.")
            new.update({k: (res.get(k) or new[k]).strip() for k in new})
        thumb_changed = new["thumbnail_text"] != info["thumbnail_text"]
        info.update(new)
        _rewrite_sheet(Path(info["txt"]), info["title"], info["description"])
        ids = self.reply(f"{note}\n\n📋 TITLE:\n{info['title']}\n\n📋 DESCRIPTION:\n{info['description']}", to)
        if thumb_changed and info.get("thumb"):
            clip = dict(info["clip"], thumbnail_text=info["thumbnail_text"])
            try:
                render.make_thumbnail({"video": Path(info["media"])}, clip, self.cfg,
                                      Path(info["cwork"]), Path(info["thumb"]), info["lang"])
                ids.append(telegram.send_document(Path(info["thumb"]), "🖼️ Nayi thumbnail"))
            except Exception as e:  # Thumbnail na bane to bhi baaqi badlav mehfooz
                self.reply(f"⚠️ Nayi thumbnail nahi bani: {str(e)[:200]}", to)
        for m in ids:
            self.state.data["msg"][str(m)] = key
        self.state.data["shorts"][key] = info
        self.state.save()

    def handle(self, msg: dict):
        text = (msg.get("text") or "").strip()
        to = msg["message_id"]
        if not text:
            return
        say(f"\n📩 Telegram: {text[:80]}")
        cmd, _, rest = text.partition(" ")
        cmd = cmd.lower().split("@")[0]
        rest = rest.strip()
        srcs = sources.load(self.cfg["_base"])
        if cmd in ("/start", "/help"):
            self.reply(HELP, to)
        elif cmd == "/sources":
            lines = [f"/{k}  → {v.get('name', k)}" for k, v in srcs.items()]
            self.reply("📺 Mehfooz channels:\n" + "\n".join(lines)
                       + "\n\n/cc topic  → Creative Commons search", to)
        elif cmd == "/cc":
            if not rest:
                self.reply("Topic bhi likhein, jaise: /cc business podcast", to)
            else:
                self.make_from_source(topic=rest, to=to)
        elif cmd == "/link":
            parts = rest.split()
            if not parts or not parts[0].startswith("http"):
                self.reply("Link bhi likhein, jaise: /link https://www.youtube.com/watch?v=...", to)
            else:
                allowed = any(p.lower() in ("ijazat", "permission", "haan") for p in parts[1:])
                self.make_from_link(parts[0], allowed, to)
        elif cmd in ("/title", "/desc", "/thumb"):
            if not rest:
                self.reply(f"Naya text bhi likhein, jaise: {cmd} ...", to)
            else:
                field = {"/title": "title", "/desc": "description", "/thumb": "thumbnail_text"}[cmd]
                self.edit(msg, field=field, value=rest)
        elif cmd.startswith("/") and cmd[1:] in srcs and (not rest or rest.isdigit()):
            count = max(1, min(int(rest), 5)) if rest.isdigit() else None
            self.make_from_source(key=cmd[1:], count=count, to=to)
        else:  # Aam baat (/ ke saath ya baghair): AI samjhe ke kya chahiye
            self.understand(msg, text.lstrip("/").strip(), srcs)

    def understand(self, msg: dict, text: str, srcs: dict):
        to = msg["message_id"]
        is_reply = bool((msg.get("reply_to_message") or {}).get("message_id"))
        names = {k: v.get("name", k) for k, v in srcs.items()}
        r = planner.route_message(self.cfg, text, names, bool(self.state.data.get("last")))
        act = r["action"]
        if is_reply and act in ("unknown", "help"):
            act = "edit"  # Short par reply = usi ko badalna
        if act != "edit" and r.get("reply"):
            self.reply("🤖 " + r["reply"], to)
        if act == "source" and r.get("source") in srcs:
            n = int(r.get("count") or 0)
            self.make_from_source(key=r["source"], count=max(1, min(n, 5)) if n else None, to=to)
        elif act == "cc" and r.get("topic"):
            self.make_from_source(topic=r["topic"], to=to)
        elif act == "link" and r.get("url", "").startswith("http"):
            self.make_from_link(r["url"], bool(r.get("permission")), to)
        elif act == "edit":
            self.edit(msg, request=text)
        elif act == "help":
            self.reply(HELP, to)
        else:
            self.reply("Ye baat samajh nahi aayi 🙏 Misal: \"mars ka short bhejo\", "
                       "\"/nasa 2\", \"title chatpata karo\". Saari commands: /help", to)

    # ------------------------------------------------------------- loop
    def run(self):
        if not telegram.enabled():
            raise BotError("Telegram jura nahi. Pehle: python bot.py --telegram-setup")
        me = telegram._call("getMe")
        say(f"✅ Telegram bot @{me.get('username')} sun raha hai. Telegram par /help bhejein.")
        say("   (Ye window khuli rakhein. Band karne ke liye Ctrl + C.)")
        self.reply("🟢 Bot on ho gaya. /help se commands dekhein.")
        while True:
            try:
                updates = telegram._call(
                    "getUpdates", timeout=40,
                    data={"offset": self.state.data.get("offset", 0), "timeout": 25,
                          "allowed_updates": '["message"]'})
            except BotError as e:
                say(f"⚠️  Telegram se rabta toota ({str(e)[:120]}). 15 second baad dobara...")
                time.sleep(15)
                continue
            for u in updates:
                self.state.data["offset"] = u["update_id"] + 1
                self.state.save()
                msg = u.get("message") or {}
                if str((msg.get("chat") or {}).get("id")) != self.chat:
                    continue  # Sirf aap ki chat
                try:
                    self.handle(msg)
                except BotError as e:
                    self.reply(f"❌ {str(e)[:500]}", msg.get("message_id"))
                except Exception as e:  # Bot band na ho: ghalti likh kar agla message
                    log = self.cfg["paths"]["work"] / "error-log.txt"
                    log.parent.mkdir(parents=True, exist_ok=True)
                    with open(log, "a", encoding="utf-8") as f:
                        f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M} telegram\n{traceback.format_exc()}")
                    self.reply(f"❌ Bot mein ghalti: {type(e).__name__}: {str(e)[:200]}\n"
                               f"Tafseel computer par: {log}", msg.get("message_id"))


def run(cfg: dict, process):
    TelegramBot(cfg, process).run()
