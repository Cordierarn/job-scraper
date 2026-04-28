# Job Scraper

Agrégateur d'offres d'emploi multi-sources (France) avec :
- **CLI** (`scraper.py`) — recherche ad-hoc
- **Web app Flask** (`app.py`) — UI interactive
- **Bot Telegram** (`bot/`) — alertes automatiques toutes les 4 h via GitHub Actions

## Sources

| Source | Type | Clé requise |
|---|---|---|
| France Travail | API officielle | ✅ |
| Adzuna | API | ✅ |
| Jooble | API | ✅ |
| APEC | API JSON publique | — |
| HelloWork | Scraping HTML | — |
| Free-Work | API JSON publique | — |
| LinkedIn | Endpoint guest | — |
| Indeed | `curl_cffi` (TLS impersonation) | — |
| JobSpy (meta) | Agrégation LinkedIn/Indeed/Glassdoor/Google | — |
| Talent.com | Scraping HTML | — |
| Codeur.com | Scraping HTML (freelance) | — |
| Welcome to the Jungle | API Algolia publique (+ fallback HTML) | — |
| Remotive | API publique (remote international) | — |

## Installation locale

```bash
pip install -r requirements.txt
cp .env.example .env
# édite .env et remplis tes clés
```

## Mode 1 — Web app

```bash
python app.py
# → http://127.0.0.1:5000
```

## Mode 2 — CLI

```bash
python scraper.py -k "data engineer" -l "Lyon" --contract alternance -o csv -f offres.csv
python scraper.py -k "data engineer" -l "Lyon" --max-age-hours 24
```

## Mode 3 — Bot Telegram (local)

```bash
python -m bot.main test    # vérifie la connexion Telegram
python -m bot.main list    # affiche les alertes
python -m bot.main once    # un scan, envoie les nouveautés
python -m bot.main daemon  # boucle (toutes les 4 h)
```

## Mode 4 — Bot 24/7 sur GitHub Actions

Le workflow [`.github/workflows/job-bot.yml`](.github/workflows/job-bot.yml) tourne **toutes les 4 h** sur runner gratuit. Il scanne, envoie les nouveautés sur Telegram, et **re-commit** `data/seen.json` pour que la dédup persiste entre runs.

### Mise en place

1. **Crée un repo GitHub** (privé recommandé) puis ajoute le remote :
   ```bash
   git remote add origin git@github.com:TON_USER/job-scraper.git
   git push -u origin main
   ```

2. **Settings → Secrets and variables → Actions → New repository secret** — ajoute :

   | Nom | Valeur |
   |---|---|
   | `FRANCE_TRAVAIL_CLIENT_ID` | depuis francetravail.io |
   | `FRANCE_TRAVAIL_CLIENT_SECRET` | idem |
   | `ADZUNA_APP_ID` | depuis developer.adzuna.com |
   | `ADZUNA_APP_KEY` | idem |
   | `JOOBLE_API_KEY` | depuis jooble.org/api/about |
   | `TELEGRAM_BOT_TOKEN` | depuis @BotFather |
   | `TELEGRAM_CHAT_ID` | id de ton chat (voir ci-dessous) |

3. **Settings → Actions → General → Workflow permissions** :
   coche **Read and write permissions** (sinon le commit de `seen.json` échouera).

4. **Premier run manuel** : Actions → "Job alerts bot" → Run workflow.

### Setup Telegram

1. Sur Telegram, parle à **@BotFather** → `/newbot` → récupère le **token**.
2. Envoie un message à ton bot fraîchement créé.
3. Ouvre `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` — repère `"chat":{"id":...}`.

## Configuration des alertes

Édite [`alerts.json`](alerts.json). Chaque entrée :

```json
{
  "name": "Data Engineer alternance Lyon",
  "keywords": "data engineer",
  "locations": ["Lyon", "Villeurbanne", "69"],
  "contract": "alternance",
  "remote": false,
  "sources": null,
  "limit": 30,
  "enabled": true
}
```

- `locations` — liste de lieux (villes, codes postaux, n° département). Le bot scanne chaque lieu et fusionne.
- `contract` — `cdi`, `cdd`, `freelance`, `stage`, `alternance`, `interim`, ou omis.
- `max_age_hours` — filtre de fraîcheur strict (ex: `24`) ; relayé aux sources qui supportent un filtre côté serveur (LinkedIn `f_TPR`, Indeed `fromage`, Adzuna `max_days_old`, JobSpy `hours_old`) puis re-filtré côté bot.
- `sources` — `null` = toutes ; sinon liste de noms (`"france_travail"`, `"indeed"`, …).
- `enabled: false` — désactive sans supprimer.

## Sécurité

- `.env` est dans `.gitignore` ; aucun secret ne quitte ta machine.
- Les secrets pour le workflow vivent **uniquement** dans GitHub Secrets.
- Si tu exposes par erreur un secret dans un commit, **régénère-le** chez le fournisseur (BotFather, Adzuna…).

## Limites connues

- Indeed : peut renvoyer 403 si Cloudflare durcit ; la détection TLS du `curl_cffi` est régulièrement mise à jour.
- WTTJ : les clés Algolia publiques peuvent changer ; un fallback HTML est gardé en secours.
- JobSpy : sur CI sans proxy, rester sur des volumes modestes par run (en pratique <= 50) pour garder des résultats stables.
- Jooble : index US, peu de résultats français pour des requêtes en anglais.
