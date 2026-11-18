"""What the API sends and receives about itineraries and bookings (the shapes the frontend reads)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class FlightOut(BaseModel):
    kind: str  # "flight_out" or "flight_return"
    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    seats: int
    price: Decimal  # for the group


class RoomOut(BaseModel):
    name: str
    beds: int
    quantity: int


class HotelOut(BaseModel):
    name: str
    stars: int
    nights: int
    rooms: list[RoomOut]
    price: Decimal  # every night, every room


class ActivityOut(BaseModel):
    activity_id: int
    name: str
    start_time: str  # "HH:MM", local time
    end_time: str
    price_per_person: Decimal
    price: Decimal  # for the group
    selected: bool


class DayOut(BaseModel):
    day: date
    activities: list[ActivityOut]  # chosen and alternatives, by start time


class ItineraryDetails(BaseModel):
    itinerary_id: int
    variant: str
    status: str
    city: str
    travelers: int
    start_date: date
    end_date: date
    budget: Decimal
    total: Decimal
    flights: list[FlightOut]
    hotel: HotelOut
    days: list[DayOut]  # full days only: not the arrival day, not the departure day


class ItinerarySummary(BaseModel):
    """One proposal ticket: what the chat shows before the details are opened."""

    itinerary_id: int
    variant: str
    status: str
    city: str
    origin: str
    destination: str
    hotel: str
    hotel_stars: int
    start_date: date
    end_date: date
    travelers: int
    total: Decimal
    budget: Decimal


class ActivityChoice(BaseModel):
    day: date
    activity_id: int


class BookingOut(BaseModel):
    booking_id: int
    status: str
    booked_at: datetime
    total: Decimal
    itinerary: ItinerarySummary
