"""FastAPI entry point: creates the app, registers the API routes and serves the frontend."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import auth, bookings, itineraries
from app.config import ROOT_DIR, get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

@app.get("/api/health")
def health() -> dict[str, str]:
    """Quick check that the server is up."""
    return {"status": "ok"}

app.include_router(auth.router)
app.include_router(itineraries.router)
app.include_router(bookings.router)

# Mounted last: it answers every path not handled by the API routes above.
app.mount("/", StaticFiles(directory=ROOT_DIR / "frontend", html=True), name="frontend")