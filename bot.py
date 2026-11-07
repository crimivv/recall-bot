from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import pathlib
import re
import threading
import time

import aiohttp
import discord
from aiohttp import web
from discord import ui
from discord.ext import tasks
from urllib.parse import urlencode

CHANNEL_ID = 1568033554993250405
CHECK_EVERY_MINUTES = 1
DOWNLOAD_PREFIX = "https://rdd.whatexpsare.online"
VERSION_URL = "https://clientsettings.roblox.com/v2/client-version/WindowsPlayer"
STATE_FILE = pathlib.Path(__file__).with_name("state.json")

REQUEST_HEADERS = {
    "User-Agent": "Recall-Discord-Bot/1.0",
    "Accept": "application/json",
}

intents = discord.Intents.default()


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def pick_version(data: dict) -> str:
    for key in ("clientVersionUpload", "version"):
        value = data.get(key)
        if value and str(value).startswith("version-"):
            return str(value)
    return str(data.get("version") or "unknown")


async def fetch_roblox_version() -> str:
    async with aiohttp.ClientSession(headers=REQUEST_HEADERS) as session:
        async with session.get(
            VERSION_URL, timeout=aiohttp.ClientTimeout(total=20)
        ) as response:
            response.raise_for_status()
            data = await response.json()
    return pick_version(data)


def download_link(version: str) -> str:
    params = urlencode({"channel": "LIVE", "binaryType": "WindowsPlayer",
                        "version": version})
    return f"{DOWNLOAD_PREFIX}?{params}"


def build_announcement(version: str, last_check: dt.datetime) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)

    details = (
        "**Platform:** Windows\n"
        f"**Roblox Version:** `{version}`\n"
        f"-# Last checked: <t:{int(last_check.timestamp())}:R>"
    )

    children = [
        ui.TextDisplay("## Current Supported Roblox Version"),
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        ui.TextDisplay(details),
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        ui.ActionRow(
            ui.Button(
                label="Download",
                style=discord.ButtonStyle.link,
                url=download_link(version),
            )
        ),
    ]
    view.add_item(ui.Container(*children))
    return view


def describe(error: Exception) -> str:
    if isinstance(error, discord.Forbidden):
        return (f"Recall is missing channel permissions — give its role View Channel and "
                f"Send Messages in channel {CHANNEL_ID} (the '📦｜roblox-updates' channel)")
    if isinstance(error, discord.NotFound):
        return (f"channel {CHANNEL_ID} (the '📦｜roblox-updates' channel) wasn't found — "
                f"check that Recall is in that server")
    message = str(error)
    return message or error.__class__.__name__


async def fetch_card_message() -> discord.Message | None:
    card_id = load_state().get("card_message_id")
    if not card_id:
        return None
    try:
        channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
        return await channel.fetch_message(int(card_id))
    except (discord.NotFound, discord.Forbidden, ValueError):
        return None


async def refresh_card(version: str, last_check: dt.datetime) -> str:
    view = build_announcement(version, last_check)

    message = await fetch_card_message()
    if message is not None:
        try:
            await message.edit(view=view, attachments=[])
            return "edited"
        except discord.HTTPException:
            state = load_state()
            state.pop("card_message_id", None)
            save_state(state)

    channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
    message = await channel.send(view=view)
    state = load_state()
    state["card_message_id"] = message.id
    state["card_channel_id"] = CHANNEL_ID
    save_state(state)
    return "posted"


def _component_text(component) -> str:
    parts = []
    if isinstance(component, dict):
        parts.append(str(component.get("content") or ""))
        parts.append(str(component.get("label") or ""))
        parts.append(str(component.get("url") or ""))
        children = component.get("components") or component.get("items") or []
    else:
        parts.append(str(getattr(component, "content", "") or ""))
        parts.append(str(getattr(component, "label", "") or ""))
        parts.append(str(getattr(component, "url", "") or ""))
        children = (getattr(component, "children", None)
                    or getattr(component, "items", None)
                    or [])
    for child in children:
        parts.append(_component_text(child))
    return " ".join(parts)


def _is_recall_card(message: discord.Message) -> bool:
    text = " ".join(_component_text(component)
                    for component in (message.components or [])).lower()
    return "whatexpsare.online" in text or "roblox.com/download" in text


def _card_facts(message: discord.Message) -> dict:
    text = " ".join(_component_text(component)
                    for component in (message.components or []))
    version_match = re.search(r"`(version-[0-9a-zA-Z]+)`", text)
    check_match = (re.search(r"<t:(\d+):R>", text)
                   or re.search(r"<t:(\d+):[a-zA-Z]>", text))
    return {
        "version": version_match.group(1) if version_match else None,
        "check": int(check_match.group(1)) if check_match else None,
    }


