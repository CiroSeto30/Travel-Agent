"""Itineraries proposed to a user, their items, and the bookings made from them."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

Money = Numeric(10, 2)

ITINERARY_STATUSES = ("proposed", "superseded", "booked", "cancelled")
BOOKING_STATUSES = ("confirmed", "cancelled")
ITEM_KINDS = ("flight_out", "flight_return", "hotel_night", "activity")
MAX_TRAVELERS = 6


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Itinerary(Base):
    __tablename__ = "itineraries"
    __table_args__ = (
        CheckConstraint(_in("status", ITINERARY_STATUSES), name="ck_itineraries_status"),
        CheckConstraint(f"travelers BETWEEN 1 AND {MAX_TRAVELERS}", name="ck_itineraries_travelers"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    # proposals generated together share this id; booking one supersedes its siblings
    proposal_set_id: Mapped[str | None] = mapped_column(String(36), index=True)
    variant: Mapped[str] = mapped_column(String(20))
    travelers: Mapped[int] = mapped_column(Integer)
    budget: Mapped[Decimal] = mapped_column(Money)  # kept to check later changes, like the activity choice
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    total_cost: Mapped[Decimal] = mapped_column(Money)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    superseded_by: Mapped[int | None] = mapped_column(ForeignKey("itineraries.id"))

    items: Mapped[list["ItineraryItem"]] = relationship(order_by="ItineraryItem.day")


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"
    __table_args__ = (
        CheckConstraint(_in("kind", ITEM_KINDS), name="ck_itinerary_items_kind"),
        CheckConstraint(
            "num_nonnulls(flight_id, room_type_id, activity_id) = 1", name="ck_itinerary_items_one_reference"
        ),
        CheckConstraint("quantity >= 1", name="ck_itinerary_items_quantity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    itinerary_id: Mapped[int] = mapped_column(ForeignKey("itineraries.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    flight_id: Mapped[int | None] = mapped_column(ForeignKey("flights.id"))
    room_type_id: Mapped[int | None] = mapped_column(ForeignKey("room_types.id"))
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    # seats for flights and activities, rooms for a hotel night
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    day: Mapped[date] = mapped_column(Date)
    # total of this line (unit price x quantity) at proposal time, so the itinerary total never changes later
    price: Mapped[Decimal] = mapped_column(Money)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (CheckConstraint(_in("status", BOOKING_STATUSES), name="ck_bookings_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    itinerary_id: Mapped[int] = mapped_column(ForeignKey("itineraries.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    total_cost: Mapped[Decimal] = mapped_column(Money)
    booked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    itinerary: Mapped[Itinerary] = relationship()