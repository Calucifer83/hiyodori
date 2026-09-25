"""
Bot Discord - Annonces de sorties de jeux vidéo
------------------------------------------------
Lit une Google Sheet publiée en CSV (aucune authentification requise)
et poste un message dans un channel Discord le jour de la sortie.
"""

import os
import csv
import io
from datetime import datetime, timezone

import requests
import discord
from discord.ext import tasks

# --- Configuration (via variables d'environnement) ---
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["ANNOUNCE_CHANNEL_ID"])
SHEET_CSV_URL = os.environ["SHEET_CSV_URL"]
CHECK_INTERVAL_MINUTES = int(os.environ.get("CHECK_INTERVAL_MINUTES", "30"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# État en mémoire : évite de reposter la même annonce plusieurs fois par jour
_posted_keys = set()
_last_reset_date = None


def get_sheet_rows():
    """Récupère et parse le CSV publié depuis Google Sheets."""
    response = requests.get(SHEET_CSV_URL, timeout=15)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    return list(reader)


def reset_daily_state_if_needed():
    global _last_reset_date, _posted_keys
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _last_reset_date:
        _posted_keys = set()
        _last_reset_date = today


@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_releases():
    await client.wait_until_ready()
    reset_daily_state_if_needed()

    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("⚠️ Channel introuvable, vérifie ANNOUNCE_CHANNEL_ID")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        rows = get_sheet_rows()
    except Exception as e:
        print(f"⚠️ Erreur lecture du CSV : {e}")
        return

    for row in rows:
        date = str(row.get("Date", "")).strip()
        game = str(row.get("Jeu", "")).strip()
        link = str(row.get("Lien", "")).strip()
        key = f"{date}|{game}"

        if date == today and game and key not in _posted_keys:
            embed = discord.Embed(
                title=f"🎮 Sortie du jour : {game}",
                description=f"[Plus d'infos]({link})" if link else "Disponible dès aujourd'hui !",
                color=discord.Color.blurple(),
            )
            await channel.send(embed=embed)
            _posted_keys.add(key)
            print(f"✅ Annonce postée : {game}")


@client.event
async def on_ready():
    print(f"Connecté en tant que {client.user}")
    if not check_releases.is_running():
        check_releases.start()


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