async def settle_card() -> None:
    state = load_state()
    keep_id = state.get("card_message_id")
    try:
        channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
    except Exception:
        return
    try:
        history = [message async for message in channel.history(limit=100)]
    except discord.HTTPException:
        return
    recall_cards = [message for message in history
                    if message.author == bot.user and _is_recall_card(message)]
    anchor = None
    if keep_id:
        anchor = next((message for message in recall_cards
                       if message.id == keep_id), None)
    if anchor is None and recall_cards:
        anchor = recall_cards[0]
    if anchor is None:
        return
    for message in recall_cards:
        if message.id == anchor.id:
            continue
        try:
            await message.delete()
        except discord.HTTPException:
            pass
    if anchor.id == keep_id:
        return
    facts = _card_facts(anchor)
    check = (dt.datetime.fromtimestamp(facts["check"], dt.timezone.utc)
             if facts["check"] is not None else None)
    state = load_state()
    if facts["version"] and not state.get("known_version"):
        state["known_version"] = facts["version"]
    if check:
        state.setdefault("last_check", check.isoformat())
    state["card_message_id"] = anchor.id
    state["card_channel_id"] = CHANNEL_ID
    save_state(state)


async def ensure_card() -> None:
    try:
        await settle_card()
    except Exception:
        pass
    state = load_state()
    version = state.get("known_version")
    if not version:
        try:
            version = await fetch_roblox_version()
        except Exception:
            print("[Recall] Roblox's version API isn't answering at startup — "
                  "the card appears at the next check")
            return
        save_state({**state, "known_version": version})
        state = load_state()
    try:
        if await fetch_card_message() is None:
            await refresh_card(version, now())
    except Exception as error:
        print(f"[Recall] The card could not be posted: {describe(error)} "
              "— retrying at the next check")


async def perform_check() -> None:
    state = load_state()
    known_version = state.get("known_version")

    try:
        current_version = await fetch_roblox_version()
    except Exception:
        print("[Recall] Couldn't reach Roblox's version API — will retry at the next check")
        return

    if not known_version:
        check_time = now()
        save_state({**state, "known_version": current_version})
        try:
            if await fetch_card_message() is None:
                await refresh_card(current_version, check_time)
        except Exception as error:
            print(f"[Recall] The card could not be posted: {describe(error)} "
                  "— retrying at the next check")
            return
        state = load_state()
        state["last_check"] = check_time.isoformat()
        save_state(state)
        return

    if current_version == known_version:
        check_time = now()
        if not state.get("card_message_id"):
            try:
                await refresh_card(current_version, check_time)
            except Exception as error:
                print(f"[Recall] The card is missing but couldn't be re-posted: {describe(error)}")
                return
            state = load_state()
            state["last_check"] = check_time.isoformat()
            save_state(state)
            return
        try:
            await refresh_card(current_version, check_time)
        except Exception as error:
            print(f"[Recall] The card's last-check stamp couldn't be updated: {describe(error)}")
            return
        state = load_state()
        state["last_check"] = check_time.isoformat()
        save_state(state)
        return

    check_time = now()
    try:
        await refresh_card(current_version, check_time)
    except Exception as error:
        print(f"[Recall] Card update failed for the new version: {describe(error)}")
        return

    state = load_state()
    state["known_version"] = current_version
    state["last_check"] = check_time.isoformat()
    save_state(state)


@tasks.loop(minutes=CHECK_EVERY_MINUTES)
async def roblox_update_check() -> None:
    await perform_check()


class RecallClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)
        self._commands_cleared: set[int] = set()
        self._startup_done = False

    async def setup_hook(self) -> None:
        await self.tree.sync()

    async def _clear_guild_commands(self, guild: discord.Guild) -> None:
        if guild.id in self._commands_cleared:
            return
        try:
            await self.tree.sync(guild=discord.Object(id=guild.id))
            self._commands_cleared.add(guild.id)
        except discord.HTTPException:
            pass

    async def on_ready(self) -> None:
        for guild in self.guilds:
            await self._clear_guild_commands(guild)

        if not self._startup_done:
            self._startup_done = True
            await ensure_card()

        if not roblox_update_check.is_running():
            roblox_update_check.start()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._clear_guild_commands(guild)


bot = RecallClient()


@roblox_update_check.before_loop
async def wait_for_bot_ready() -> None:
    await bot.wait_until_ready()


def _run_website() -> None:
    async def index(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "bot": "Recall is awake!"})

    async def serve() -> None:
        app = web.Application()
        app.router.add_get("/", index)
        runner = web.AppRunner(app, handle_signals=False)
        await runner.setup()
        await web.TCPSite(
            runner,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "8080")),
        ).start()
        await asyncio.Event().wait()

    while True:
        try:
            asyncio.run(serve())
        except Exception:
            time.sleep(3)


def main() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Missing the DISCORD_TOKEN environment variable.")
    if os.environ.get("PORT"):
        threading.Thread(target=_run_website, name="keep-alive", daemon=True).start()
    bot.run(token)


if __name__ == "__main__":
    main()
