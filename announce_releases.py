"""
Daily game release announcement script (runs once, via GitHub Actions).
--------------------------------------------------------------------------
Queries IGDB for today's game releases (Paris timezone), ranks them by a
popularity score, and posts the top N to a Discord channel via a single
REST call (no persistent bot connection needed).
"""

import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = os.environ["ANNOUNCE_CHANNEL_ID"]
TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
TOP_N = int(os.environ.get("TOP_N", "5"))

PARIS_TZ = ZoneInfo("Europe/Paris")
DISCORD_API = "https://discord.com/api/v10"
BLURPLE = 0x5865F2


def get_igdb_token():
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
    return response.json()["access_token"]


def build_cover_url(cover_url):
    if not cover_url:
        return None
    if cover_url.startswith("//"):
        cover_url = "https:" + cover_url
    return cover_url.replace("t_thumb", "t_cover_big")


def get_todays_releases(igdb_token):
    today_str = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    start_dt = datetime.strptime(today_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_ts = int(start_dt.timestamp())
    end_ts = start_ts + 86400

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {igdb_token}",
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


def post_discord_message(payload):
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        f"{DISCORD_API}/channels/{CHANNEL_ID}/messages",
        headers=headers,
        json=payload,
        timeout=15,
    )
    if not response.ok:
        print(f"⚠️ Discord HTTP error {response.status_code}: {response.text}")
        response.raise_for_status()


def main():
    igdb_token = get_igdb_token()
    games = get_todays_releases(igdb_token)

    if not games:
        print("ℹ️ No notable releases today.")
        return

    post_discord_message({
        "content": f"🎮 **Today's Top {len(games)} Game Release{'s' if len(games) > 1 else ''}**"
    })

    for game in games:
        name = game.get("name", "Unknown game")
        summary = game.get("summary", "")
        if summary and len(summary) > 350:
            summary = summary[:347] + "..."
        url = game.get("url", "")
        cover = build_cover_url((game.get("cover") or {}).get("url"))
        platforms = [p.get("name") for p in (game.get("platforms") or []) if p.get("name")]

        embed = {"title": name, "description": summary or "Available today!", "color": BLURPLE}
        if url:
            embed["url"] = url

        fields = []
        if platforms:
            fields.append({"name": "Platforms", "value": ", ".join(platforms), "inline": False})
        if url:
            fields.append({"name": "More info", "value": f"[IGDB page]({url})", "inline": False})
        if fields:
            embed["fields"] = fields
        if cover:
            embed["image"] = {"url": cover}

        post_discord_message({"embeds": [embed]})
        print(f"✅ Announced: {name}")
        time.sleep(1)  # small delay to stay well clear of Discord rate limits


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
