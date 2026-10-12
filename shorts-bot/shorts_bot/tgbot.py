"""Telegram se bot chalana: /nasa, /cc, /link se Shorts mangwana, aur reply se
title / description / thumbnail badalna.

Sirf aap ki chat (TELEGRAM_CHAT_ID) ke messages mane jate hain."""

import collections
import copy
import inspect
import os
import queue
import re
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from . import planner, render, sources, telegram
from .download import BOT_CHECK
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
/status  → abhi kya ban raha hai, line mein kya hai
/awaaz  → saari awaazon ke namoone (aur batata hai Microsoft lagi ya Google backup)
/awaaz 2  → 2 number wali awaaz channel ki awaaz bana do
/awaaz tez  ya  /awaaz dheemi  → kahani wali awaaz ki raftar
/save ASAD  → abhi wali awaaz "ASAD" naam se save (kisi namoone par reply karke bhejein to wohi)
/awaaz ASAD  → save ki hui awaaz lagao (aur namoona sunao)
Video par REPLY karke "awaaz ASAD"  → wahi video ASAD ki awaaz mein dobara
/gemini  → insaan jaisi awaaz (Gemini) lagane ka tareeqa
/update  → bot ka naya version abhi lao (waise bhi khud har 30 minute check karta hai)

✏️ Short badalna (Short ke kisi message par REPLY karein; reply na karein to aakhri Short badlega):
/title naya title
/desc nayi description
/thumb naya thumbnail text
Ya seedha likhein, jaise: "title aur chatpata karo" ya "thumbnail par SHOCKING likho"

💬 Commands yaad na hon to apni zubaan mein likh dein, jaise:
"mars ki 1 video bana do 30 sec ki"
"mars ki 2 minute ki video ke 3 clips, 1 minute se kam"
"business podcast ka short chahiye"

🗣️ Gap-shap bhi kar saktay hain: "kaise ho?", "views kaise barhayein?", "acha title batao"

🎙️ Awaaz: poori video Urdu mein (intro, beech, outro). Video mein jaisa banda ho waisi
awaaz (buddha/jawan/aurat); kahani ya documentary ho to bhaari narrator awaaz.

