import threading
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.booking.service import BookingError, book_itinerary
from app.db.models import (Activity, ActivitySlot, Airport, Booking, Flight, Hotel, Itinerary, ItineraryItem,
                           RoomAvailability, RoomType, User)

CHECK_IN = date(2027, 4, 11)
NIGHTS = [CHECK_IN + timedelta(days=i) for i in range(4)]
ACTIVITY_DAY = date(2027, 4, 12)


def add_catalog(s, *, seats=10, rooms=4, spots=10):
    """One route, one hotel with one room type, one activity: just enough to book."""
    s.add_all([Airport(iata="NAP", city="Napoli", country="Italia", is_departure=True),
               Airport(iata="HND", city="Tokyo", country="Giappone")])
    out = Flight(origin="NAP", destination="HND", departure_at=datetime(2027, 4, 10, 15),
                 arrival_at=datetime(2027, 4, 11, 9), price=Decimal("500"), seats_left=seats)
    back = Flight(origin="HND", destination="NAP", departure_at=datetime(2027, 4, 15, 11),
                  arrival_at=datetime(2027, 4, 15, 20), price=Decimal("450"), seats_left=seats)
    hotel = Hotel(name="Hotel Prova", city="Tokyo", country="Giappone", stars=3, description="")
    s.add_all([out, back, hotel])
    s.flush()
    room = RoomType(hotel_id=hotel.id, name="Doppia", beds=2)
    activity = Activity(name="Onsen", city="Tokyo", country="Giappone", category="relax", target="couples",
                        price=Decimal("40"), duration_hours=Decimal("2"), start_time=time(10), description="")
    s.add_all([room, activity])
    s.flush()
    s.add_all([RoomAvailability(room_type_id=room.id, night=n, price=Decimal("100"), rooms_left=rooms) for n in NIGHTS])
    s.add(ActivitySlot(activity_id=activity.id, day=ACTIVITY_DAY, spots_left=spots))
    s.flush()
    return {"out": out.id, "back": back.id, "room": room.id, "activity": activity.id}


def add_user(s, name="ciro"):
    user = User(email=f"{name}@example.com", password_hash="x", first_name=name, last_name="Prova")
    s.add(user)
    s.flush()
    return user.id


def add_itinerary(s, catalog, user_id, *, travelers=2, rooms=1, set_id=None, variant="Bilanciata"):
    items = [
        ItineraryItem(kind="flight_out", flight_id=catalog["out"], quantity=travelers, day=date(2027, 4, 10),
                      price=Decimal("500") * travelers),
        ItineraryItem(kind="flight_return", flight_id=catalog["back"], quantity=travelers, day=date(2027, 4, 15),
                      price=Decimal("450") * travelers),
        *[ItineraryItem(kind="hotel_night", room_type_id=catalog["room"], quantity=rooms, day=n,
                        price=Decimal("100") * rooms) for n in NIGHTS],
        ItineraryItem(kind="activity", activity_id=catalog["activity"], quantity=travelers, day=ACTIVITY_DAY,
                      price=Decimal("40") * travelers),
    ]
    itinerary = Itinerary(user_id=user_id, proposal_set_id=set_id or str(uuid.uuid4()), variant=variant,
                          travelers=travelers, budget=Decimal("10000"), total_cost=sum(i.price for i in items),
                          start_date=date(2027, 4, 10), end_date=date(2027, 4, 15), items=items)
    s.add(itinerary)
    s.flush()
    return itinerary.id


def left(s, catalog):
    s.expire_all()
    return (s.get(Flight, catalog["out"]).seats_left, s.get(Flight, catalog["back"]).seats_left,
            [s.get(RoomAvailability, (catalog["room"], n)).rooms_left for n in NIGHTS],
            s.get(ActivitySlot, (catalog["activity"], ACTIVITY_DAY)).spots_left)


# --- one booking at a time -------------------------------------------------------------------------------------

