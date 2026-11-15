from datetime import date
from decimal import Decimal
from pathlib import Path

from seed.build_catalog import build_catalog, season_factor
from seed.schema import load_base_data

BASE = load_base_data(Path(__file__).resolve().parents[1] / "seed" / "data")
START = date(2026, 11, 15)


def test_same_seed_same_catalog():
    a, b = build_catalog(BASE, START, days=30), build_catalog(BASE, START, days=30)
    assert a.flights == b.flights and a.room_availability == b.room_availability


def test_season_factor():
    assert season_factor(date(2027, 8, 1)) == Decimal("1.40")
    assert season_factor(date(2027, 2, 1)) == Decimal("0.90")


def test_no_flights_on_tuesday_and_both_directions():
    c = build_catalog(BASE, START, days=14)
    assert all(f["departure_at"].weekday() != 1 for f in c.flights)
    pairs = {(f["origin"], f["destination"]) for f in c.flights}
    assert ("NAP", "KIX") in pairs and ("KIX", "NAP") in pairs


def test_prices_have_two_decimals():
    c = build_catalog(BASE, START, days=7)
    for row in c.flights + c.room_availability:
        assert isinstance(row["price"], Decimal) and row["price"] == row["price"].quantize(Decimal("0.01"))


def test_room_types_follow_stars():
    c = build_catalog(BASE, START, days=1)
    for i, hotel in enumerate(BASE.hotels):
        rooms = {rt["name"]: rt["beds"] for rt in c.room_types if rt["hotel_index"] == i}
        assert rooms["Singola"] == 1 and rooms["Doppia"] == 2
        if hotel.stars >= 3:
            assert rooms["Tripla"] == 3 and rooms["Familiare"] == 4
        else:
            assert "Tripla" not in rooms and "Familiare" not in rooms


def test_every_room_type_has_every_night():
    c = build_catalog(BASE, START, days=10)
    assert len(c.room_availability) == len(c.room_types) * 10


def test_single_room_costs_less_than_double():
    c = build_catalog(BASE, START, days=1)
    night = {r["room_type_index"]: r["price"] for r in c.room_availability}
    first_hotel = [i for i, rt in enumerate(c.room_types) if rt["hotel_index"] == 0]
    by_name = {c.room_types[i]["name"]: night[i] for i in first_hotel}
    assert by_name["Singola"] < by_name["Doppia"]


def test_activity_slots_follow_weekdays():
    c = build_catalog(BASE, START, days=14)
    for slot in c.activity_slots:
        assert slot["day"].weekday() in BASE.activities[slot["activity_index"]].weekdays