"""Catalog tables: what can be booked (flights, hotels, activities) and when."""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Boolean, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

Money = Numeric(10, 2)


class Airport(Base):
    __tablename__ = "airports"

    iata: Mapped[str] = mapped_column(String(3), primary_key=True)
    city: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100))
    is_departure: Mapped[bool] = mapped_column(Boolean, default=False)


class Flight(Base):
    """A one-way flight; a round trip uses two of them."""

    __tablename__ = "flights"
    __table_args__ = (Index("ix_flights_route_departure", "origin", "destination", "departure_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(ForeignKey("airports.iata"))
    destination: Mapped[str] = mapped_column(ForeignKey("airports.iata"))
    departure_at: Mapped[datetime] = mapped_column(DateTime)
    arrival_at: Mapped[datetime] = mapped_column(DateTime)
    price: Mapped[Decimal] = mapped_column(Money)
    seats_left: Mapped[int] = mapped_column(Integer)


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), index=True)
    country: Mapped[str] = mapped_column(String(100))
    stars: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)


class RoomType(Base):
    """A kind of room in a hotel (single, double, …), with how many people it sleeps."""

    __tablename__ = "room_types"
    __table_args__ = (
        UniqueConstraint("hotel_id", "name", name="uq_room_types_hotel_name"),
        CheckConstraint("beds BETWEEN 1 AND 6", name="ck_room_types_beds"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    beds: Mapped[int] = mapped_column(Integer)


class RoomAvailability(Base):
    """One row per room type per night: the price of a room that night and how many are still free."""

    __tablename__ = "room_availability"

    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"), primary_key=True)
    night: Mapped[date] = mapped_column(Date, primary_key=True)
    price: Mapped[Decimal] = mapped_column(Money)
    rooms_left: Mapped[int] = mapped_column(Integer)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), index=True)
    country: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Money)
    duration_hours: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    start_time: Mapped[time] = mapped_column(Time)  # local time, the same on every day it runs
    description: Mapped[str] = mapped_column(Text)


class ActivitySlot(Base):
    """One row per activity per day it runs, with the spots still free."""

    __tablename__ = "activity_slots"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    spots_left: Mapped[int] = mapped_column(Integer)