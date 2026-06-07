# Hey Cindy

[![CI](https://github.com/DincyYang/HeyCindy/actions/workflows/test.yml/badge.svg)](https://github.com/DincyYang/HeyCindy/actions/workflows/test.yml)

A distributed voice-controlled automation system. Say **"Hey Cindy, turn on the light"** — the light turns on.

## Architecture

```
Local (Mac)             Cloud (AWS EC2)         Physical
────────────────        ───────────────         ────────
Wake word detect   →    FastAPI server      →   Smart plug
Speech-to-text          SQLite (state)           (coming soon)
NLP pipeline            REST API
Voice feedback          Token-based auth
```

## Tech Stack

- **Backend**: Python, FastAPI, AWS EC2 (t3.micro)
- **NLP**: Claude (`claude-sonnet-4-6`) intent classifier + decision layer, with an offline keyword fallback
- **Voice**: Porcupine wake word detection, Google Speech-to-Text
- **Auth**: Token-based authentication
- **Testing**: pytest, GitHub Actions CI (80%+ coverage)

## Project Structure

```
local/                 Mac-side voice pipeline
cloud/                 FastAPI service (deployed to EC2)
tests/                 pytest suite
```

| File | Role |
|------|------|
| `local/wake_word.py` | Wake word detection (Porcupine) |
| `local/command_listener.py` | Speech-to-text via Google API |
| `local/normalizer.py` | Raw text → on / off / unknown (Claude + keyword fallback) |
| `local/decision.py` | Execute / clarify / reject / ignore |
| `local/cloud_client.py` | Send command to cloud via REST |
| `local/command.py` | Execute command + text-to-speech |
| `local/dashboard.py` | Web control panel (Flask) |
| `local/main.py` | Voice controller entry point |
| `cloud/app.py` | Cloud API (FastAPI + SQLite) |

## Run Locally

```bash
# Clone and set up environment
git clone https://github.com/DincyYang/hey_cindy.git
cd hey_cindy
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure secrets
cp .env.example .env        # then fill in ANTHROPIC_API_KEY + PORCUPINE_ACCESS_KEY
export $(grep -v '^#' .env | xargs)

# Start local dashboard (web UI)
python -m local.dashboard
# Open http://127.0.0.1:6060

# Start voice controller
python -m local.main
```

## Run Tests

```bash
pip install -r requirements-dev.txt
pytest --cov=. --cov-report=term-missing
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Claude API key (intent classification) |
| `PORCUPINE_ACCESS_KEY` | — | Porcupine wake-word key |
| `HEY_CINDY_MODEL` | `claude-sonnet-4-6` | Classifier model |
| `HEY_CINDY_CLOUD` | `http://3.234.157.34:8000` | Cloud API base URL |
| `HEY_CINDY_TOKEN` | `cindy-dev-token-123` | Auth token |

## Roadmap

- [x] Wake word detection
- [x] Speech-to-text + NLP pipeline
- [x] Cloud API (FastAPI + AWS EC2)
- [x] Local dashboard
- [x] Unit tests + CI (GitHub Actions)
- [x] LLM intent classification (Claude) with keyword fallback
- [ ] PostgreSQL + Redis
- [ ] React frontend + WebSocket
- [ ] Physical smart plug integration
