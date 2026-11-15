"""Deterministic generation of flights and availability from the base catalog data.

The same base data, start date and seed always produce exactly the same catalog.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from seed.schema import BaseData

FLIGHT_SEATS = 20
# name, beds, price factor on the double-room base price, rooms per hotel, minimum hotel stars
ROOM_TYPES = (
    ("Singola", 1, Decimal("0.75"), 2, 2),
    ("Doppia", 2, Decimal("1.00"), 4, 2),
    ("Tripla", 3, Decimal("1.30"), 2, 3),
    ("Familiare", 4, Decimal("1.60"), 2, 3),
)
ACTIVITY_SPOTS = 10
NO_FLIGHT_WEEKDAY = 1  # Tuesday
WEEKEND = {4, 5, 6}  # Friday, Saturday, Sunday
CENT = Decimal("0.01")


@dataclass
class Catalog:
    flights: list[dict]
    room_types: list[dict]  # rows carry hotel_index (position in BaseData.hotels)
    room_availability: list[dict]  # rows carry room_type_index (position in room_types)
    activity_slots: list[dict]  # rows carry activity_index (position in BaseData.activities)


def season_factor(d: date) -> Decimal:
    """Price multiplier for the month of the given date."""
    if d.month in (7, 8):
        return Decimal("1.40")
    if d.month == 12:
        return Decimal("1.30")
    if d.month in (4, 5, 6, 9):
        return Decimal("1.10")
    return Decimal("0.90")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _variation(rng: random.Random, low: float, high: float) -> Decimal:
    return Decimal(f"{rng.uniform(low, high):.4f}")


def _flights(base: BaseData, days: list[date], rng: random.Random) -> list[dict]:
    departures = [a for a in base.airports if a.role == "departure"]
    destinations = [a for a in base.airports if a.role == "destination"]
    rows = []
    for dest in destinations:
        for dep in departures:
            for origin, destination in ((dep.iata, dest.iata), (dest.iata, dep.iata)):
                for day in days:
                    if day.weekday() == NO_FLIGHT_WEEKDAY:
                        continue
                    weekend = Decimal("1.10") if day.weekday() in WEEKEND else Decimal("1.00")
                    price = dest.base_fare * season_factor(day) * weekend * _variation(rng, 0.85, 1.15)
                    minutes = 6 * 60 + 15 * rng.randint(0, 56)  # 06:00 … 20:00, every 15 minutes
                    departure_at = datetime.combine(day, time()) + timedelta(minutes=minutes)
                    rows.append({
                        "origin": origin,
                        "destination": destination,
                        "departure_at": departure_at,
                        "arrival_at": departure_at + timedelta(hours=float(dest.flight_hours)),
                        "price": _money(price),
                        "seats_left": FLIGHT_SEATS,
                    })
    return rows


def _room_types(base: BaseData) -> list[dict]:
    return [
        {"hotel_index": i, "name": name, "beds": beds, "factor": factor, "rooms": rooms}
        for i, hotel in enumerate(base.hotels)
        for name, beds, factor, rooms, min_stars in ROOM_TYPES
        if hotel.stars >= min_stars
    ]


def _room_nights(base: BaseData, room_types: list[dict], days: list[date], rng: random.Random) -> list[dict]:
    """One row per room type per night. All room types of a hotel share that night's price variation."""
    rows = []
    for i, hotel in enumerate(base.hotels):
        types = [(j, rt) for j, rt in enumerate(room_types) if rt["hotel_index"] == i]
        for night in days:
            double = hotel.base_price * season_factor(night) * _variation(rng, 0.90, 1.10)
            rows.extend(
                {"room_type_index": j, "night": night, "price": _money(double * rt["factor"]),
                 "rooms_left": rt["rooms"]}
                for j, rt in types
            )
    return rows


def _activity_slots(base: BaseData, days: list[date]) -> list[dict]:
    return [
        {"activity_index": i, "day": day, "spots_left": ACTIVITY_SPOTS}
        for i, activity in enumerate(base.activities)
        for day in days
        if day.weekday() in activity.weekdays
    ]


def build_catalog(base: BaseData, start: date, days: int = 365, seed: int = 42) -> Catalog:
    rng = random.Random(seed)
    calendar = [start + timedelta(days=n) for n in range(days)]
    flights = _flights(base, calendar, rng)
    room_types = _room_types(base)
    return Catalog(
        flights=flights,
        room_types=[{k: rt[k] for k in ("hotel_index", "name", "beds")} for rt in room_types],
        room_availability=_room_nights(base, room_types, calendar, rng),
        activity_slots=_activity_slots(base, calendar),
    )