def test_booking_takes_seats_rooms_and_spots(db_session):
    s = db_session
    catalog = add_catalog(s)
    user = add_user(s)
    set_id = str(uuid.uuid4())
    chosen = add_itinerary(s, catalog, user, travelers=3, rooms=2, set_id=set_id)
    sibling = add_itinerary(s, catalog, user, set_id=set_id, variant="Economica")

    booking = book_itinerary(s, user_id=user, itinerary_id=chosen)

    assert left(s, catalog) == (7, 7, [2, 2, 2, 2], 7)
    itinerary = s.get(Itinerary, chosen)
    assert itinerary.status == "booked"
    assert (booking.user_id, booking.itinerary_id, booking.status) == (user, chosen, "confirmed")
    assert booking.total_cost == itinerary.total_cost == Decimal("3770")  # 1500 + 1350 + 4 × 200 + 120
    other = s.get(Itinerary, sibling)
    assert (other.status, other.superseded_by) == ("superseded", chosen)


def test_booking_again_returns_the_same_booking(db_session):
    s = db_session
    catalog = add_catalog(s)
    user = add_user(s)
    itinerary = add_itinerary(s, catalog, user)

    first = book_itinerary(s, user_id=user, itinerary_id=itinerary)
    second = book_itinerary(s, user_id=user, itinerary_id=itinerary)

    assert first.id == second.id
    assert left(s, catalog) == (8, 8, [3, 3, 3, 3], 8)  # taken once


@pytest.mark.parametrize("whose", ["missing", "someone else"])
def test_only_your_own_itinerary_can_be_booked(db_session, whose):
    s = db_session
    catalog = add_catalog(s)
    owner = add_user(s)
    itinerary = add_itinerary(s, catalog, owner)
    other = add_user(s, "mario")

    with pytest.raises(BookingError) as e:
        if whose == "missing":
            book_itinerary(s, user_id=owner, itinerary_id=itinerary + 1000)
        else:
            book_itinerary(s, user_id=other, itinerary_id=itinerary)
    assert e.value.code == "not_found"


def test_a_superseded_proposal_cannot_be_booked(db_session):
    s = db_session
    catalog = add_catalog(s)
    user = add_user(s)
    set_id = str(uuid.uuid4())
    first = add_itinerary(s, catalog, user, set_id=set_id)
    second = add_itinerary(s, catalog, user, set_id=set_id)
    book_itinerary(s, user_id=user, itinerary_id=first)

    with pytest.raises(BookingError) as e:
        book_itinerary(s, user_id=user, itinerary_id=second)
    assert e.value.code == "not_bookable"


@pytest.mark.parametrize("missing", ["seats", "room", "spots"])
def test_one_unavailable_item_books_nothing(db_session, missing):
    s = db_session
    catalog = add_catalog(s)
    user = add_user(s)
    itinerary = add_itinerary(s, catalog, user)
    if missing == "seats":
        s.get(Flight, catalog["back"]).seats_left = 1
    elif missing == "room":
        s.get(RoomAvailability, (catalog["room"], NIGHTS[2])).rooms_left = 0
    else:
        s.delete(s.get(ActivitySlot, (catalog["activity"], ACTIVITY_DAY)))
    s.flush()
    before = left(s, catalog) if missing != "spots" else None

    savepoint = s.begin_nested()  # stands in for the caller's transaction, which rolls back on error
    with pytest.raises(BookingError) as e:
        book_itinerary(s, user_id=user, itinerary_id=itinerary)
    savepoint.rollback()

    assert e.value.code == "unavailable"
    assert e.value.item  # says which item, so the agent can explain what changed
    assert s.get(Itinerary, itinerary).status == "proposed"
    assert s.scalar(select(func.count()).select_from(Booking)) == 0
    if before is not None:
        assert left(s, catalog) == before


# --- two bookings at the same time ----------------------------------------------------------------------------
# These need committed data, seen by several connections at once: no rollback-per-test session here.

