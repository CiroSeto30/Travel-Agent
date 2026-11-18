"""Read a saved itinerary back from its items, in the shapes the chat and the details panel show."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity, ActivitySlot, Flight, Hotel, Itinerary, ItineraryItem, RoomType
from app.schemas.itinerary import (ActivityOut, DayOut, FlightOut, HotelOut, ItineraryDetails, ItinerarySummary,
                                   RoomOut)


def end_time(start: time, hours) -> time:
    return (datetime.combine(date.min, start) + timedelta(hours=float(hours))).time()


def hhmm(t: time) -> str:
    return t.strftime("%H:%M")


@dataclass(frozen=True)
class Stay:
    hotel: Hotel
    nights: list[date]

    @property
    def full_days(self) -> list[date]:
        """The days activities can go on: every night but the first is the morning after one, so not arrival day."""
        return self.nights[1:]


def stay_of(s: Session, itinerary: Itinerary) -> Stay:
    nights = sorted({i.day for i in itinerary.items if i.kind == "hotel_night"})
    room_type_id = next(i.room_type_id for i in itinerary.items if i.kind == "hotel_night")
    return Stay(s.get(Hotel, s.get(RoomType, room_type_id).hotel_id), nights)


def _flights(s: Session, items: list[ItineraryItem]) -> list[FlightOut]:
    out = []
    for item in sorted((i for i in items if i.flight_id is not None), key=lambda i: i.kind != "flight_out"):
        f = s.get(Flight, item.flight_id)
        out.append(FlightOut(kind=item.kind, origin=f.origin, destination=f.destination, departure_at=f.departure_at,
                             arrival_at=f.arrival_at, seats=item.quantity, price=item.price))
    return out


def _hotel(s: Session, stay: Stay, items: list[ItineraryItem]) -> HotelOut:
    nights = [i for i in items if i.kind == "hotel_night"]
    rooms = {}
    for item in nights:
        rooms[item.room_type_id] = max(rooms.get(item.room_type_id, 0), item.quantity)
    return HotelOut(
        name=stay.hotel.name, stars=stay.hotel.stars, nights=len(stay.nights),
        rooms=[RoomOut(name=(rt := s.get(RoomType, rid)).name, beds=rt.beds, quantity=q) for rid, q in rooms.items()],
        price=sum(i.price for i in nights))


def _days(s: Session, itinerary: Itinerary, stay: Stay) -> list[DayOut]:
    chosen = {(i.day, i.activity_id): i for i in itinerary.items if i.kind == "activity"}
    offered = s.execute(
        select(Activity, ActivitySlot.day).join(ActivitySlot, ActivitySlot.activity_id == Activity.id)
        .where(Activity.city == stay.hotel.city, ActivitySlot.day.in_(stay.full_days),
               ActivitySlot.spots_left >= itinerary.travelers)).all()
    by_day = defaultdict(dict)
    for a, day in offered:
        by_day[day][a.id] = a
    for day, activity_id in chosen:  # a chosen activity always shows, even once its spots are taken (booked)
        by_day[day].setdefault(activity_id, s.get(Activity, activity_id))

    days = []
    for day in stay.full_days:
        rows = []
        for a in sorted(by_day[day].values(), key=lambda a: (a.start_time, a.id)):
            item = chosen.get((day, a.id))
            price = item.price if item else a.price * itinerary.travelers
            rows.append(ActivityOut(
                activity_id=a.id, name=a.name, start_time=hhmm(a.start_time),
                end_time=hhmm(end_time(a.start_time, a.duration_hours)),
                price_per_person=price / itinerary.travelers, price=price, selected=item is not None))
        days.append(DayOut(day=day, activities=rows))
    return days


def itinerary_details(s: Session, itinerary: Itinerary) -> ItineraryDetails:
    stay = stay_of(s, itinerary)
    return ItineraryDetails(
        itinerary_id=itinerary.id, variant=itinerary.variant, status=itinerary.status, city=stay.hotel.city,
        travelers=itinerary.travelers, start_date=itinerary.start_date, end_date=itinerary.end_date,
        budget=itinerary.budget, total=itinerary.total_cost, flights=_flights(s, itinerary.items),
        hotel=_hotel(s, stay, itinerary.items), days=_days(s, itinerary, stay))


def itinerary_summary(s: Session, itinerary: Itinerary) -> ItinerarySummary:
    stay = stay_of(s, itinerary)
    out = s.get(Flight, next(i.flight_id for i in itinerary.items if i.kind == "flight_out"))
    return ItinerarySummary(
        itinerary_id=itinerary.id, variant=itinerary.variant, status=itinerary.status, city=stay.hotel.city,
        origin=out.origin, destination=out.destination, hotel=stay.hotel.name, hotel_stars=stay.hotel.stars,
        start_date=itinerary.start_date, end_date=itinerary.end_date, travelers=itinerary.travelers,
        total=itinerary.total_cost, budget=itinerary.budget)
