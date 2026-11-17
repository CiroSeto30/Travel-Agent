"""Book a proposed itinerary in one database transaction (docs/design.md §11).

Every availability row the itinerary uses is locked with SELECT ... FOR UPDATE, always in the same order,
then checked and decreased. Two bookings that want the same seat or room run one after the other, never
both on the same count. The caller commits on success and rolls back on BookingError.
"""

from collections import Counter
from datetime import date

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.db.models import ActivitySlot, Booking, Flight, Itinerary, RoomAvailability


class BookingError(Exception):
    def __init__(self, code: str, message: str, item: str | None = None) -> None:
        super().__init__(message)
        self.code = code  # "not_found", "not_bookable", "unavailable"
        self.item = item  # the item no longer available, for "unavailable"


def _lock_proposal_set(s: Session, user_id: int, itinerary_id: int) -> Itinerary:
    """Lock the itinerary together with its sibling proposals, so only one of them can ever be booked."""
    set_id = s.scalar(select(Itinerary.proposal_set_id).where(
        Itinerary.id == itinerary_id, Itinerary.user_id == user_id))
    if set_id is None:
        raise BookingError("not_found", f"itinerary {itinerary_id} not found")
    locked = s.scalars(select(Itinerary).where(Itinerary.proposal_set_id == set_id)
                       .order_by(Itinerary.id).with_for_update().execution_options(populate_existing=True)).all()
    return next(i for i in locked if i.id == itinerary_id)


def _needed(itinerary: Itinerary) -> tuple[Counter, Counter, Counter]:
    """How much the itinerary takes from each row: seats per flight, rooms per (type, night), spots per (activity, day)."""
    seats, rooms, spots = Counter(), Counter(), Counter()
    for item in itinerary.items:
        if item.flight_id is not None:
            seats[item.flight_id] += item.quantity
        elif item.room_type_id is not None:
            rooms[(item.room_type_id, item.day)] += item.quantity
        else:
            spots[(item.activity_id, item.day)] += item.quantity
    return seats, rooms, spots


def _take(rows, needed: Counter, key, field: str, describe) -> None:
    found = {key(r): r for r in rows}
    for k in sorted(needed):
        row = found.get(k)
        if row is None or getattr(row, field) < needed[k]:
            raise BookingError("unavailable", f"{describe(k)} is no longer available", describe(k))
        setattr(row, field, getattr(row, field) - needed[k])


def book_itinerary(s: Session, *, user_id: int, itinerary_id: int) -> Booking:
    itinerary = _lock_proposal_set(s, user_id, itinerary_id)
    if itinerary.status == "booked":  # idempotent: booking twice returns the first booking
        return s.scalar(select(Booking).where(Booking.itinerary_id == itinerary.id))
    if itinerary.status != "proposed":
        raise BookingError("not_bookable", f"itinerary {itinerary_id} is {itinerary.status}")

    seats, rooms, spots = _needed(itinerary)
    # always the same order (flights, then hotel nights, then activities, each by key): no deadlocks
    flights = s.scalars(select(Flight).where(Flight.id.in_(seats)).order_by(Flight.id)
                        .with_for_update().execution_options(populate_existing=True))
    _take(flights, seats, lambda r: r.id, "seats_left", lambda k: f"flight {k}")
    nights = s.scalars(select(RoomAvailability)
                       .where(tuple_(RoomAvailability.room_type_id, RoomAvailability.night).in_(list(rooms)))
                       .order_by(RoomAvailability.room_type_id, RoomAvailability.night)
                       .with_for_update().execution_options(populate_existing=True))
    _take(nights, rooms, lambda r: (r.room_type_id, r.night), "rooms_left",
          lambda k: f"room type {k[0]} on {_day(k[1])}")
    slots = s.scalars(select(ActivitySlot)
                      .where(tuple_(ActivitySlot.activity_id, ActivitySlot.day).in_(list(spots)))
                      .order_by(ActivitySlot.activity_id, ActivitySlot.day)
                      .with_for_update().execution_options(populate_existing=True))
    _take(slots, spots, lambda r: (r.activity_id, r.day), "spots_left", lambda k: f"activity {k[0]} on {_day(k[1])}")

    itinerary.status = "booked"
    for sibling in s.scalars(select(Itinerary).where(
            Itinerary.proposal_set_id == itinerary.proposal_set_id, Itinerary.id != itinerary.id,
            Itinerary.status == "proposed")):
        sibling.status, sibling.superseded_by = "superseded", itinerary.id
    booking = Booking(user_id=user_id, itinerary_id=itinerary.id, total_cost=itinerary.total_cost)
    s.add(booking)
    s.flush()
    return booking


def _day(d: date) -> str:
    return d.isoformat()