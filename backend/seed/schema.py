"""Shape and validation of the hand-written catalog data in seed/data/."""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

Category = Literal["culture", "food", "nature", "sport", "relax", "nightlife"]
Target = Literal["families", "young", "couples", "sporty"]


class AirportIn(BaseModel):
    iata: str = Field(pattern=r"^[A-Z]{3}$")
    city: str
    country: str
    role: Literal["departure", "destination"]
    base_fare: Decimal | None = Field(default=None, gt=0)  # one-way fare from Italy, EUR
    flight_hours: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def destinations_have_fare_and_duration(self) -> "AirportIn":
        if self.role == "destination" and (self.base_fare is None or self.flight_hours is None):
            raise ValueError(f"Destination {self.iata} needs base_fare and flight_hours")
        return self


class HotelIn(BaseModel):
    name: str
    city: str
    stars: int = Field(ge=2, le=5)
    base_price: Decimal = Field(gt=0)  # per night, EUR
    description: str = Field(min_length=10)


class ActivityIn(BaseModel):
    name: str
    city: str
    category: Category
    target: Target
    price: Decimal = Field(ge=0)
    duration_hours: Decimal = Field(gt=0)
    weekdays: list[int] = Field(min_length=1)  # Monday = 0 … Sunday = 6
    description: str = Field(min_length=20)

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, days: list[int]) -> list[int]:
        if any(d not in range(7) for d in days) or len(set(days)) != len(days):
            raise ValueError(f"weekdays must be distinct values from 0 to 6, got {days}")
        return days


@dataclass(frozen=True)
class BaseData:
    airports: list[AirportIn]
    hotels: list[HotelIn]
    activities: list[ActivityIn]

    def country_of(self, city: str) -> str:
        return next(a.country for a in self.airports if a.role == "destination" and a.city == city)


def _read(path: Path, model: type[BaseModel]) -> list:
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = []
    for i, item in enumerate(raw):
        try:
            records.append(model.model_validate(item))
        except ValidationError as e:
            raise ValueError(f"{path.name}, record {i}: {e}") from e
    return records


def load_base_data(data_dir: Path) -> BaseData:
    """Read and validate the three JSON files. Raises ValueError naming the bad record."""
    airports = _read(data_dir / "airports.json", AirportIn)
    hotels = _read(data_dir / "hotels.json", HotelIn)
    activities = _read(data_dir / "activities.json", ActivityIn)

    codes = [a.iata for a in airports]
    if len(codes) != len(set(codes)):
        raise ValueError("Duplicate airport codes in airports.json")

    cities = {a.city for a in airports if a.role == "destination"}
    for h in hotels:
        if h.city not in cities:
            raise ValueError(f"Hotel '{h.name}': unknown city '{h.city}'")
    for a in activities:
        if a.city not in cities:
            raise ValueError(f"Activity '{a.name}': unknown city '{a.city}'")

    return BaseData(airports=airports, hotels=hotels, activities=activities)