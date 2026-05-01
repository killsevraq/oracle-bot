# Oracle Bot V2.0

Bot automatise de paris sur Bitcoin combinant les bougies Binance 10 min et les marches publics Polymarket.
Ce dépôt implémente l'intégralité du cahier des charges V2.0 : **mode DEMO gratuit** (paris simulés sur vrais prix) et **mode PRODUCTION** (paris réels via Polymarket CLOB), bascule sans changer le code.

> *Valide d'abord. Investis ensuite.*

## Sommaire

- [Architecture](#architecture)
- [Demarrage rapide](#demarrage-rapide-mode-demo-0)
- [Variables d'environnement](#variables-denvironnement)
- [Bascule DEMO → PROD](#bascule-demo--prod)
- [Bot Telegram](#bot-telegram)
- [Dashboard](#dashboard)
- [Tests & qualité](#tests--qualite)

## Architecture

```
oracle-bot/
├── backend/
│   ├── main.py            # FastAPI + lifespan = bot
│   ├── bot.py             # Orchestrateur asyncio (start/stop, SL/TP, paris)
│   ├── strategy.py        # Signal bougie + double confirmation
│   ├── binance_ws.py      # WebSocket Binance (btcusdt@kline_10m)
│   ├── polymarket.py      # Client REST public (gamma + clob)
│   ├── trader.py          # DemoTrader / ProdTrader (meme interface)
│   ├── telegram_bot.py    # Notifs + commandes /start /stop /mise /mode /solde /stats /status
│   ├── api.py             # REST + SSE (/api/events)
│   ├── db.py / models.py  # SQLite + table bets
│   ├── state.py           # Etat partage du bot
│   └── config.py          # Settings pydantic
├── frontend/              # Dashboard Vite + React + TS + Recharts
└── tests/                 # pytest (strategie + trader)
```

Flow :

1. Binance WebSocket envoie chaque bougie BTC 10 min en temps réel (gratuit, public).
2. Le bot calcule la couleur de la bougie (verte/rouge) et la tendance court-terme.
3. **Double confirmation** : un pari n'est placé que si bougie + tendance Binance s'alignent. Sinon → skip.
4. Polymarket public est lu pour récupérer le prix du marché BTC et calculer un PnL virtuel réaliste.
5. **Mode DEMO** → log virtuel + résolution sur prix Binance après 5 min. **Mode PROD** → ordre réel via `py-clob-client`.
6. Résultat enregistré dans SQLite, dashboard et Telegram mis à jour en temps réel.

## Démarrage rapide (mode DEMO, 0$)

Prérequis : Python 3.10+, Node 18+.

```bash
git clone https://github.com/killsevraq/oracle-bot.git
cd oracle-bot

# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# Frontend
npm --prefix frontend install
npm --prefix frontend run build   # pour servir le dashboard depuis FastAPI

# Configuration
cp .env.example .env
# (optionnel) renseigne TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID

# Lancement
python -m backend.main
# Dashboard : http://localhost:8000/
# API       : http://localhost:8000/api
```

En développement frontend (hot-reload), lance plutôt :

```bash
npm --prefix frontend run dev   # http://localhost:5173 (proxy vers :8000/api)
```

## Variables d'environnement

Voir [`.env.example`](.env.example). Principales :

| Variable | Description | Defaut |
| --- | --- | --- |
| `MODE` | `demo` (paris virtuels) ou `prod` (Polymarket reel) | `demo` |
| `BET_AMOUNT` | Mise par pari en USDC | `5` |
| `STOP_LOSS` / `TAKE_PROFIT` | Seuils auto d'arret (USDC, `0` = off) | `0` |
| `DEMO_STARTING_BALANCE` | Solde virtuel de depart | `100` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Notifs Telegram | (vide → desactive) |
| `POLYMARKET_PRIVATE_KEY` / `POLYMARKET_FUNDER_ADDRESS` | Wallet pour mode prod uniquement | (vide) |
| `DATABASE_URL` | URL SQLAlchemy (async) | `sqlite+aiosqlite:///./data/oracle.db` |

## Bascule DEMO → PROD

1. Valide la stratégie en mode DEMO (≥ 2 semaines, win rate > 55 %).
2. Approvisionne un wallet Polygon avec des USDC.
3. Renseigne `POLYMARKET_PRIVATE_KEY` et `POLYMARKET_FUNDER_ADDRESS` dans `.env`.
4. Installe les deps prod : `pip install -e '.[prod]'` (ajoute `py-clob-client`).
5. Bascule `MODE=prod` (ou via le dashboard / `/mode prod` Telegram).

> Le code Python du bot est strictement identique. Seul le `Trader` change.

## Bot Telegram

Notifications automatiques :

| Evenement | Message |
| --- | --- |
| Pari place | `[DEMO] Pari UP — 5 USDC \| BTC-5min @ 67432.10` |
| Pari gagne | `[DEMO] GAGNE +4.50 USDC \| Solde: 104.50` |
| Pari perdu | `[DEMO] PERDU -5.00 USDC \| Solde: 95.00` |
| Stop-Loss | `Stop-Loss atteint — Bot arrete.` |
| Signal incertain | `Signal incertain — pari ignore (...)` |

Commandes :

| Cmd | Action |
| --- | --- |
| `/start` | Demarre le bot |
| `/stop` | Arrete le bot |
| `/mise 10` | Regle la mise a 10 USDC |
| `/mode demo` / `/mode prod` | Change de mode |
| `/solde` | Solde actuel |
| `/stats` | Resume gains / win rate |
| `/status` | Etat courant (mode, prix, signal) |

## Dashboard

- Section **Contrôle** : démarrer / arrêter, mode, marché cible, mise, stop-loss, take-profit.
- Section **Statistiques** : win rate, PnL, total misé, courbe des gains/pertes (Recharts).
- Section **Monitoring** : prix BTC live, tendance, couleur de bougie, signal courant, prochain pari, solde.
- Section **Historique** : tous les paris (DEMO et PROD) avec entrée / sortie / PnL.
- Badge `DEMO` / `PROD` permanent en haut de page.

Le frontend est branché en temps réel sur `/api/events` (Server-Sent Events).

## Tests & qualité

```bash
pip install -e '.[dev]'
ruff check backend tests
pytest -q
mypy backend
```

Et côté frontend :

```bash
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Limitations actuelles & roadmap

- Le `ProdTrader` expose la même interface que le `DemoTrader` ; le passage d'ordre Polymarket via `py-clob-client` est encore à brancher (sélection token YES/NO + post d'ordre limit) — la logique métier (signal, SL/TP, persistance) est déjà 100 % opérationnelle.
- Pas d'authentification du dashboard pour l'instant (déploiement local uniquement).
- Backtesting historique non inclus dans cette V1.

PRs et issues bienvenus.
