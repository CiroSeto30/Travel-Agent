"""Itinerary planner: pure Python on the catalog, no LLM (docs/design.md §7).

Every proposal it returns is within budget, covers every night and uses only what is available on its date.
"""

import calendar
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity, ActivitySlot, Airport, Flight, Hotel, RoomAvailability, RoomType
from app.planner.rooms import RoomOption, RoomPick, cheapest_rooms
from app.planner.schedule import Slot, choose_activities, overlaps

FLIGHT_PAIRS_PER_AIRPORT = 2
FLIGHT_PAIRS = 6


@dataclass(frozen=True)
class TripRequest:
    country: str
    month: int
    nights: int
    travelers: int
    budget: Decimal  # for the whole group
    origin: str  # departure airport
    preferences: str = ""  # in the user's words, for the RAG ranking
    categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlightLeg:
    flight_id: int
    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    unit_price: Decimal  # one seat
    total: Decimal


@dataclass(frozen=True)
class HotelStay:
    hotel_id: int
    name: str
    stars: int
    city: str
    check_in: date
    check_out: date
    rooms: tuple[RoomPick, ...]
    total: Decimal


@dataclass(frozen=True)
class PlannedActivity(Slot):
    total: Decimal = Decimal("0")


@dataclass(frozen=True)
class PlannedDay:
    day: date
    chosen: tuple[PlannedActivity, ...]
    alternatives: tuple[PlannedActivity, ...]  # the other activities available that day for the group


@dataclass(frozen=True)
class Proposal:
    variant: str
    travelers: int
    budget: Decimal
    outbound: FlightLeg
    inbound: FlightLeg
    hotel: HotelStay
    days: tuple[PlannedDay, ...]
    total: Decimal


@dataclass(frozen=True)
class NoSolution:
    reason: str  # "unknown_country", "no_flights", "no_hotel", "over_budget"
    minimum_cost: Decimal | None = None  # cheapest flights + hotel found, when the budget is the problem


# activities of a city, request → activity ids from the most relevant; feat/rag passes a semantic ranker
Ranker = Callable[[list[Activity], TripRequest], list[int]]


def rank_by_category(activities: list[Activity], req: TripRequest) -> list[int]:
    return [a.id for a in sorted(activities, key=lambda a: (a.category not in req.categories, a.id))]


@dataclass
class _Candidate:
    outbound: FlightLeg
    inbound: FlightLeg
    hotel: HotelStay
    fixed: Decimal = field(init=False)  # flights + hotel

    def __post_init__(self) -> None:
        self.fixed = self.outbound.total + self.inbound.total + self.hotel.total


def _travel_window(month: int, today: date) -> tuple[date, date]:
    """First and last departure day: the next occurrence of the month, from tomorrow on."""
    tomorrow = today + timedelta(days=1)
    year = today.year
    if date(year, month, calendar.monthrange(year, month)[1]) < tomorrow:
        year += 1
    return max(date(year, month, 1), tomorrow), date(year, month, calendar.monthrange(year, month)[1])


def _leg(flight: Flight, travelers: int) -> FlightLeg:
    return FlightLeg(flight.id, flight.origin, flight.destination, flight.departure_at, flight.arrival_at,
                     flight.price, flight.price * travelers)


def _flight_pairs(s: Session, req: TripRequest, airports: list[str], first: date, last: date):
    """The cheapest outbound + return pairs with enough seats, a few per destination airport."""
    def in_range(start: date, end: date):
        return Flight.departure_at >= datetime.combine(start, time()), \
            Flight.departure_at < datetime.combine(end + timedelta(days=1), time())

    outbound = s.scalars(select(Flight).where(
        Flight.origin == req.origin, Flight.destination.in_(airports), Flight.seats_left >= req.travelers,
        *in_range(first, last)))
    back = defaultdict(list)
    for f in s.scalars(select(Flight).where(
            Flight.origin.in_(airports), Flight.destination == req.origin, Flight.seats_left >= req.travelers,
            *in_range(first + timedelta(days=req.nights), last + timedelta(days=req.nights)))):
        back[(f.origin, f.departure_at.date())].append(f)

    pairs = defaultdict(list)
    for out in outbound:
        returns = back.get((out.destination, out.departure_at.date() + timedelta(days=req.nights)))
        if returns:
            ret = min(returns, key=lambda f: f.price)
            pairs[out.destination].append((_leg(out, req.travelers), _leg(ret, req.travelers)))
    best = [p for options in pairs.values()
            for p in sorted(options, key=lambda p: p[0].total + p[1].total)[:FLIGHT_PAIRS_PER_AIRPORT]]
    return sorted(best, key=lambda p: p[0].total + p[1].total)[:FLIGHT_PAIRS]


def _hotel_stays(s: Session, city: str, check_in: date, check_out: date, travelers: int) -> list[HotelStay]:
    nights = (check_out - check_in).days
    rows = s.execute(
        select(Hotel, RoomType, RoomAvailability)
        .join(RoomType, RoomType.hotel_id == Hotel.id)
        .join(RoomAvailability, RoomAvailability.room_type_id == RoomType.id)
        .where(Hotel.city == city, RoomAvailability.night >= check_in, RoomAvailability.night < check_out)
        .order_by(Hotel.id, RoomType.id, RoomAvailability.night))
    by_type = defaultdict(list)
    hotels, types = {}, {}
    for hotel, room_type, row in rows:
        hotels[hotel.id], types[room_type.id] = hotel, room_type
        by_type[(hotel.id, room_type.id)].append(row)

    options = defaultdict(list)
    for (hotel_id, type_id), night_rows in by_type.items():
        if len(night_rows) == nights:  # free on every night of the stay
            room_type = types[type_id]
            options[hotel_id].append(RoomOption(
                room_type_id=type_id, name=room_type.name, beds=room_type.beds,
                available=min(r.rooms_left for r in night_rows), cost=sum(r.price for r in night_rows),
                nightly=tuple((r.night, r.price) for r in night_rows)))

    stays = []
    for hotel_id, hotel_options in options.items():
        rooms = cheapest_rooms(hotel_options, travelers)
        if rooms:
            hotel = hotels[hotel_id]
            stays.append(HotelStay(hotel_id, hotel.name, hotel.stars, city, check_in, check_out, tuple(rooms),
                                   sum(r.option.cost * r.quantity for r in rooms)))
    return stays


