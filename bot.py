"""
Discord Bot - Game Release Announcements (fully automated via IGDB)
---------------------------------------------------------------------
Every day at a fixed time (Paris timezone), queries the IGDB API for
games releasing that day, ranks them by a popularity score, and posts
the top N in a Discord channel.
"""

import os
import time as time_module
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

import requests
import discord
from discord.ext import tasks

# --- Configuration (via environment variables) ---
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["ANNOUNCE_CHANNEL_ID"])
TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
TOP_N = int(os.environ.get("TOP_N", "5"))

PARIS_TZ = ZoneInfo("Europe/Paris")
ANNOUNCE_HOUR = int(os.environ.get("ANNOUNCE_HOUR", "9"))
ANNOUNCE_MINUTE = int(os.environ.get("ANNOUNCE_MINUTE", "0"))
ANNOUNCE_TIME = dtime(hour=ANNOUNCE_HOUR, minute=ANNOUNCE_MINUTE, tzinfo=PARIS_TZ)

intents = discord.Intents.default()
client = discord.Client(intents=intents)

_igdb_token = None
_igdb_token_expiry = 0.0


def get_igdb_token():
    """Fetches (and caches) a Twitch/IGDB access token."""
    global _igdb_token, _igdb_token_expiry
    if _igdb_token and time_module.time() < _igdb_token_expiry:
        return _igdb_token

    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    _igdb_token = data["access_token"]
    # 60s safety margin before actual expiration
    _igdb_token_expiry = time_module.time() + data["expires_in"] - 60
    return _igdb_token


def build_cover_url(cover_url):
    """Turns an IGDB cover URL (thumbnail) into a larger image."""
    if not cover_url:
        return None
    if cover_url.startswith("//"):
        cover_url = "https:" + cover_url
    return cover_url.replace("t_thumb", "t_cover_big")


def get_todays_releases():
    """Queries the IGDB release_dates endpoint (one entry per release, per
    platform/region) to catch today's releases even when the game already
    shipped on another platform earlier. Returns the TOP_N most popular
    (score-based ranking acts as the filter: no category filter, since many
    games don't have that field populated)."""
    token = get_igdb_token()

    today_str = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    start_dt = datetime.strptime(today_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_ts = int(start_dt.timestamp())
    end_ts = start_ts + 86400

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain",
    }
    body = (
        "fields date,game.id,game.name,game.summary,game.url,"
        "game.hypes,game.follows,game.total_rating,game.cover.url,"
        "game.platforms.name;"
        f" where date >= {start_ts} & date < {end_ts};"
        " limit 500;"
    )

    response = requests.post(
        "https://api.igdb.com/v4/release_dates", headers=headers, data=body, timeout=15
    )
    if not response.ok:
        print(f"⚠️ IGDB HTTP error {response.status_code}: {response.text}")
        response.raise_for_status()

    entries = response.json()

    # A game can appear multiple times (one entry per platform/region):
    # keep only one entry per game.
    games_by_id = {}
    for entry in entries:
        game = entry.get("game")
        if not game or "id" not in game:
            continue
        games_by_id[game["id"]] = game

    games = list(games_by_id.values())
    print(f"ℹ️ {len(games)} release(s) found today, before picking the top {TOP_N}")

    for game in games:
        hypes = game.get("hypes") or 0
        follows = game.get("follows") or 0
        rating = game.get("total_rating") or 0
        game["_score"] = hypes * 2 + follows + rating / 10

    games.sort(key=lambda g: g["_score"], reverse=True)
    return games[:TOP_N]


@tasks.loop(time=ANNOUNCE_TIME)
async def check_releases():
    """Runs once a day, exactly at ANNOUNCE_TIME (Paris timezone)."""
    await client.wait_until_ready()

    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("⚠️ Channel not found, check ANNOUNCE_CHANNEL_ID")
        return

    try:
        games = get_todays_releases()
    except Exception as e:
        print(f"⚠️ Error while querying IGDB: {e}")
        return

    if not games:
        print("ℹ️ No notable releases today.")
        return

    await channel.send(f"🎮 **Today's Top {len(games)} Game Release{'s' if len(games) > 1 else ''}**")

    for game in games:
        name = game.get("name", "Unknown game")
        summary = game.get("summary", "")
        if summary and len(summary) > 350:
            summary = summary[:347] + "..."
        url = game.get("url", "")
        cover = build_cover_url((game.get("cover") or {}).get("url"))
        platforms = [p.get("name") for p in (game.get("platforms") or []) if p.get("name")]

        embed = discord.Embed(
            title=name,
            description=summary or "Available today!",
            url=url or None,
            color=discord.Color.blurple(),
        )
        if platforms:
            embed.add_field(name="Platforms", value=", ".join(platforms), inline=False)
        if url:
            embed.add_field(name="More info", value=f"[IGDB page]({url})", inline=False)
        if cover:
            embed.set_image(url=cover)

        await channel.send(embed=embed)
        print(f"✅ Announced: {name}")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print(f"Daily check scheduled at {ANNOUNCE_HOUR:02d}:{ANNOUNCE_MINUTE:02d} (Paris time)")
    if not check_releases.is_running():
        check_releases.start()


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
