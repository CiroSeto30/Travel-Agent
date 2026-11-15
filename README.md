# Travel Assistant

Conversational AI travel assistant that builds personalized itineraries (flights, hotels, daily activities) within budget and books them via chat.

Status: work in progress.

## Requirements

- Python 3.12+
- Docker Desktop

## Run locally

```bash
# 1. Configuration
cp .env.example .env          # then fill in LLM_API_KEY and JWT_SECRET

# 2. Databases (PostgreSQL + Qdrant)
docker compose up -d

# 3. Backend dependencies
python -m venv .venv
source .venv/Scripts/activate  # Windows (Git Bash); on macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend

# 4. Tables and synthetic catalog (once; running it again does nothing)
python -m seed.load_db

# 5. Start the server
fastapi dev app/main.py
```

## Catalog

`python -m seed.load_db` creates the tables and loads a synthetic catalog for the next 12 months: 11 countries, 33 destinations, 200 hotels, 500 activities, about 62,000 flights. The base data lives in `backend/seed/data/`; dates, prices and availability are generated with a fixed random seed, so every run produces the same catalog.

## Tests

From the `backend/` folder, with the databases running:

```bash
pytest
```

The tests use a separate `travel_test` database, created automatically on the first run.

Then open:

- http://localhost:8000 — web app
- http://localhost:8000/docs — interactive API documentation
- http://localhost:8000/api/health — health check
