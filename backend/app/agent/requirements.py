"""The trip requirements the agent collects in the chat, and the rules they must follow (docs/design.md §3, §8).

The LLM only extracts what the user said; whether it is complete and valid is decided here, in code.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import get_args

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Airport
from app.db.models.itinerary import MAX_TRAVELERS
from app.planner.planner import TripRequest
from seed.schema import Category

CATEGORIES: tuple[str, ...] = get_args(Category)
REQUIRED = ("budget", "country", "month", "nights", "travelers", "origin")
NIGHTS = (2, 14)


class Requirements(BaseModel):
    """What is known about the trip so far. None means "not said yet"."""

    budget: Decimal | None = None  # for the whole group, in euro
    country: str | None = None
    month: int | None = None
    nights: int | None = None
    travelers: int | None = None
    origin: str | None = None  # departure airport, as a code or a city name
    preferences: str | None = None  # in the user's words
    categories: list[str] | None = None


@dataclass(frozen=True)
class CatalogInfo:
    countries: dict[str, list[str]]  # country -> destination cities
    departures: dict[str, str]  # airport code -> city


def load_catalog_info(s: Session) -> CatalogInfo:
    countries: dict[str, list[str]] = {}
    departures = {}
    for a in s.scalars(select(Airport).order_by(Airport.country, Airport.city)):
        if a.is_departure:
            departures[a.iata] = a.city
        else:
            countries.setdefault(a.country, []).append(a.city)
    return CatalogInfo(countries, dict(sorted(departures.items())))


def merge(current: Requirements, update: Requirements) -> Requirements:
    """The user changes one thing at a time: what the new message says replaces, the rest stays."""
    return current.model_copy(update=update.model_dump(exclude_none=True))


@dataclass
class Review:
    requirements: Requirements  # with country and origin in their catalog form
    missing: list[str] = field(default_factory=list)
    problems: dict[str, str] = field(default_factory=dict)  # field -> "not_available", "out_of_range", "unknown"

    @property
    def complete(self) -> bool:
        return not self.missing and not self.problems

    def trip_request(self) -> TripRequest:
        r = self.requirements
        return TripRequest(country=r.country, month=r.month, nights=r.nights, travelers=r.travelers,
                           budget=r.budget, origin=r.origin, preferences=r.preferences or "",
                           categories=tuple(r.categories or ()))


def _match(said: str, names: dict[str, str]) -> str | None:
    """`names` maps every accepted spelling, lowercase, to the catalog value."""
    return names.get(said.strip().lower())


def review(req: Requirements, catalog: CatalogInfo) -> Review:
    r = Review(req.model_copy())
    r.missing = [f for f in REQUIRED if getattr(req, f) is None]

    if req.country is not None:
        country = _match(req.country, {c.lower(): c for c in catalog.countries})
        if country is None:
            r.problems["country"] = "not_available"
        r.requirements.country = country or req.country
    if req.origin is not None:
        spellings = {code.lower(): code for code in catalog.departures}
        spellings |= {city.lower(): code for code, city in catalog.departures.items()}
        origin = _match(req.origin, spellings)
        if origin is None:
            r.problems["origin"] = "not_available"
        r.requirements.origin = origin or req.origin

    ranges = {"month": (1, 12), "nights": NIGHTS, "travelers": (1, MAX_TRAVELERS)}
    for name, (low, high) in ranges.items():
        value = getattr(req, name)
        if value is not None and not low <= value <= high:
            r.problems[name] = "out_of_range"
    if req.budget is not None and req.budget <= 0:
        r.problems["budget"] = "out_of_range"
    if req.categories and not set(req.categories) <= set(CATEGORIES):
        r.problems["categories"] = "unknown"
    return r
