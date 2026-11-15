from datetime import date
from pathlib import Path

from app.db.models import Airport, Flight, Hotel, RoomAvailability, RoomType
from seed.build_catalog import build_catalog
from seed.load_db import load_catalog
from seed.schema import load_base_data

BASE = load_base_data(Path(__file__).resolve().parents[1] / "seed" / "data")
CAT = build_catalog(BASE, date(2026, 11, 15), days=5)


def test_load_catalog_inserts_everything(db_session):
    assert load_catalog(db_session, CAT, BASE) is True
    assert db_session.query(Airport).count() == len(BASE.airports)
    assert db_session.query(Flight).count() == len(CAT.flights)
    assert db_session.query(RoomType).count() == len(CAT.room_types)
    assert db_session.query(RoomAvailability).count() == len(CAT.room_availability)


def test_room_availability_points_to_the_right_room(db_session):
    load_catalog(db_session, CAT, BASE)
    row = CAT.room_availability[0]
    room = CAT.room_types[row["room_type_index"]]
    hotel = db_session.query(Hotel).filter_by(name=BASE.hotels[room["hotel_index"]].name).one()
    rt = db_session.query(RoomType).filter_by(hotel_id=hotel.id, name=room["name"]).one()
    assert db_session.get(RoomAvailability, (rt.id, row["night"])).price == row["price"]


def test_second_load_does_nothing(db_session):
    load_catalog(db_session, CAT, BASE)
    flights = db_session.query(Flight).count()
    assert load_catalog(db_session, CAT, BASE) is False
    assert db_session.query(Flight).count() == flights