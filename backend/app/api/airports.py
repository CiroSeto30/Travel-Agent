"""Departure airports, for the registration form."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.db.models import Airport
from app.schemas.auth import AirportOut

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/airports")
def departure_airports(db: DbSession) -> list[AirportOut]:
    return list(db.scalars(select(Airport).where(Airport.is_departure).order_by(Airport.city)))