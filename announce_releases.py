"""
Daily game release announcement script (runs once, via GitHub Actions).
--------------------------------------------------------------------------
Queries IGDB for today's game releases (Paris timezone), ranks them by a
popularity score, builds a single cover-art grid image, and posts ONE
compact message (one embed, one attached grid image, one field per game)
to a Discord channel.
"""

import io
import json
import os
import sys
from datetime import datetime, timezone
from math import ceil
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = os.environ["ANNOUNCE_CHANNEL_ID"]
TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
TOP_N = int(os.environ.get("TOP_N", "5"))
ANNOUNCE_ROLE_ID = os.environ.get("ANNOUNCE_ROLE_ID", "")

PARIS_TZ = ZoneInfo("Europe/Paris")
DISCORD_API = "https://discord.com/api/v10"
BLURPLE = 0x5865F2

# --- Grid image settings ---
CELL_WIDTH = 264
CELL_HEIGHT = 352
CELL_PADDING = 12
GRID_COLUMNS = 5  # wraps to a new row automatically beyond 5 games
GRID_BG_COLOR = (43, 45, 49)  # close to Discord's dark theme background
PLACEHOLDER_COLOR = (79, 84, 92)


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


def fetch_cover_image(cover_url):
    """Downloads a cover image and returns it as a PIL Image, or None on failure."""
    if not cover_url:
        return None
    try:
        response = requests.get(cover_url, timeout=15)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception as e:
        print(f"⚠️ Could not download cover ({cover_url}): {e}")
        return None


def build_grid_image(games):
    """Builds a single grid image from each game's cover, numbered to match
    the embed fields below it. Returns PNG bytes."""
    count = len(games)
    columns = min(count, GRID_COLUMNS)
    rows = ceil(count / columns)

    grid_width = columns * CELL_WIDTH + (columns + 1) * CELL_PADDING
    grid_height = rows * CELL_HEIGHT + (rows + 1) * CELL_PADDING

    grid = Image.new("RGB", (grid_width, grid_height), GRID_BG_COLOR)
    draw = ImageDraw.Draw(grid)
    font = ImageFont.load_default(size=28)

    for index, game in enumerate(games):
        col = index % columns
        row = index // columns
        x = CELL_PADDING + col * (CELL_WIDTH + CELL_PADDING)
        y = CELL_PADDING + row * (CELL_HEIGHT + CELL_PADDING)

        cover_url = build_cover_url((game.get("cover") or {}).get("url"))
        cover_img = fetch_cover_image(cover_url)

        if cover_img:
            cover_img = cover_img.resize((CELL_WIDTH, CELL_HEIGHT))
        else:
            cover_img = Image.new("RGB", (CELL_WIDTH, CELL_HEIGHT), PLACEHOLDER_COLOR)

        grid.paste(cover_img, (x, y))

        # Number badge in the top-left corner, to match the embed field below
        badge_text = str(index + 1)
        draw.rectangle([x, y, x + 34, y + 34], fill=(0, 0, 0))
        draw.text((x + 10, y + 5), badge_text, fill=(255, 255, 255), font=font)

    buffer = io.BytesIO()
    grid.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


def post_discord_message(payload, image_bytes=None, image_filename="grid.png"):
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}

    if image_bytes:
        files = {"file": (image_filename, image_bytes, "image/png")}
        data = {"payload_json": json.dumps(payload)}
        response = requests.post(
            f"{DISCORD_API}/channels/{CHANNEL_ID}/messages",
            headers=headers,
            data=data,
            files=files,
            timeout=30,
        )
    else:
        headers["Content-Type"] = "application/json"
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

    grid_bytes = build_grid_image(games)

    fields = []
    for index, game in enumerate(games, start=1):
        name = game.get("name", "Unknown game")
        summary = game.get("summary", "")
        if summary and len(summary) > 180:
            summary = summary[:177] + "..."
        url = game.get("url", "")
        platforms = [p.get("name") for p in (game.get("platforms") or []) if p.get("name")]

        value_lines = []
        if summary:
            value_lines.append(summary)
        if platforms:
            value_lines.append(f"**Platforms:** {', '.join(platforms)}")
        if url:
            value_lines.append(f"[IGDB page]({url})")

        fields.append({
            "name": f"{index}. {name}",
            "value": "\n".join(value_lines) or "No description available.",
            "inline": False,
        })

    mention = f"<@&{ANNOUNCE_ROLE_ID}> " if ANNOUNCE_ROLE_ID else ""
    embed = {
        "title": f"🎮 Today's Top {len(games)} Game Release{'s' if len(games) > 1 else ''}",
        "color": BLURPLE,
        "image": {"url": "attachment://grid.png"},
        "fields": fields,
    }

    payload = {
        "content": mention or None,
        "embeds": [embed],
        "allowed_mentions": {"roles": [ANNOUNCE_ROLE_ID]} if ANNOUNCE_ROLE_ID else {"parse": []},
    }

    post_discord_message(payload, image_bytes=grid_bytes)
    print(f"✅ Announced {len(games)} game(s) in a single message")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