def _choose_variants(candidates: list[_Candidate], budget: Decimal) -> list[tuple[str, _Candidate]]:
    """Up to three itineraries with different hotels: cheapest, balanced, best hotel."""
    cheapest = min(candidates, key=lambda c: (c.fixed, -c.hotel.stars))
    others = [c for c in candidates if c.hotel.hotel_id != cheapest.hotel.hotel_id]
    comfort = max(others, key=lambda c: (c.hotel.stars, -c.fixed), default=None)
    used = {cheapest.hotel.hotel_id} | ({comfort.hotel.hotel_id} if comfort else set())
    rest = [c for c in candidates if c.hotel.hotel_id not in used]
    # balanced: hotel quality and money left count the same
    balanced = max(rest, key=lambda c: c.hotel.stars / 5 - float(c.fixed / budget), default=None)
    chosen = [("Economica", cheapest), ("Bilanciata", balanced), ("Comfort", comfort)]
    return [(name, c) for name, c in chosen if c is not None]


def _planned(slot: Slot, travelers: int) -> PlannedActivity:
    return PlannedActivity(slot.activity_id, slot.name, slot.start, slot.end, slot.unit_price,
                           total=slot.unit_price * travelers)


def _end(start: time, hours: Decimal) -> time:
    return (datetime.combine(date.min, start) + timedelta(hours=float(hours))).time()


def _activity_days(s: Session, c: _Candidate, req: TripRequest, rank: Ranker) -> tuple[PlannedDay, ...]:
    full_days = [c.hotel.check_in + timedelta(days=i) for i in range(1, (c.hotel.check_out - c.hotel.check_in).days)]
    rows = s.execute(
        select(Activity, ActivitySlot.day).join(ActivitySlot, ActivitySlot.activity_id == Activity.id)
        .where(Activity.city == c.hotel.city, ActivitySlot.day.in_(full_days),
               ActivitySlot.spots_left >= req.travelers)).all()
    activities = {a.id: a for a, _ in rows}
    offered = {day: [] for day in full_days}
    for a, day in rows:
        offered[day].append(Slot(a.id, a.name, a.start_time, _end(a.start_time, a.duration_hours), a.price))

    # with categories, the planner picks only what was asked for; the rest stays on offer in the panel
    wanted = {i for i, a in activities.items() if not req.categories or a.category in req.categories}
    candidates = {day: [sl for sl in slots if sl.activity_id in wanted] for day, slots in offered.items()}
    chosen = choose_activities(candidates, rank(list(activities.values()), req), req.travelers,
                               req.budget - c.fixed)
    picked = {slot.activity_id for slots in chosen.values() for slot in slots}
    return tuple(
        PlannedDay(
            day=day,
            chosen=tuple(_planned(sl, req.travelers) for sl in chosen[day]),
            alternatives=tuple(_planned(sl, req.travelers)
                               for sl in sorted(offered[day], key=lambda sl: sl.start) if sl.activity_id not in picked),
        )
        for day in full_days)


def _check(p: Proposal, req: TripRequest) -> None:
    """Last line of defence: a broken proposal is a bug, never something to show."""
    assert p.total <= req.budget, "over budget"
    assert p.inbound.departure_at.date() - p.outbound.departure_at.date() == timedelta(days=req.nights)
    assert sum(r.option.beds * r.quantity for r in p.hotel.rooms) >= req.travelers, "not enough beds"
    for day in p.days:
        assert not any(overlaps(a, b) for i, a in enumerate(day.chosen) for b in day.chosen[i + 1:])


def plan(s: Session, req: TripRequest, *, today: date, rank: Ranker = rank_by_category) -> list[Proposal] | NoSolution:
    airports = {a.iata: a.city for a in s.scalars(
        select(Airport).where(Airport.country == req.country, Airport.is_departure.is_(False)))}
    if not airports:
        return NoSolution("unknown_country")

    first, last = _travel_window(req.month, today)
    pairs = _flight_pairs(s, req, list(airports), first, last)
    if not pairs:
        return NoSolution("no_flights")

    candidates, cheapest = [], None
    for out, back in pairs:
        check_in, check_out = out.arrival_at.date(), back.departure_at.date()
        if check_out <= check_in:
            continue
        for stay in _hotel_stays(s, airports[out.destination], check_in, check_out, req.travelers):
            candidate = _Candidate(out, back, stay)
            cheapest = candidate.fixed if cheapest is None else min(cheapest, candidate.fixed)
            if candidate.fixed <= req.budget:
                candidates.append(candidate)
    if not candidates:
        return NoSolution("over_budget", cheapest) if cheapest is not None else NoSolution("no_hotel")

    proposals = []
    for variant, c in _choose_variants(candidates, req.budget):
        days = _activity_days(s, c, req, rank)
        total = c.fixed + sum(a.total for d in days for a in d.chosen)
        proposal = Proposal(variant, req.travelers, req.budget, c.outbound, c.inbound, c.hotel, days, total)
        _check(proposal, req)
        proposals.append(proposal)
    return proposals