@pytest.fixture
def shared(test_engine):
    Session = sessionmaker(test_engine, expire_on_commit=False)
    with Session() as s:
        catalog = add_catalog(s)
        s.commit()
    yield Session, catalog
    with test_engine.begin() as conn:
        tables = ", ".join(t.name for t in reversed(Itinerary.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def book_in_thread(Session, user_id, itinerary_id, results):
    def run():
        with Session() as s:
            try:
                results.append(book_itinerary(s, user_id=user_id, itinerary_id=itinerary_id).id)
                s.commit()
            except BookingError as e:
                s.rollback()
                results.append(e.code)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def held_booking(Session, user_id, itinerary_id):
    """A booking done but not committed yet: its transaction keeps the locks."""
    s = Session()
    book_itinerary(s, user_id=user_id, itinerary_id=itinerary_id)
    return s


def race(Session, first, second):
    """`first` books and holds its transaction; `second` must wait for it, then sees what `first` left."""
    holder = held_booking(Session, *first)
    results = []
    thread = book_in_thread(Session, *second, results)
    thread.join(timeout=1)
    waited = thread.is_alive()
    holder.commit()
    holder.close()
    thread.join(timeout=10)
    return waited, results


def test_two_bookings_for_the_last_room_only_one_succeeds(shared):
    Session, catalog = shared
    with Session() as s:
        s.get(RoomAvailability, (catalog["room"], NIGHTS[1])).rooms_left = 1
        a, b = add_user(s, "anna"), add_user(s, "bruno")
        first, second = add_itinerary(s, catalog, a), add_itinerary(s, catalog, b)
        s.commit()

    waited, results = race(Session, (a, first), (b, second))

    assert waited, "the second booking did not wait for the lock"
    assert results == ["unavailable"]
    with Session() as s:
        assert s.get(RoomAvailability, (catalog["room"], NIGHTS[1])).rooms_left == 0
        assert s.scalar(select(func.count()).select_from(Booking)) == 1


def test_two_groups_of_three_for_four_seats_only_one_succeeds(shared):
    Session, catalog = shared
    with Session() as s:
        s.get(Flight, catalog["out"]).seats_left = 4
        a, b = add_user(s, "anna"), add_user(s, "bruno")
        first = add_itinerary(s, catalog, a, travelers=3, rooms=2)
        second = add_itinerary(s, catalog, b, travelers=3, rooms=2)
        s.commit()

    waited, results = race(Session, (a, first), (b, second))

    assert waited and results == ["unavailable"]
    with Session() as s:
        assert s.get(Flight, catalog["out"]).seats_left == 1


def test_two_sibling_proposals_at_once_only_one_is_booked(shared):
    Session, catalog = shared
    with Session() as s:
        user = add_user(s)
        set_id = str(uuid.uuid4())
        first, second = add_itinerary(s, catalog, user, set_id=set_id), add_itinerary(s, catalog, user, set_id=set_id)
        s.commit()

    waited, results = race(Session, (user, first), (user, second))

    assert waited and results == ["not_bookable"]
    with Session() as s:
        assert [s.get(Itinerary, i).status for i in (first, second)] == ["booked", "superseded"]


def test_a_double_click_books_once(shared):
    Session, catalog = shared
    with Session() as s:
        user = add_user(s)
        itinerary = add_itinerary(s, catalog, user)
        s.commit()

    waited, results = race(Session, (user, itinerary), (user, itinerary))

    with Session() as s:
        [booking_id] = s.scalars(select(Booking.id))
        assert waited and results == [booking_id]
        assert s.get(Flight, catalog["out"]).seats_left == 8


def test_many_bookings_at_once_never_oversell(shared):
    Session, catalog = shared
    with Session() as s:
        s.get(Flight, catalog["out"]).seats_left = 5
        users = [add_user(s, f"u{i}") for i in range(6)]
        itineraries = [add_itinerary(s, catalog, u, travelers=2) for u in users]
        s.commit()

    results = []
    threads = [book_in_thread(Session, u, i, results) for u, i in zip(users, itineraries)]
    for t in threads:
        t.join(timeout=20)

    assert sorted(r for r in results if isinstance(r, str)) == ["unavailable"] * 4  # 5 seats: 2 groups of 2
    with Session() as s:
        assert s.get(Flight, catalog["out"]).seats_left == 1
