"""Discord slash commands (read-only): /positions, /today.

Webhook sirf bhejta hai, sun nahi sakta. Command ke liye ek Discord *bot* chahiye:
  .env mein:  DISCORD_BOT_TOKEN=...   (aur optional: DISCORD_GUILD_ID=server id, DISCORD_ALLOWED_USER_ID=aapki id,
                                       DISCORD_PROXY=...)
  pip install discord.py
Token / package na ho to bot normal chalta rahega, bas command band rahegi (ek line message aata hai).
Commands sirf padhte hain (state files): koi trade band/khol nahi sakti."""
from __future__ import annotations

import glob
import os
import threading

from gridbot.notify import load_dotenv

from . import dashboard, messages


def state_files(folder: str = ".") -> list[tuple[str, str, str, str]]:
    """(label, state, trades, equity) - folder mein jitne bots ki state file hai (test/commands files chhod kar)."""
    out = []
    for p in sorted(glob.glob(os.path.join(folder, "scalp_state*.json"))):
        base = os.path.basename(p)
        if base.endswith("_commands.json") or base.startswith("scalp_test_"):
            continue
        suffix = base[len("scalp_state"):-len(".json")].strip("_")
        label = suffix.upper() if suffix else "MAIN"
        trades = os.path.join(folder, f"scalp_trades{'_' + suffix if suffix else ''}.csv")
        out.append((label, p, trades, p.replace(".json", "_equity.csv")))
    return out


def snapshot(folder: str = ".", which: str = "") -> list[tuple[str, dict]]:
    res = []
    for label, sp, tp, ep in state_files(folder):
        if which and which.lower() != label.lower():
            continue
        res.append((label, dashboard.build_state(sp, tp, ep)))
    return res


def positions_reply(folder: str = ".", which: str = "") -> str:
    snap = snapshot(folder, which)
    return messages.positions_text(snap) if snap else "Koi bot state file nahi mili (bot chal raha hai?)"


def start(folder: str = ".", env_file: str = ".env") -> threading.Thread | None:
    f = load_dotenv(env_file)
    token = f.get("DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("Discord commands: DISCORD_BOT_TOKEN .env mein nahi hai -> /positions band (alerts normal chalenge)")
        return None
    try:
        import discord
        from discord import app_commands
    except ImportError:
        print("Discord commands: 'pip install discord.py' chalao, phir bot restart karo (abhi /positions band)")
        return None
    guild = f.get("DISCORD_GUILD_ID") or os.environ.get("DISCORD_GUILD_ID")
    allowed = f.get("DISCORD_ALLOWED_USER_ID") or os.environ.get("DISCORD_ALLOWED_USER_ID")
    proxy = (f.get("DISCORD_PROXY") or os.environ.get("DISCORD_PROXY") or "").split(",")[0].strip() or None

    client = discord.Client(intents=discord.Intents.none(), proxy=proxy)
    tree = app_commands.CommandTree(client)
    target = discord.Object(id=int(guild)) if guild else None

    async def guard(inter) -> bool:
        if allowed and str(inter.user.id) != allowed.strip():
            await inter.response.send_message("Aap is command ke liye authorised nahi hain.", ephemeral=True)
            return False
        return True

    @tree.command(name="positions", description="Open trades ki current position (dashboard jaisa)", guild=target)
    @app_commands.describe(bot="Kaun sa bot (khali = sab): scalp1h, freq, big, main")
    async def positions(inter, bot: str = ""):
        if await guard(inter):
            await inter.response.send_message(positions_reply(folder, bot.strip()), ephemeral=True)

    @tree.command(name="today", description="Aaj ka P&L aur equity", guild=target)
    async def today(inter):
        if await guard(inter):
            lines = []
            for label, st in snapshot(folder):
                if st.get("status") == "no_state":
                    continue
                t = st["today"]
                lines.append(f"**{label}**: aaj {t['n']} trades (won {t['wins']}) · net {t['net']:+,.2f} · fees {t['fees']:.2f} · "
                             f"equity ${st['equity']:,.2f} · open {len(st['positions'])}")
            await inter.response.send_message("\n".join(lines) or "Abhi data nahi", ephemeral=True)

    @client.event
    async def on_ready():
        await tree.sync(guild=target)
        print(f"Discord commands ready: /positions, /today ({client.user})")

    def run():
        try:
            client.run(token, log_handler=None)
        except Exception as e:  # noqa: BLE001
            print(f"Discord commands band: {type(e).__name__} (bot normal chalta rahega)")

    th = threading.Thread(target=run, daemon=True, name="discord-cmd")
    th.start()
    return th
