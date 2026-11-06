from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import pathlib
import threading

import aiohttp
import discord
from aiohttp import web
from discord import app_commands, ui
from discord.ext import tasks

CHANNEL_ID = 1568033554993250405
CHECK_EVERY_MINUTES = 5
DOWNLOAD_URL = "https://www.roblox.com/download"
VERSION_URL = "https://clientsettings.roblox.com/v2/client-version/WindowsPlayer"
STATE_FILE = pathlib.Path(__file__).with_name("state.json")
BANNER_FILE = pathlib.Path(__file__).with_name("assets") / "banner.png"

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


def build_announcement(version: str, detected_at: dt.datetime) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)

    details = (
        "**Platform:** Windows\n"
        f"**Roblox Version:** `{version}`\n"
        f"**Detected:** <t:{int(detected_at.timestamp())}:F>"
    )

    children = []
    if BANNER_FILE.exists():
        children.append(
            ui.MediaGallery(
                discord.MediaGalleryItem(media="attachment://banner.png")
            )
        )
    children += [
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        ui.TextDisplay(
            "## Live update detected!\n"
            "A new ROBLOX LIVE version is out. Recall has been auto-updated to match."
        ),
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        ui.TextDisplay(details),
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        ui.ActionRow(
            ui.Button(
                label="Download",
                style=discord.ButtonStyle.link,
                url=DOWNLOAD_URL,
            )
        ),
    ]
    view.add_item(ui.Container(*children))
    return view


def banner_attachments() -> list[discord.File]:
    if BANNER_FILE.exists():
        return [discord.File(BANNER_FILE, filename="banner.png")]
    return []


async def fetch_card_message() -> discord.Message | None:
    card_id = load_state().get("card_message_id")
    if not card_id:
        return None
    try:
        channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
        return await channel.fetch_message(int(card_id))
    except (discord.NotFound, discord.Forbidden, ValueError):
        return None


async def refresh_card(version: str, detected_at: dt.datetime) -> str:
    view = build_announcement(version, detected_at)
    upload = banner_attachments()

    message = await fetch_card_message()
    if message is not None:
        try:
            await message.edit(view=view, attachments=upload)
            return "edited"
        except discord.HTTPException:
            pass
    else:
        state = load_state()
        state.pop("card_message_id", None)
        save_state(state)

    channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
    message = await channel.send(view=view, files=upload)
    state = load_state()
    state["card_message_id"] = message.id
    state["card_channel_id"] = CHANNEL_ID
    save_state(state)
    return "posted"


async def ensure_card() -> None:
    state = load_state()
    version = state.get("known_version")
    if not version:
        try:
            version = await fetch_roblox_version()
        except Exception:
            return
        save_state({**state, "known_version": version, "first_seen": now().isoformat()})
    try:
        if await fetch_card_message() is None:
            await refresh_card(version, now())
    except Exception:
        pass


async def perform_check() -> str:
    state = load_state()
    known_version = state.get("known_version")

    try:
        current_version = await fetch_roblox_version()
    except Exception:
        return (f"Couldn't reach Roblox's version API — will retry at the next check "
                f"(every {CHECK_EVERY_MINUTES} minutes).")

    if not known_version:
        save_state({**state, "known_version": current_version, "first_seen": now().isoformat()})
        try:
            if await fetch_card_message() is None:
                await refresh_card(current_version, now())
        except Exception:
            pass
        return f"First check done — memorized {current_version}."

    if current_version == known_version:
        return f"Checked Roblox — still {current_version}, nothing new."

    detected_at = now()
    try:
        action = await refresh_card(current_version, detected_at)
    except Exception:
        return ("A new version exists, but updating the card failed — I'll retry on "
                "the next check. (Check my channel permissions!)")

    state = load_state()
    state["known_version"] = current_version
    state["last_announced"] = detected_at.isoformat()
    save_state(state)
    return f"New Roblox version! {current_version} — live card {action}."


@tasks.loop(minutes=CHECK_EVERY_MINUTES)
async def roblox_update_check() -> None:
    await perform_check()


recall_group = app_commands.Group(
    name="recall",
    description="Roblox update card commands",
)


@recall_group.command(
    name="status",
    description="See which Roblox version Recall is tracking",
)
async def recall_status_command(interaction: discord.Interaction) -> None:
    state = load_state()
    lines = [
        f"**Tracking:** {state.get('known_version', 'not seen yet')}",
        f"Checks Roblox every **{CHECK_EVERY_MINUTES} min**",
    ]
    if state.get("last_announced"):
        stamp = int(dt.datetime.fromisoformat(state["last_announced"]).timestamp())
        lines.append(f"Last card refresh: <t:{stamp}:F>")
    lines.append("Live card: set up ✓" if state.get("card_message_id")
                 else "Live card: not posted yet")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@recall_group.command(
    name="check",
    description="Check Roblox right now and refresh the live card",
)
async def recall_check_command(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True, ephemeral=True)
    summary = await perform_check()
    await interaction.followup.send(summary, ephemeral=True)


class RecallClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._guilds_synced: set[int] = set()
        self._startup_done = False

    async def setup_hook(self) -> None:
        self.tree.add_command(recall_group)
        await self.tree.sync()

    async def _sync_guild(self, guild: discord.Guild) -> None:
        if guild.id in self._guilds_synced:
            return
        try:
            self.tree.copy_global_to(guild=discord.Object(id=guild.id))
            await self.tree.sync(guild=discord.Object(id=guild.id))
            self._guilds_synced.add(guild.id)
        except discord.HTTPException:
            pass

    async def on_ready(self) -> None:
        for guild in self.guilds:
            await self._sync_guild(guild)

        if not roblox_update_check.is_running():
            roblox_update_check.start()

        if not self._startup_done:
            self._startup_done = True
            await ensure_card()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._sync_guild(guild)


bot = RecallClient()


@roblox_update_check.before_loop
async def wait_for_bot_ready() -> None:
    await bot.wait_until_ready()


def _run_website() -> None:
    async def index(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "bot": "Recall is awake!"})

    app = web.Application()
    app.router.add_get("/", index)
    asyncio.set_event_loop(asyncio.new_event_loop())
    web.run_app(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        print=None,
    )


def main() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Missing the DISCORD_TOKEN environment variable.")
    if os.environ.get("PORT"):
        threading.Thread(target=_run_website, name="keep-alive", daemon=True).start()
    bot.run(token)


if __name__ == "__main__":
    main()
