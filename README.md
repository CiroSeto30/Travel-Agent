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

# 3. Backend
python -m venv .venv
source .venv/Scripts/activate  # Windows (Git Bash); on macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
fastapi dev app/main.py
```

Then open:

- http://localhost:8000 — web app
- http://localhost:8000/docs — interactive API documentation
- http://localhost:8000/api/health — health check
