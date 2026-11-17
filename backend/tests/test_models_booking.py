from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Airport, Booking, Flight, Itinerary, ItineraryItem, User


@pytest.fixture
def user(db_session):
    db_session.add(Airport(iata="NAP", city="Napoli", country="Italia"))
    u = User(email="ciro@example.com", password_hash="x", first_name="Ciro", last_name="Setolino")
    db_session.add(u)
    db_session.flush()
    return u


def new_itinerary(s, user):
    it = Itinerary(user_id=user.id, variant="bilanciata", travelers=2, budget=Decimal("2000.00"), total_cost=Decimal("1860.00"),
                   start_date=date(2027, 4, 3), end_date=date(2027, 4, 9))
    s.add(it)
    s.flush()
    return it


def test_email_is_unique(db_session, user):
    db_session.add(User(email="ciro@example.com", password_hash="y", first_name="Mario", last_name="Rossi"))
    with pytest.raises(IntegrityError):
        db_session.flush()

def test_last_name_is_required(db_session, user):
    db_session.add(User(email="mario@example.com", password_hash="y", first_name="Mario"))
    with pytest.raises(IntegrityError):
        db_session.flush()

def test_new_itinerary_is_proposed(db_session, user):
    assert new_itinerary(db_session, user).status == "proposed"


def test_item_needs_exactly_one_reference(db_session, user):
    it = new_itinerary(db_session, user)
    db_session.add(ItineraryItem(itinerary_id=it.id, kind="activity", day=date(2027, 4, 4), price=Decimal("25")))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_unknown_status_is_rejected(db_session, user):
    it = new_itinerary(db_session, user)
    it.status = "paid"
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_one_booking_per_itinerary(db_session, user):
    it = new_itinerary(db_session, user)
    db_session.add(Booking(user_id=user.id, itinerary_id=it.id, total_cost=it.total_cost))
    db_session.flush()
    db_session.add(Booking(user_id=user.id, itinerary_id=it.id, total_cost=it.total_cost))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("travelers", [0, 7])
def test_travelers_must_be_between_one_and_six(db_session, user, travelers):
    it = new_itinerary(db_session, user)
    it.travelers = travelers
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_item_quantity_must_be_positive(db_session, user):
    db_session.add(Airport(iata="KIX", city="Osaka", country="Giappone"))
    flight = Flight(origin="NAP", destination="KIX", departure_at=datetime(2027, 4, 3, 10),
                    arrival_at=datetime(2027, 4, 4, 8), price=Decimal("600"), seats_left=20)
    db_session.add(flight)
    it = new_itinerary(db_session, user)
    db_session.add(ItineraryItem(itinerary_id=it.id, kind="flight_out", flight_id=flight.id,
                                 quantity=0, day=date(2027, 4, 3), price=Decimal("0")))
    with pytest.raises(IntegrityError):
        db_session.flush()