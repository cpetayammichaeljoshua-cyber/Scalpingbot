# Railway Deployment Guide — MiroFish Swarm + G0DM0D3 AI Bot

## Quick Deploy

1. Push this repository to GitHub
2. Create a new Railway project → "Deploy from GitHub repo"
3. Railway auto-detects the `Dockerfile` and builds the container
4. Set the required environment variables (see below)
5. (Recommended) Add a Railway Volume mounted at `/data` for SQLite persistence

---

## Required Environment Variables

Set these in Railway → Variables tab:

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | Primary AI — G0DM0D3 ULTRAPLINIAN engine via OpenRouter |
| `BINANCE_API_KEY` | Binance USDM Futures read access |
| `BINANCE_API_SECRET` | Binance USDM Futures read access |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHANNEL_ID` | Channel to send signals (e.g. `-1003031984142`) |
| `TELEGRAM_CHAT_ID` | Admin personal chat ID for alerts |

## Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Claude fallback (leave blank — G0DM0D3 handles AI) |
| `OPENAI_API_KEY` | — | GPT-4o-mini fallback (leave blank — G0DM0D3 handles AI) |
| `DATA_DIR` | `/data` | Persistent SQLite storage dir (match to Railway volume) |
| `PORT` | `8080` | Health-check HTTP port |
| `SCAN_PARALLEL_LIMIT` | `15` | Concurrent market scans |
| `SIGNALS_PER_HOUR_MIN` | `5` | Min signals per hour |
| `SIGNALS_PER_HOUR_MAX` | `10` | Max signals per hour |
| `AI_THRESHOLD_PERCENT` | `80` | Confidence gate % |

---

## Volume Mount (Recommended)

To persist the SQLite trading history and NN weights across deployments:

1. Railway → your service → "Add Volume"
2. Mount path: `/data`
3. Set env var: `DATA_DIR=/data`

Without a volume, the bot retrains its neural net from scratch on each deployment (works fine — just takes a few more cycles to reach peak accuracy).

---

## Health Check

The bot runs an HTTP server on `PORT` (default `8080`):
- `GET /health` → JSON with bot status, uptime, timestamp
- `GET /` → plain text "MiroFish Swarm Bot running"

Railway automatically polls `/health` every 60 seconds.

---

## Architecture

```
python3 start_ultimate_bot.py
       │
       ├── Health check server (aiohttp, port 8080)
       │
       └── MiroFish Parallel Scanner (80 symbols, Semaphore=15)
              │
              └── 10 Swarm Agents per symbol:
                    TrendAgent | MomentumAgent | VolumeAgent
                    VolatilityAgent | OrderFlowAgent | SentimentAgent
                    FundingFlowAgent | PivotSRAgent | FLOOPAgent
                    G0DM0D3 Agent (ULTRAPLINIAN → qwen/qwen3.6-plus:free)
```

---

## Build Method

Railway uses the **Dockerfile** (primary). Fallback: `nixpacks.toml`.

The Dockerfile:
- Base: `python:3.11-slim`
- Installs: all deps from `requirements.txt`
- Creates: `/data` directory for SQLite persistence
- Runs: `python3 start_ultimate_bot.py`
