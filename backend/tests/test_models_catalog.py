from datetime import date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Activity, ActivitySlot, Airport, Flight, Hotel, RoomAvailability, RoomType


def make_airports(s):
    s.add_all([
        Airport(iata="NAP", city="Napoli", country="Italia"),
        Airport(iata="KIX", city="Osaka", country="Giappone"),
    ])
    s.flush()


def test_flight_price_is_decimal(db_session):
    make_airports(db_session)
    f = Flight(origin="NAP", destination="KIX", departure_at=datetime(2027, 4, 3, 10),
               arrival_at=datetime(2027, 4, 4, 8), price=Decimal("612.40"), seats_left=20)
    db_session.add(f)
    db_session.flush()
    db_session.refresh(f)
    assert f.price == Decimal("612.40")


def make_room_type(s, beds=3, name="Tripla"):
    h = Hotel(name="Ryokan Sakura", city="Kyoto", country="Giappone", stars=3, description="…")
    s.add(h)
    s.flush()
    rt = RoomType(hotel_id=h.id, name=name, beds=beds)
    s.add(rt)
    s.flush()
    return rt


def test_room_type_has_beds(db_session):
    rt = make_room_type(db_session, beds=4, name="Familiare")
    db_session.refresh(rt)
    assert (rt.name, rt.beds) == ("Familiare", 4)


def test_room_type_name_is_unique_per_hotel(db_session):
    rt = make_room_type(db_session)
    db_session.add(RoomType(hotel_id=rt.hotel_id, name="Tripla", beds=3))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_room_night_is_unique(db_session):
    rt = make_room_type(db_session)
    db_session.add(RoomAvailability(room_type_id=rt.id, night=date(2027, 4, 3), price=Decimal("150"), rooms_left=2))
    db_session.flush()
    db_session.add(RoomAvailability(room_type_id=rt.id, night=date(2027, 4, 3), price=Decimal("99"), rooms_left=1))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_activity_slot_belongs_to_activity(db_session):
    a = Activity(name="Fushimi Inari all'alba", city="Kyoto", country="Giappone", category="culture",
                 target="couples", price=Decimal("25.00"), duration_hours=Decimal("3"), start_time=time(5,30), description="…")
    db_session.add(a)
    db_session.flush()
    db_session.add(ActivitySlot(activity_id=a.id, day=date(2027, 4, 4), spots_left=10))
    db_session.flush()
    assert db_session.get(ActivitySlot, (a.id, date(2027, 4, 4))).spots_left == 10


def test_sessions_are_isolated(db_session):
    # the fixture rolls back, so airports created by other tests are not here
    assert db_session.query(Airport).count() == 0