/help  → ye list"""


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data = read_json(path, {"offset": 0, "shorts": {}, "msg": {}, "last": None})
        self.lock = threading.RLock()  # Short banane wala aur message sunne wala saath chalte hain

    def save(self):
        with self.lock:
            write_json(self.path, self.data)

    def add_short(self, info: dict, msg_ids: list):
        with self.lock:
            self._add_short(info, msg_ids)

    def _add_short(self, info: dict, msg_ids: list):
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


class Progress:
    """Video bante waqt chat mein 'ban rahi hai' ka nishan: upar "sending video..." aur ek
    message jo har qadam par badalta hai. Video aate hi message hat jata hai."""
    SPIN = "◐◓◑◒"

    def __init__(self, bot, to, desc: str):
        self.bot, self.to, self.desc = bot, to, desc
        self.text = "Shuru ho raha hai..."
        self.n = 0
        self.mid = None
        self.started = time.time()
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self._show()
        threading.Thread(target=self._loop, daemon=True).start()

    def _body(self) -> str:
        m = re.match(r"(\d)/5\s+(.*)", self.text)
        k, what = (int(m.group(1)), m.group(2)) if m else (0, self.text)
        bar = "▰" * k + "▱" * (5 - k)
        secs = int(time.time() - self.started)
        return (f"{self.SPIN[self.n % 4]} 🎬 Video ban rahi hai: {self.desc}\n"
                f"{bar}  {what}\n⏱️ {secs // 60}:{secs % 60:02d}  (tayyar hote hi yahan aa jayegi)")

    def _show(self):
        with self.lock:
            if self.stop.is_set():
                return
            try:
                if self.mid is None:
                    self.mid = telegram.send_message(self._body(), self.to)[0]
                else:
                    telegram._call("editMessageText", data={"chat_id": self.bot.chat,
                                                            "message_id": self.mid, "text": self._body()})
            except BotError:
                pass

    def _loop(self):
        tick = 0
        while not self.stop.wait(4):
            tick += 1
            try:  # Chat ke upar "sending video..." (5 second tak rehta hai, is liye har 4 second)
                telegram._call("sendChatAction", data={"chat_id": self.bot.chat, "action": "upload_video"})
            except BotError:
                pass
            if tick % 3 == 0:  # Har 12 second message mein waqt/ghoomta nishan
                self.n += 1
                self._show()

    def update(self, text: str):
        self.text = text
        self.n += 1
        self._show()

    def hide(self):
        """Video bhejne se pehle nishan hatao (series ka agla part aaye to naya ban jata hai)."""
        with self.lock:
            if self.mid is not None:
                try:
                    telegram._call("deleteMessage", data={"chat_id": self.bot.chat, "message_id": self.mid})
                except BotError:
                    pass
                self.mid = None

    def finish(self):
        self.hide()
        self.stop.set()


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
    def __init__(self, cfg: dict, process, updater=None, update_available=None):
        self.cfg = cfg
        self.process = process
        self.updater = updater                  # GitHub se naya code (bot.self_update)
        self.update_available = update_available
        self.restart = False
        self.update_wanted = None               # /update aaya lekin Short ban raha tha
        self.chat = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
        self.state = State(cfg["paths"]["output"] / "telegram-state.json")
        self.jobs = queue.Queue()   # Shorts ek ek karke bante hain (line)
        self.current = None         # Abhi kya ban raha hai
        self.progress = None        # Chat mein "video ban rahi hai" ka nishan
        self.chat_log = collections.deque(maxlen=12)  # Haal ki baatein (gap-shap ke liye)
        # Bheje gaye awaaz ke namoone: message id -> awaaz ki settings (restart ke baad bhi yaad)
        self.voice_msgs = {int(k): v for k, v in (self.state.data.get("voices") or {}).items()}
        self.last_voice = None  # Sab se aakhri namoone ki settings
        threading.Thread(target=self._worker, daemon=True).start()

    # ------------------------------------------------------------- line (queue)
    def _worker(self):
        while True:
            desc, fn, to, kwargs = self.jobs.get()
            self.current = desc
            from . import util
            try:
                self.progress = Progress(self, to, desc)
                util.STEP_HOOK = self.progress.update
                self._safe(fn, to, **kwargs)
            finally:
                util.STEP_HOOK = None
                if self.progress:
                    self.progress.finish()
                self.progress = None
                self.current = None
                self.jobs.task_done()

    def queue_job(self, desc: str, fn, to: int = None, **kwargs):
        ahead = self.jobs.qsize() + (1 if self.current else 0)
        self.jobs.put((desc, fn, to, kwargs))
        if ahead:
            self.reply(f"✅ Line mein laga diya: {desc}\nAap se pehle {ahead} kaam hai, bari aate hi shuru "
                       "hoga. Is dauran title/thumbnail badalna aur /status chalta rahega.", to)

    def _safe(self, fn, to, *args, **kwargs):
        """Kaam chalao; ghalti ho to bot band na ho, Telegram par ek dafa batao."""
        try:
            if "to" in inspect.signature(fn).parameters:
                fn(*args, to=to, **kwargs)
            else:
                fn(*args, **kwargs)
        except BotError as e:
            self.fail(str(e)[:600], to)
        except Exception as e:
            log = self.cfg["paths"]["work"] / "error-log.txt"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M} telegram\n{traceback.format_exc()}")
            self.reply(f"❌ Bot mein ghalti: {type(e).__name__}: {str(e)[:200]}\n"
                       f"Tafseel computer par: {log}", to)

    def status(self, to: int = None):
        if not self.current and self.jobs.empty():
            self.reply("😴 Abhi koi kaam nahi chal raha. Naya Short mangwayein!", to)
            return
        waiting = [d for d, *_ in list(self.jobs.queue)]
        lines = [f"⚙️ Abhi ban raha hai: {self.current}"] if self.current else []
        lines += [f"{i}. {d}" for i, d in enumerate(waiting, 1)]
        self.reply("\n".join(lines) if not waiting else "\n".join(lines[:1] + ["⏳ Line mein:"] + lines[1:]), to)

    # ------------------------------------------------------------ helpers
    def reply(self, text: str, to: int = None) -> list:
        try:
            return telegram.send_message(text, reply_to=to)
        except BotError as e:
            say(f"  ⚠️  Telegram jawab nahi gaya: {e}")
            return []

    def on_short(self, info: dict):
        say("  📲 Telegram par bhej raha hoon...")
        if self.progress:  # "Ban rahi hai" hatao, phir video
            self.progress.hide()
        try:
            ids = telegram.send_short(Path(info["video"]), info["title"], info["description"],
                                      Path(info["thumb"]) if info.get("thumb") else None)
        except BotError as e:
            say(f"  ⚠️  Telegram par nahi gaya: {e}")
            ids = []
        if info.get("voice_note"):
            self.reply(info["voice_note"])
        self.state.add_short(info, ids)

    def _args(self, strict: bool):
        return SimpleNamespace(yes=False, strict=strict)

    def _cfg(self, count: int = None, mode: str = None, seconds: int = None):
        """Is dafa ke liye: kitne (count), kis tarah (single/series), har ek kitne second."""
        cfg = copy.deepcopy(self.cfg)
        c = cfg["clips"]
        if mode in ("single", "series"):
            c["mode"] = mode
        elif count == 1:  # "1 video" = ek alag Short, "Part 1" wali series nahi
            c["mode"] = "single"
        if count:
            c["parts" if c["mode"] == "series" else "per_video"] = max(1, min(int(count), 5))
        if seconds:
            sec = max(15, min(int(seconds), 60))
            c["total_seconds"] = sec  # Poori video (intro + clip + outro) itne second ki
            if c["mode"] == "series":
                c["part_seconds"] = sec
            else:  # Intro/outro ke ~7 second nikaal kar clip ki lambai
                c["min_seconds"], c["max_seconds"] = max(8, sec - 13), max(12, sec - 6)
        return cfg

    @staticmethod
    def _shape(cfg: dict) -> str:
        c = cfg["clips"]
        if c["mode"] == "series":
            return f"{c['parts']} parts ki series, har part ~{c['part_seconds']} second"
        return f"{c['per_video']} Short(s), har ek {c['min_seconds']}-{c['max_seconds']} second"

    # ----------------------------------------------------------- commands
    def fail(self, text: str, to: int = None):
        """Ghalti sirf ek dafa batao. Wahi ghalti 15 minute ke andar dobara ho to chhota sa note."""
        now = time.time()
        last_text, last_time = getattr(self, "_last_err", ("", 0))
        if text == last_text and now - last_time < 15 * 60:
            self.reply("❌ Wahi masla abhi bhi hai (upar wala message dekhein).", to)
        else:
            self.reply("❌ " + text, to)
        self._last_err = (text, now)

    def make_from_source(self, key: str = None, topic: str = None, count: int = None, to: int = None,
                         mode: str = None, seconds: int = None):
        cfg = self._cfg(count, mode, seconds)
        if self.progress:
            self.progress.update(f"Video dhoond raha hoon ({self._shape(cfg)}). 5-15 minute lagenge")
        vids, kind, note = sources.candidates(self.cfg, key=key, topic=topic)
        if not vids:
            self.fail("Koi nayi munasib video nahi mili. Doosra channel/topic try karein.", to)
            return
        errors = []
        for url, title in vids[:6]:  # CC search mein kuch videos CC nahi niklti: agli try karo
            say(f"\n🎬 Koshish: {title[:70]}  {url}")
            try:
                permission = f"Public domain: {note}" if kind == "public_domain" else None
                out = self.process(url, cfg, self._args(strict=True),
                                   on_short=self.on_short, permission=permission)
                if out:
                    self._last_err = ("", 0)
                    return
            except BotError as e:
                if str(e) == BOT_CHECK:  # YouTube ne roka: agli video bhi ruk jayegi
                    self.fail(str(e), to)
                    return
                errors.append(str(e).splitlines()[0][:150])
                say(f"  ⚠️  Ye video nahi chali, agli try kar raha hoon: {errors[-1]}")
        reason = f"\nAakhri wajah: {errors[-1]}" if errors else ""
        self.fail(f"{len(vids[:6])} videos try kin, Short nahi ban saka.{reason}", to)

    def make_from_link(self, url: str, allowed: bool, to: int = None, count: int = None,
                       mode: str = None, seconds: int = None):
        cfg = self._cfg(count, mode, seconds)
        if self.progress:
            self.progress.update(f"Shuru ({self._shape(cfg)}). 5-15 minute lagenge")
        permission = "User ne Telegram par ijazat confirm ki" if allowed else None
        try:
            out = self.process(url, cfg,
                               self._args(strict=not allowed),
                               on_short=self.on_short, permission=permission)
            if out:
                self._last_err = ("", 0)
            else:
                self.fail("Short nahi bana.", to)
        except BotError as e:
            hint = ("\nAgar is video ki ijazat aap ke paas hai to likhein:\n/link " + url + " ijazat"
                    if "Creative Commons nahi" in str(e) else "")
            self.fail(f"{str(e)[:600]}{hint}", to)

    def edit(self, msg: dict, field: str = None, value: str = None, request: str = None,
             quiet: bool = False):
        with self.state.lock:
            self._edit(msg, field, value, request, quiet)

    def _edit(self, msg: dict, field: str = None, value: str = None, request: str = None,
              quiet: bool = False):
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
            if not quiet:
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
        if re.fullmatch(r"AIza[0-9A-Za-z_\-]{30,}", text):  # Sirf Gemini key paste ki
            text = "/gemini " + text
        target = (msg.get("reply_to_message") or {}).get("message_id")
        if (target in self.voice_msgs or self._old_voice(msg.get("reply_to_message"))) \
                and not text.startswith("/") and re.fullmatch(r"[\w\- ]{1,30}", text) \
                and len(text.split()) <= 3:  # Awaaz par reply mein sirf naam = us naam se save
            text = "/save " + text
        rv = re.fullmatch(r"/?(?:awaaz|awaz|aawaz|voice|آواز)\s+(.+)", text, re.I)
        if rv and target and self.state.data["msg"].get(str(target)) \
                and rv.group(1).strip().lower() not in ("tez", "fast", "dheemi", "dheema", "slow", "normal"):
            say(f"\n📩 Telegram: {text[:80]}  (video nayi awaaz mein)")
            return self.queue_job("video nayi awaaz mein", self.revoice, to, msg=msg, name=rv.group(1))
        shown = "/gemini ****" if text.lower().startswith("/gemini ") else text[:80]  # Key kabhi screen par nahi
        say(f"\n📩 Telegram: {shown}")
        cmd, _, rest = text.partition(" ")
        cmd = cmd.lower().split("@")[0]
        rest = rest.strip()
        srcs = sources.load(self.cfg["_base"])
        if cmd in ("/start", "/help"):
            self.reply(HELP, to)
        elif cmd == "/status":
            self.status(to)
        elif cmd in ("/awaaz", "/voice") and rest.lower().startswith("save "):
            self.save_voice(rest[5:], msg)
        elif cmd == "/save":
            self.save_voice(rest, msg)
        elif cmd in ("/awaaz", "/voice"):
            self.voice_test(rest, to)
        elif cmd == "/update":
            self.update_now(to)
        elif cmd == "/gemini":
            self.set_gemini(rest, msg)
        elif cmd == "/sources":
            lines = [f"/{k}  → {v.get('name', k)}" for k, v in srcs.items()]
            self.reply("📺 Mehfooz channels:\n" + "\n".join(lines)
                       + "\n\n/cc topic  → Creative Commons search", to)
        elif cmd == "/cc":
            if not rest:
                self.reply("Topic bhi likhein, jaise: /cc business podcast", to)
            else:
                self.queue_job(f"'{rest}' (Creative Commons)", self.make_from_source, to, topic=rest)
        elif cmd == "/link":
            parts = rest.split()
            if not parts or not parts[0].startswith("http"):
                self.reply("Link bhi likhein, jaise: /link https://www.youtube.com/watch?v=...", to)
            else:
                allowed = any(p.lower() in ("ijazat", "permission", "haan") for p in parts[1:])
                self.queue_job("aap ka link", self.make_from_link, to, url=parts[0], allowed=allowed)
        elif cmd in ("/title", "/desc", "/thumb"):
            if not rest:
                self.reply(f"Naya text bhi likhein, jaise: {cmd} ...", to)
            else:
                field = {"/title": "title", "/desc": "description", "/thumb": "thumbnail_text"}[cmd]
                self.edit(msg, field=field, value=rest)
        elif cmd.startswith("/") and cmd[1:] in srcs and (not rest or rest.isdigit()):
            count = max(1, min(int(rest), 5)) if rest.isdigit() else None
            self.queue_job(srcs[cmd[1:]].get("name", cmd[1:]), self.make_from_source, to,
                           key=cmd[1:], count=count)
        else:  # Aam baat (/ ke saath ya baghair): AI samjhe ke kya chahiye
            self.understand(msg, text.lstrip("/").strip(), srcs)

    # ----------------------------------------------------------- khud update
    def busy(self) -> bool:
        return bool(self.current) or not self.jobs.empty()

    def update_now(self, to: int = None, auto: bool = False):
        if not self.updater:
            return self.reply("Update yahan se nahi ho sakta.", to)
        if self.busy():
            self.update_wanted = to or 0
            if not auto:
                self.reply("⏳ Abhi Short ban raha hai. Khatam hote hi update kar doonga.", to)
            return
        self.update_wanted = None
        if not auto:
            self.reply("🔄 Naya version dekh raha hoon...", to)
        if self.restart:
            return
        log = self.updater(quiet=True)
        if log is None:
            if not auto:
                self.reply("⚠️ Update nahi hua (internet?). Purana version chal raha hai.", to)
        elif not log:
            if not auto:
                self.reply("✅ Bot pehle se naya hai.", to)
        else:
            self.reply("🔄 Naya version aa gaya, bot restart ho raha hai...\n" + log[:1500], to)
            self.restart = True

    def _auto_update(self):
        """Har 30 minute GitHub dekho; naya code ho aur bot khaali ho to khud update + restart."""
        last = 0.0
        while not self.restart:
            time.sleep(60)
            if self.restart:
                break
            try:
                if self.update_wanted is not None and not self.busy():
                    self.update_now(self.update_wanted or None)
                elif time.time() - last > 1800:
                    last = time.time()
                    if self.update_available and self.update_available():
                        self.update_now(auto=True)
            except Exception as e:  # Update ki ghalti se bot band na ho
                say(f"⚠️  Khud update check nahi hua: {str(e)[:150]}")

    def set_gemini(self, key: str, msg: dict):
        """/gemini KEY: insaan jaisi awaaz (Gemini) ki key .env mein rakho. File kholni nahi parti."""
        from . import voice
        to = msg["message_id"]
        key = key.strip()
        if not key:
            return self.reply(
                "🎙️ Insaan jaisi awaaz (Gemini, muft) ke liye key chahiye:\n"
                "1. Phone/computer par kholein: https://aistudio.google.com/apikey\n"
                "2. Apne Gmail se login karein\n"
                "3. 'Create API key' dabayein, key copy karein\n"
                "4. Yahin is chat mein paste karke bhej dein (bas key, aur kuch nahi)\n\n"
                "Key wala message main khud mita doonga taake chat mein na rahe.", to)
        if not re.fullmatch(r"[A-Za-z0-9_\-]{20,}", key):
            return self.reply("Ye key sahi nahi lag rahi. Poori key copy karke bhejein: /gemini AAPKI-KEY", to)
        telegram._write_env(self.cfg["_base"] / ".env", "GEMINI_API_KEY", key)
        os.environ["GEMINI_API_KEY"] = key
        try:  # Key chat mein na rahe
            telegram._call("deleteMessage", data={"chat_id": self.chat, "message_id": to})
        except BotError:
            pass
        voice.USED.clear()
        self.reply("✅ Gemini key lag gayi (aap ka message mita diya). Ab awaaz Gemini ki hogi.\n"
                   "Namoone sunne ke liye: /awaaz")

    def voice_test(self, text: str, to: int = None):
        """/awaaz = har awaaz ka namoona. /awaaz 2 = 2 number wali awaaz channel ki awaaz bana do."""
        from . import config as config_mod
        from . import voice
        from .util import run
        word = text.strip().lower()
        if word in ("tez", "fast", "dheemi", "dheema", "slow", "normal"):
            cur = float((self.cfg["dub"].get("styles") or {}).get("narrator", {}).get("speed")
                        or voice.STYLE_SPEED.get("narrator", 1.0))
            new = 1.1 if word == "normal" else cur + (0.08 if word in ("tez", "fast") else -0.08)
            new = round(min(max(new, 0.8), 1.4), 2)
            styles = dict(self.cfg["dub"].get("styles") or {})
            styles["narrator"] = dict(styles.get("narrator") or {}, speed=new)
            self.cfg["dub"]["styles"] = styles
            config_mod.save_local(self.cfg["_base"], {"dub": {"styles": {"narrator": {"speed": new}}}})
            self.reply(f"✅ Kahani wali awaaz ki raftar ab {new}x. Namoona aa raha hai...", to)
            wav = voice.speak("یہ کہانی انیس سو انہتر کی ہے، جب انسان نے پہلی بار چاند پر قدم رکھا۔",
                              self.cfg["paths"]["output"] / "awaaz-raftar", voice.styled(self.cfg, "narrator"))
            mp3 = wav.with_suffix(".mp3")
            run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-b:a", "128k", mp3])
            self._send_voice(mp3, f"Raftar {new}x  (aur tez: /awaaz tez, dheemi: /awaaz dheemi)\n"
                                  "Save karna ho: is par reply karke naam likh dein (jaise ASAD)", self._narrator())
            return
        presets = self.cfg.get("voice_presets") or {}
        if word and not word.isdigit() and len(word.split()) <= 3 and (presets or len(word) < 25):
            return self.use_voice(text, to)  # /awaaz ASAD (ya اسد)
        if text.strip().isdigit():
            n = int(text.strip())
            if not 1 <= n <= voice.NARRATOR_CHOICES:
                return self.reply(f"1 se {voice.NARRATOR_CHOICES} tak number likhein, jaise: /awaaz 2", to)
            label, _, over = voice.samples(self.cfg)[n - 1]
            keep = (self.cfg["dub"].get("styles") or {}).get("narrator", {}).get("speed")
            over = dict(over, speed=keep) if keep else dict(over)
            self._set_narrator(over)
            return self.reply(f"✅ Ab se intro, outro aur kahani wali awaaz: {n}. {label}\n"
                              f"Naam se save karna ho: /save NAAM", to)
        self.reply("🎙️ Awaaz ke namoone bana raha hoon (1-2 minute)...", to)
        line = text or ("یہ کہانی انیس سو انہتر کی ہے، جب انسان نے پہلی بار چاند پر قدم رکھا۔ "
                        "لیکن اس رات کچھ ایسا ہوا جو آج تک کسی کو نہیں بتایا گیا۔")
        folder = self.cfg["paths"]["output"] / "awaaz"
        folder.mkdir(parents=True, exist_ok=True)
        voice.USED.clear()
        sent = 0
        for i, (label, _, over) in enumerate(voice.samples(self.cfg)):
            try:
                wav = voice.speak(line, folder / f"awaaz-{i + 1}", voice.sample_cfg(self.cfg, i))
                mp3 = folder / f"awaaz-{i + 1}.mp3"
                run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-b:a", "128k", mp3])
                tag = "  ← pasand ho to: /awaaz " + str(i + 1) if over is not None else ""
                if over is not None:
                    settings = dict(over)
                    sp = self._narrator().get("speed")
                    if sp and "speed" not in settings:
                        settings["speed"] = sp
                else:
                    settings = {"base_style": voice.samples(self.cfg)[i][1]}
                self._send_voice(mp3, f"{i + 1}. {label}{tag}", settings)
                sent += 1
            except BotError as e:
                say(f"  ⚠️  Namoona {i + 1} nahi bana: {str(e)[:150]}")
        if not sent:
            return self.fail("Koi awaaz nahi bani. Internet check karein.", to)
        saved = ", ".join(sorted(presets)) if presets else ""
        self.reply(voice.report() + "\n\nPasand ki awaaz ka number bhejein, jaise: /awaaz 2\n"
                   "Kisi namoone ko naam se save karna ho: us par REPLY karke bas naam likh dein (jaise ASAD)"
                   + (f"\nSave ki hui awaazein: {saved}  (lagane ke liye: /awaaz NAAM)" if saved else ""), to)

    # ----------------------------------------------------- naam wali awaazein
    def _narrator(self) -> dict:
        return dict((self.cfg["dub"].get("styles") or {}).get("narrator") or {})

    def _old_voice(self, replied: dict):
        """Purane version ka bheja hua awaaz ka message (jis ka record nahi): file ke naam aur
        caption se pehchano. Wapas: settings ya None."""
        from . import voice
        if not replied:
            return None
        doc = replied.get("document") or replied.get("audio") or {}
        fname = (doc.get("file_name") or "").lower()
        if not fname.startswith("awaaz"):
            return None
        if "raftar" in fname:  # Raftar wala namoona = us waqt ki channel awaaz
            return self._narrator()
        m = re.match(r"\s*(\d+)\.", replied.get("caption") or "")
        items = voice.samples(self.cfg)
        if m and 1 <= int(m.group(1)) <= len(items):
            _, st, over = items[int(m.group(1)) - 1]
            if over is None:
                return {"base_style": st}
            out = dict(over)
            sp = self._narrator().get("speed")
            if sp and "speed" not in out:
                out["speed"] = sp
            return out
        return self._narrator()

    def _send_voice(self, mp3, caption: str, settings: dict):
        mid = telegram.send_document(mp3, caption, mime="audio/mpeg")
        self.voice_msgs[mid] = dict(settings)
        with self.state.lock:
            keep = dict(list(self.voice_msgs.items())[-60:])
            self.state.data["voices"] = {str(k): v for k, v in keep.items()}
            self.state.save()
        self.last_voice = dict(settings)

    def _set_narrator(self, settings: dict):
        from . import config as config_mod
        styles = dict(self.cfg["dub"].get("styles") or {})
        styles["narrator"] = dict(settings)
        self.cfg["dub"]["styles"] = styles
        config_mod.set_local(self.cfg["_base"], ["dub", "styles", "narrator"], dict(settings))

    def save_voice(self, name: str, msg: dict):
        """Awaaz ko naam se yaad rakho. Namoone par reply ho to wohi, warna abhi wali awaaz."""
        from . import config as config_mod
        to = msg["message_id"]
        name = re.sub(r"[^\w\- ]", "", name or "").strip().upper()[:30]
        if not name:
            return self.reply("Naam bhi likhein, jaise: /save ASAD", to)
        replied = msg.get("reply_to_message")
        target = (replied or {}).get("message_id")
        old = self._old_voice(replied)
        if target in self.voice_msgs:
            settings, which = self.voice_msgs[target], "Ye awaaz"
        elif old is not None:
            settings, which = old, "Ye awaaz"
        else:
            settings, which = self._narrator(), "Abhi wali awaaz"
        presets = dict(self.cfg.get("voice_presets") or {})
        presets[name] = dict(settings)
        self.cfg["voice_presets"] = presets
        config_mod.set_local(self.cfg["_base"], ["voice_presets", name], dict(settings))
        if target in self.voice_msgs or old is not None:  # Reply wala namoona channel ki awaaz bhi bana do
            self._set_narrator(settings)
        self.reply(f"✅ {which} '{name}' naam se save ho gayi aur ab yahi channel ki awaaz hai.\n"
                   f"Baad mein wapas lagani ho: /awaaz {name}", to)

    def _find_voice(self, name: str):
        """Naam (ya namoone ka number) se awaaz ki settings. Urdu likhawat (اسد) bhi chalti hai.
        Wapas: (NAAM, settings) ya (None, None)."""
        from . import voice
        raw = (name or "").strip()
        presets = self.cfg.get("voice_presets") or {}
        if raw.upper() in presets:
            return raw.upper(), presets[raw.upper()]
        if raw.isdigit() and 1 <= int(raw) <= voice.NARRATOR_CHOICES:
            over = voice.samples(self.cfg)[int(raw) - 1][2]
            return f"awaaz {raw}", dict(over)
        if presets and raw:  # "اسد" / "asad wali" -> ASAD: AI se poochho
            schema = {"type": "object", "properties": {"name": {"type": "string"}},
                      "required": ["name"], "additionalProperties": False}
            try:
                r = planner.ask_claude(
                    self.cfg, "Match the user's words to one of the saved voice names. They may write it "
                    "in Urdu script, Roman Urdu or with extra words. Return the exact saved name, or an "
                    "empty string if none fits.",
                    f"Saved names: {', '.join(presets)}\nUser wrote: {raw}", schema, effort="low")
                key = (r.get("name") or "").strip().upper()
                if key in presets:
                    return key, presets[key]
            except BotError:
                pass
        return None, None

    def _voice_sample(self, settings: dict, caption: str):
        from . import voice
        from .util import run
        c = dict(self.cfg, dub=dict(self.cfg["dub"], styles=dict(self.cfg["dub"].get("styles") or {},
                                                                  narrator=dict(settings))))
        wav = voice.speak("یہ کہانی انیس سو انہتر کی ہے، جب انسان نے پہلی بار چاند پر قدم رکھا۔",
                          self.cfg["paths"]["output"] / "awaaz-namoona", voice.styled(c, "narrator"))
        mp3 = wav.with_suffix(".mp3")
        run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-b:a", "128k", mp3])
        self._send_voice(mp3, caption, settings)

    def use_voice(self, name: str, to: int = None):
        key, settings = self._find_voice(name)
        if not key:
            names = ", ".join(sorted(self.cfg.get("voice_presets") or {})) or "abhi koi nahi"
            return self.reply(f"'{name}' naam ki awaaz save nahi. Save ki hui: {names}", to)
        self._set_narrator(settings)
        self.reply(f"✅ Ab se intro, outro aur kahani wali awaaz: {key}. Namoona aa raha hai...", to)
        try:
            self._voice_sample(settings, f"🎙️ {key} ka namoona\n"
                                         "Kisi video ko is awaaz mein dobara banana ho: us video par "
                                         f"reply karke likhein: awaaz {key}")
        except BotError as e:
            self.reply(f"⚠️ Namoona nahi bana: {str(e)[:200]}", to)

    def revoice(self, msg: dict, name: str, to: int = None):
        """Bani hui video ko nayi awaaz mein dobara banao (video wahi, sirf awaaz nayi)."""
        from . import voice
        reply_to = (msg.get("reply_to_message") or {}).get("message_id")
        skey, info = self.state.target(reply_to)
        if not info:
            return self.reply("Kaunsi video? Video par reply karke likhein: awaaz ASAD", to)
        vkey, settings = self._find_voice(name)
        if not vkey:
            names = ", ".join(sorted(self.cfg.get("voice_presets") or {})) or "abhi koi nahi"
            return self.reply(f"'{name}' naam ki awaaz save nahi. Save ki hui: {names}", to)
        media, cwork = Path(info["media"]), Path(info["cwork"])
        if not media.exists():
            return self.reply("Is video ki purani files computer par nahi milin, dobara nahi ban sakti.", to)
        cfg = copy.deepcopy(self.cfg)
        cfg["dub"]["styles"] = dict(cfg["dub"].get("styles") or {}, narrator=dict(settings))
        if self.progress:
            self.progress.update(f"Nayi awaaz ({vkey}) laga raha hoon")
        clip = info["clip"]
        work = cwork / f"awaaz-{re.sub(r'[^A-Za-z0-9]+', '-', vkey).strip('-').lower() or 'nayi'}"
        work.mkdir(parents=True, exist_ok=True)
        voice.USED.clear()
        voices = {}
        if clip.get("hook_voice", "").strip() and cfg["clips"]["hook"]:
            voices["hook"] = voice.fit(voice.speak(clip["hook_voice"], work / "hook",
                                                   voice.styled(cfg, cfg["voice"]["gender"])), 3.5)
        if clip.get("outro_voice", "").strip() and cfg["clips"]["outro"]:
            og = cfg["voice"].get("outro_gender") or cfg["voice"]["gender"]
            voices["outro"] = voice.fit(voice.speak(clip["outro_voice"], work / "outro",
                                                    voice.styled(cfg, og)), 4.5)
        old = Path(info["video"])
        final = old.with_name(f"{old.stem}_{work.name}.mp4")
        render.render_short({"video": media}, clip, voices, cfg, work, final, info["lang"])
        if self.progress:
            self.progress.hide()
        ids = self.reply(f"🎙️ Ye rahi wahi video, {vkey} ki awaaz mein:")
        ids += telegram.send_short(final, info["title"], info["description"], None)
        note = voice.report()
        if note:
            ids += self.reply(note)
        with self.state.lock:
            for m in ids:
                self.state.data["msg"][str(m)] = skey
            self.state.save()

    def understand(self, msg: dict, text: str, srcs: dict):
        to = msg["message_id"]
        self.reply("🤔 Samajh raha hoon...", to)
        is_reply = bool((msg.get("reply_to_message") or {}).get("message_id"))
        names = {k: v.get("name", k) for k, v in srcs.items()}
        r = planner.route_message(self.cfg, text, names, bool(self.state.data.get("last")),
                                  list(self.chat_log))
        act = r["action"]
        self.chat_log.append(f"User: {text[:300]}")
        if r.get("reply"):
            self.chat_log.append(f"Bot: {r['reply'][:300]}")
        if act == "voice_save" and r.get("topic"):
            return self.save_voice(r["topic"], msg)
        if act == "voice_use" and r.get("topic"):
            target = (msg.get("reply_to_message") or {}).get("message_id")
            if target and self.state.data["msg"].get(str(target)):  # Video par reply: wahi video nayi awaaz mein
                return self.queue_job("video nayi awaaz mein", self.revoice, to, msg=msg, name=r["topic"])
            return self.use_voice(r["topic"], to)
        if is_reply and act in ("unknown", "help", "chat"):
            act = "edit"  # Short par reply = usi ko badalna
        if act == "chat" and r.get("reply"):
            self.reply(r["reply"], to)
            return
        if act != "edit" and r.get("reply"):
            self.reply("🤖 " + r["reply"], to)
        shape = {"count": int(r.get("count") or 0) or None, "seconds": int(r.get("seconds") or 0) or None,
                 "mode": r.get("mode") if r.get("mode") in ("single", "series") else None}
        if act == "source" and r.get("source") in srcs:
            self.queue_job(srcs[r["source"]].get("name", r["source"]), self.make_from_source, to,
                           key=r["source"], **shape)
        elif act == "cc" and r.get("topic"):
            self.queue_job(f"'{r['topic']}' (Creative Commons)", self.make_from_source, to,
                           topic=r["topic"], **shape)
        elif act == "link" and r.get("url", "").startswith("http"):
            self.queue_job("aap ka link", self.make_from_link, to, url=r["url"],
                           allowed=bool(r.get("permission")), **shape)
        elif act == "edit":
            self.edit(msg, request=text, quiet=True)
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
        if self.updater:
            threading.Thread(target=self._auto_update, daemon=True).start()
        while not self.restart:
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
                # Har message alag thread mein: Short ban raha ho tab bhi foran jawab
                threading.Thread(target=self._safe, args=(self.handle, msg.get("message_id"), msg),
                                 daemon=True).start()


def run(cfg: dict, process, updater=None, update_available=None):
    b = TelegramBot(cfg, process, updater, update_available)
    b.run()
    return "restart" if b.restart else None
