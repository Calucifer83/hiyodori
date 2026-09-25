# Bot Discord — Annonces de sorties de jeux (100% automatique via IGDB)

Ce bot interroge l'API IGDB chaque jour, à heure fixe (heure de Paris), pour trouver les jeux qui sortent ce jour-là, calcule un score de popularité, et poste automatiquement les meilleurs dans un channel Discord. Aucune saisie manuelle n'est nécessaire.

## 1. Créer le bot Discord

1. Va sur https://discord.com/developers/applications → **New Application**
2. Onglet **Bot** → **Reset Token** → copie le token (ne le partage jamais publiquement)
3. Onglet **OAuth2 > URL Generator** :
   - Scopes : `bot` (important : pas seulement `applications.commands`)
   - Permissions : `Send Messages`, `Embed Links`
   - Ouvre l'URL générée, sélectionne ton serveur, autorise

## 2. Créer les identifiants IGDB (via Twitch)

IGDB appartient à Twitch, donc l'authentification passe par un compte développeur Twitch (gratuit).

1. Va sur https://dev.twitch.tv/console/apps → connecte-toi avec un compte Twitch (ou crées-en un)
2. Clique sur **Register Your Application**
3. Remplis :
   - **Name** : un nom unique (ex: `mon-bot-sorties-jeux`)
   - **OAuth Redirect URLs** : `http://localhost` (obligatoire même si tu ne l'utilises pas vraiment)
   - **Category** : `Application Integration`
4. Valide, puis ouvre l'application créée → **Manage**
5. Note le **Client ID**, puis clique sur **New Secret** pour générer le **Client Secret**

## 3. Configurer le projet

1. Copie `.env.example` en `.env` et remplis toutes les valeurs
2. Installe les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Teste en local :
   ```bash
   python bot.py
   ```

## 4. Héberger le bot 24/7 (Railway)

1. Pousse ces fichiers sur GitHub (⚠️ jamais ton `.env` rempli — garde-le dans `.gitignore`)
2. Sur https://railway.app → **New Project** → **Deploy from GitHub repo**
3. Onglet **Variables** → ajoute toutes les variables de ton `.env`
4. Railway détecte automatiquement Python et lance `python bot.py`

## Comment fonctionne le score de popularité

Le bot combine trois métriques IGDB en une seule note :

```
score = (hypes × 2) + follows + (note moyenne / 10)
```

- **hypes** : nombre de joueurs ayant marqué le jeu comme "attendu" avant sa sortie
- **follows** : nombre de joueurs qui suivent le jeu
- **total_rating** : note moyenne (critique + joueurs), sur 100

Seuls les jeux "principaux" sont pris en compte (catégories : jeu principal, extension autonome, remake, remaster) — les DLC, ports et éditions spéciales sont automatiquement exclus pour éviter de gonfler artificiellement le nombre de sorties du jour.

## Configuration

| Variable | Rôle | Défaut |
|---|---|---|
| `TOP_N` | Nombre max de jeux annoncés par jour | `5` |
| `ANNOUNCE_HOUR` / `ANNOUNCE_MINUTE` | Heure de vérification (heure de Paris) | `9` / `0` |

## Limite connue

Le score favorise les jeux suivis *avant* leur sortie. Un petit jeu indépendant sorti sans annonce préalable peut donc être sous-représenté, même s'il devient populaire après coup. C'est un compromis raisonnable pour filtrer automatiquement 40 sorties/jour en 5 annonces pertinentes.

## Aller plus loin (idées)

- Ajouter les plateformes de sortie dans l'embed (`fields platforms.name`)
- Une commande slash `/prochaines-sorties` listant les jeux attendus des prochains jours
- Un système de cache pour éviter de re-télécharger un token à chaque redémarrage
