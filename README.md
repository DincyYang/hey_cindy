# Hey Cindy

[![CI](https://github.com/DincyYang/HeyCindy/actions/workflows/test.yml/badge.svg)](https://github.com/DincyYang/HeyCindy/actions/workflows/test.yml)

A distributed voice-controlled automation system. Say **"Hey Cindy, turn on the light"** — the light turns on.

## Architecture

```
Local (Mac)              Cloud (AWS EC2, Linux)        Stores
────────────────         ──────────────────────        ──────────────────
Wake word detect    →    FastAPI server           →    Redis    (light state)
Speech-to-text           Bearer-token auth        →    Postgres (history +
Hybrid NLP pipeline      REST API + /metrics                     latency/tokens)
Voice feedback           Docker container
Flask dashboard     ↗
```

Two independent failure domains: if Redis is down the light state falls back to
an in-process value, and if Postgres is down history writes are dropped with a
log line. Neither can fail the `POST /command` critical path.

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy, Docker, AWS EC2 (t3.micro)
- **Stores**: Redis (hot light state), PostgreSQL (durable command history)
- **NLP**: rule-based fast path + Claude (`claude-haiku-4-5`) for ambiguous input, with an offline keyword fallback
- **Voice**: Porcupine wake word detection, Google Speech-to-Text
- **Observability**: per-command latency + token-usage logging, `/metrics` aggregate, Flask dashboard
- **Testing**: pytest against fakeredis + SQLite, GitHub Actions CI (100% coverage gate on core modules)

## How a command flows

1. **Wake word** — Porcupine runs on an audio callback thread; the handler thread waits on an `Event` and pauses the mic while a command is captured.
2. **Fast path** — an unambiguous keyword match (`turn on the light`) is classified locally in microseconds. No network call, no tokens.
3. **Escalation** — only ambiguous, negated, or conflicting input goes to Claude, which returns JSON with `command`, `confidence`, `category`, and `reason`. On timeout or API error the keyword classifier answers instead.
4. **Policy** — `decision.py` maps the category to `execute` / `clarify` / `reject` / `ignore`; a `clarify` triggers one follow-up listen without needing the wake word again.
5. **Cloud** — the command, its latency, and its token usage go to the API: state to Redis, the row to Postgres.
6. **Dashboard** — polls `/state` and `/metrics` for live light state, recent commands, p95 latency, LLM escalation rate, and estimated cost.

## Project Structure

```
local/                 Mac-side voice pipeline + dashboard
cloud/                 FastAPI service (Dockerized, deployed to EC2)
tests/                 pytest suite
```

| File | Role |
|------|------|
| `local/wake_word.py` | Wake word detection (Porcupine) |
| `local/command_listener.py` | Speech-to-text via Google API |
| `local/normalizer.py` | Raw text → on / off / unknown, instrumented with latency + tokens |
| `local/decision.py` | Execute / clarify / reject / ignore policy |
| `local/cloud_client.py` | Send command + metrics to the cloud via REST |
| `local/command.py` | Execute command + text-to-speech |
| `local/dashboard.py` | Web control panel and cost/latency view (Flask) |
| `local/main.py` | Voice controller entry point |
| `cloud/app.py` | Cloud API (FastAPI): `/state`, `/command`, `/metrics`, `/health` |
| `cloud/state.py` | Light state in Redis, with in-process fallback |
| `cloud/db.py` | Command history in PostgreSQL, plus the usage/cost aggregate |
| `cloud/Dockerfile` | Container image for the cloud service |

## Run Locally

```bash
# Clone and set up environment
git clone https://github.com/DincyYang/hey_cindy.git
cd hey_cindy
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure secrets (.env is auto-loaded on import — no need to source it)
cp .env.example .env        # then fill in ANTHROPIC_API_KEY + PORCUPINE_ACCESS_KEY

# Start local dashboard (web UI)
python -m local.dashboard
# Open http://127.0.0.1:6060

# Start voice controller
python -m local.main
```

## Run the Cloud Service

```bash
docker build -f cloud/Dockerfile -t hey-cindy-cloud .
docker run -p 8000:8000 \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  -e DATABASE_URL=postgresql+psycopg2://cindy:cindy@host.docker.internal:5432/hey_cindy \
  -e HEY_CINDY_TOKEN=your-token \
  hey-cindy-cloud
```

## Run Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Coverage scope and the 100% gate are configured in `pytest.ini`, so a local run
enforces exactly what CI does. The gate covers the NLP, policy, storage, and API
modules — including their failure paths; the voice I/O modules need a microphone
and are out of scope. Tests need no Redis and no Postgres — they run
against `fakeredis` and SQLite.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Claude API key (intent classification) |
| `PORCUPINE_ACCESS_KEY` | — | Porcupine wake-word key |
| `HEY_CINDY_MODEL` | `claude-haiku-4-5` | Classifier model |
| `HEY_CINDY_LLM_TIMEOUT` | `5` | Seconds before falling back to keywords |
| `HEY_CINDY_CLOUD` | `http://3.234.157.34:8000` | Cloud API base URL |
| `HEY_CINDY_TOKEN` | `cindy-dev-token-123` | Auth token |
| `REDIS_URL` | `redis://localhost:6379/0` | Light-state store (cloud) |
| `DATABASE_URL` | `postgresql+psycopg2://cindy:cindy@localhost:5432/hey_cindy` | History store (cloud) |
| `HEY_CINDY_PRICE_IN` / `HEY_CINDY_PRICE_OUT` | `1.00` / `5.00` | USD per 1M tokens, used for cost estimates |

## Roadmap

- [x] Wake word detection
- [x] Speech-to-text + hybrid NLP pipeline
- [x] Cloud API (FastAPI + AWS EC2), Dockerized
- [x] Redis + PostgreSQL, each degrading independently
- [x] Local dashboard with live state, latency, token usage, and cost
- [x] Unit tests + CI (GitHub Actions, 100% gate on core modules)
- [ ] React frontend + WebSocket (replace dashboard polling)
- [ ] Physical smart plug integration
