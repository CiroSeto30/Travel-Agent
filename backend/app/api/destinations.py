"""Where a trip can go and where it can start from, read from the catalog (public: shown before login too)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.requirements import load_catalog_info
from app.api.deps import DbSession

router = APIRouter(prefix="/api/destinations", tags=["destinations"])


class CountryOut(BaseModel):
    country: str
    cities: list[str]


class DepartureOut(BaseModel):
    iata: str
    city: str


class DestinationsOut(BaseModel):
    countries: list[CountryOut]
    departures: list[DepartureOut]


@router.get("")
def destinations(db: DbSession) -> DestinationsOut:
    info = load_catalog_info(db)
    return DestinationsOut(
        countries=[CountryOut(country=c, cities=cities) for c, cities in info.countries.items()],
        departures=[DepartureOut(iata=code, city=city) for code, city in info.departures.items()])
