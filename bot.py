"""
Bot Discord - Annonces de sorties de jeux vidéo (100% automatique via IGDB)
----------------------------------------------------------------------------
Chaque jour à heure fixe (heure de Paris), interroge l'API IGDB pour
récupérer les jeux sortant ce jour-là, calcule un score de popularité,
et poste les N meilleurs dans un channel Discord.
"""

import os
import time as time_module
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

import requests
import discord
from discord.ext import tasks

# --- Configuration (via variables d'environnement) ---
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["ANNOUNCE_CHANNEL_ID"])
TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
TOP_N = int(os.environ.get("TOP_N", "5"))

PARIS_TZ = ZoneInfo("Europe/Paris")
ANNOUNCE_HOUR = int(os.environ.get("ANNOUNCE_HOUR", "9"))
ANNOUNCE_MINUTE = int(os.environ.get("ANNOUNCE_MINUTE", "0"))
ANNOUNCE_TIME = dtime(hour=ANNOUNCE_HOUR, minute=ANNOUNCE_MINUTE, tzinfo=PARIS_TZ)

# Catégories IGDB à inclure : 0=jeu principal, 4=extension autonome, 8=remake, 9=remaster
# (on exclut DLC, ports, saisons... qui gonflent artificiellement le nombre de "sorties")
INCLUDED_CATEGORIES = "(0,4,8,9)"

intents = discord.Intents.default()
client = discord.Client(intents=intents)

_igdb_token = None
_igdb_token_expiry = 0.0


def get_igdb_token():
    """Récupère (et met en cache) un token d'accès Twitch/IGDB."""
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
    # On retire 60s de marge de sécurité avant expiration réelle
    _igdb_token_expiry = time_module.time() + data["expires_in"] - 60
    return _igdb_token


def build_cover_url(cover_url):
    """Transforme l'URL de cover IGDB (miniature) en image grand format."""
    if not cover_url:
        return None
    if cover_url.startswith("//"):
        cover_url = "https:" + cover_url
    return cover_url.replace("t_thumb", "t_cover_big")


def get_todays_releases():
    """Interroge l'endpoint release_dates d'IGDB (une entrée par sortie, par
    plateforme/région), pour capter les sorties du jour même quand le jeu est
    déjà sorti sur une autre plateforme auparavant. Renvoie les TOP_N les
    plus populaires."""
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
        "game.hypes,game.follows,game.total_rating,game.cover.url;"
        f" where date >= {start_ts} & date < {end_ts}"
        f" & game.category = {INCLUDED_CATEGORIES};"
        " limit 500;"
    )

    response = requests.post(
        "https://api.igdb.com/v4/release_dates", headers=headers, data=body, timeout=15
    )
    response.raise_for_status()
    entries = response.json()

    # Un même jeu peut apparaître plusieurs fois (une entrée par plateforme/région) :
    # on ne garde qu'une entrée par jeu.
    games_by_id = {}
    for entry in entries:
        game = entry.get("game")
        if not game or "id" not in game:
            continue
        games_by_id[game["id"]] = game

    games = list(games_by_id.values())
    for game in games:
        hypes = game.get("hypes") or 0
        follows = game.get("follows") or 0
        rating = game.get("total_rating") or 0
        game["_score"] = hypes * 2 + follows + rating / 10

    games.sort(key=lambda g: g["_score"], reverse=True)
    return games[:TOP_N]


@tasks.loop(time=ANNOUNCE_TIME)
async def check_releases():
    """S'exécute une fois par jour, pile à ANNOUNCE_TIME (heure de Paris)."""
    await client.wait_until_ready()

    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("⚠️ Channel introuvable, vérifie ANNOUNCE_CHANNEL_ID")
        return

    try:
        games = get_todays_releases()
    except Exception as e:
        print(f"⚠️ Erreur lors de la requête IGDB : {e}")
        return

    if not games:
        print("ℹ️ Aucune sortie notable aujourd'hui.")
        return

    for game in games:
        name = game.get("name", "Jeu inconnu")
        summary = game.get("summary", "")
        if summary and len(summary) > 300:
            summary = summary[:297] + "..."
        url = game.get("url", "")
        cover = build_cover_url((game.get("cover") or {}).get("url"))

        embed = discord.Embed(
            title=f"🎮 Sortie du jour : {name}",
            description=summary or "Disponible dès aujourd'hui !",
            url=url or None,
            color=discord.Color.blurple(),
        )
        if cover:
            embed.set_image(url=cover)
        if url:
            embed.add_field(name="Plus d'infos", value=f"[Fiche IGDB]({url})", inline=False)

        await channel.send(embed=embed)
        print(f"✅ Annonce postée : {name}")


@client.event
async def on_ready():
    print(f"Connecté en tant que {client.user}")
    print(f"Vérification programmée chaque jour à {ANNOUNCE_HOUR:02d}:{ANNOUNCE_MINUTE:02d} (heure de Paris)")
    if not check_releases.is_running():
        check_releases.start()


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
