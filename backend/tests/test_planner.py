import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.models import Activity, ActivitySlot, Airport, Flight, RoomAvailability, RoomType
from app.planner.planner import NoSolution, TripRequest, plan
from app.planner.schedule import overlaps
from tests.conftest import TODAY


def request(**changes):
    values = dict(country="Giappone", month=4, nights=5, travelers=2, budget=Decimal("4000"), origin="NAP")
    return TripRequest(**{**values, **changes})


def check_against_catalog(s, proposal, req):
    """Every constraint of docs/design.md §7, verified against the database."""
    out, back = proposal.outbound, proposal.inbound
    assert proposal.total <= req.budget
    assert proposal.total == out.total + back.total + proposal.hotel.total + sum(
        a.total for d in proposal.days for a in d.chosen)

    japan = set(s.scalars(select(Airport.iata).where(Airport.country == "Giappone")))
    assert out.origin == req.origin and out.destination in japan
    assert back.origin == out.destination and back.destination == req.origin
    assert out.departure_at.month == req.month and out.departure_at.date() > TODAY
    assert back.departure_at.date() - out.departure_at.date() == timedelta(days=req.nights)
    for leg in (out, back):
        assert s.get(Flight, leg.flight_id).seats_left >= req.travelers

    hotel = proposal.hotel
    nights = [hotel.check_in + timedelta(days=i) for i in range((hotel.check_out - hotel.check_in).days)]
    assert hotel.check_in == out.arrival_at.date() and hotel.check_out == back.departure_at.date()
    assert sum(r.option.beds * r.quantity for r in hotel.rooms) >= req.travelers
    for room in hotel.rooms:
        assert s.get(RoomType, room.option.room_type_id).hotel_id == hotel.hotel_id
        for night in nights:
            row = s.get(RoomAvailability, (room.option.room_type_id, night))
            assert row is not None and row.rooms_left >= room.quantity

    full_days = nights[1:]
    used = []
    for day in proposal.days:
        assert day.day in full_days
        assert len(day.chosen) <= 2
        assert not any(overlaps(a, b) for i, a in enumerate(day.chosen) for b in day.chosen[i + 1:])
        for a in day.chosen:
            assert s.get(Activity, a.activity_id).city == hotel.city
            assert s.get(ActivitySlot, (a.activity_id, day.day)).spots_left >= req.travelers
            used.append(a.activity_id)
    assert len(used) == len(set(used))


def test_proposals_respect_every_constraint(japan):
    rng = random.Random(7)
    for _ in range(15):
        req = request(nights=rng.randint(2, 7), travelers=rng.randint(1, 6),
                      budget=Decimal(rng.randrange(1500, 9000, 100)), origin=rng.choice(["NAP", "FCO", "MXP"]))
        result = plan(japan, req, today=TODAY)
        if isinstance(result, NoSolution):
            continue
        for proposal in result:
            check_against_catalog(japan, proposal, req)


def test_three_variants_with_different_hotels(japan):
    result = plan(japan, request(budget=Decimal("6000")), today=TODAY)
    assert [p.variant for p in result] == ["Economica", "Bilanciata", "Comfort"]
    assert len({p.hotel.hotel_id for p in result}) == 3
    cheapest = min(result, key=lambda p: p.total - sum(a.total for d in p.days for a in d.chosen))
    assert cheapest.variant == "Economica"
    assert max(p.hotel.stars for p in result) == result[2].hotel.stars


def test_budget_too_low_gives_no_solution_with_the_minimum_cost(japan):
    result = plan(japan, request(budget=Decimal("300")), today=TODAY)
    assert isinstance(result, NoSolution)
    assert result.reason == "over_budget"
    assert result.minimum_cost > Decimal("300")


def test_month_without_flights_gives_no_solution(japan):
    result = plan(japan, request(month=9), today=TODAY)
    assert isinstance(result, NoSolution) and result.reason == "no_flights"


def test_only_the_requested_categories_are_chosen(japan):
    result = plan(japan, request(budget=Decimal("8000"), categories=("food", "culture")), today=TODAY)
    for proposal in result:
        chosen = [a.activity_id for d in proposal.days for a in d.chosen]
        assert chosen and {japan.get(Activity, i).category for i in chosen} <= {"food", "culture"}
        others = [a.activity_id for d in proposal.days for a in d.alternatives]
        assert any(japan.get(Activity, i).category not in ("food", "culture") for i in others)  # still offered


def test_without_categories_any_activity_can_be_chosen(japan):
    result = plan(japan, request(budget=Decimal("8000")), today=TODAY)
    chosen = {japan.get(Activity, a.activity_id).category for d in result[0].days for a in d.chosen}
    assert len(chosen) > 2
