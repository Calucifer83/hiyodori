# Bot Discord — Annonces de sorties de jeux

Ce bot lit une Google Sheet (publiée en CSV, sans authentification) et poste une annonce dans un channel Discord le jour de la sortie d'un jeu.

## 1. Créer le bot Discord

1. Va sur https://discord.com/developers/applications → **New Application**
2. Onglet **Bot** → **Reset Token** → copie le token (ne le partage jamais publiquement)
3. Toujours dans l'onglet Bot, laisse les intents par défaut (aucun intent privilégié n'est nécessaire ici)
4. Onglet **OAuth2 > URL Generator** :
   - Scopes : `bot`
   - Permissions : `Send Messages`, `Embed Links`
   - Copie l'URL générée en bas, ouvre-la dans ton navigateur, et invite le bot sur ton serveur

## 2. Créer la Google Sheet

1. Crée une nouvelle feuille Google Sheets avec exactement ces en-têtes en ligne 1 :

   | Date       | Jeu              | Lien                          |
   |------------|------------------|-------------------------------|
   | 2026-10-03 | Nom du jeu       | https://www.igdb.com/games/... |

   Le format de date doit être `YYYY-MM-DD` (ex: `2026-10-03`).

2. **Fichier** > **Partager** > **Publier sur le Web**
3. Sélectionne l'onglet concerné, format **Valeurs séparées par des virgules (.csv)**, puis **Publier**
4. Copie l'URL générée (ressemble à `https://docs.google.com/spreadsheets/d/e/XXXX/pub?output=csv`) — c'est ta variable `SHEET_CSV_URL`

⚠️ Cette URL est accessible à quiconque la possède (mais pas indexée ni modifiable), donc ne mets rien de sensible dans cette sheet.

## 3. Configurer le projet

1. Copie `.env.example` en `.env` et remplis les valeurs (token, ID de channel, URL du CSV)
2. Installe les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Teste en local :
   ```bash
   python bot.py
   ```

## 4. Héberger le bot 24/7 (Railway)

1. Crée un repo GitHub avec ces fichiers (⚠️ n'y mets JAMAIS ton `.env` — ajoute-le à un `.gitignore`)
2. Va sur https://railway.app → **New Project** → **Deploy from GitHub repo**
3. Dans l'onglet **Variables** du projet Railway, ajoute les variables de ton `.env`
4. Railway détecte automatiquement Python et lance `python bot.py`

## Ajouter une sortie de jeu

Il suffit d'ajouter une ligne dans la Google Sheet avec la date, le nom du jeu et le lien. Le bot vérifie toutes les 30 minutes (configurable) et postera automatiquement l'annonce le jour J. Comme la sheet est republiée automatiquement à chaque modification, aucune action supplémentaire n'est nécessaire.

## Aller plus loin (idées)

- Ajouter une colonne `Posté` mise à jour manuellement pour garder une trace visuelle
- Utiliser l'API IGDB directement pour récupérer automatiquement jaquette, date et description
- Ajouter une commande slash `/prochaines-sorties` pour lister les jeux à venir
