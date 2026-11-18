# The app image: FastAPI backend plus the static frontend it serves.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/models

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

WORKDIR /app/backend
EXPOSE 8000
# First start: tables, synthetic catalog and Qdrant index (each step does nothing if already done)
CMD ["sh", "-c", "python -m seed.load_db && python -m seed.index_activities && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
