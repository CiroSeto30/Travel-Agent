from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.booking.service import book_itinerary
from app.db.models import Activity, Itinerary
from app.planner.planner import TripRequest, plan
from app.planner.store import save_proposals
from tests.conftest import TODAY


def login(client, name="ciro"):
    client.cookies.clear()
    r = client.post("/api/auth/register", json={"email": f"{name}@example.com", "password": "password123",
                                                "first_name": name, "last_name": "Prova"})
    assert r.status_code == 201
    return r.json()["id"]


@pytest.fixture
def trip(client, japan):
    """A user logged in with three saved proposals for Japan in April."""
    user_id = login(client)
    req = TripRequest(country="Giappone", month=4, nights=5, travelers=2, budget=Decimal("6000"), origin="NAP")
    saved = save_proposals(japan, user_id=user_id, conversation_id=None, request=req,
                           proposals=plan(japan, req, today=TODAY))
    return user_id, [it.id for it in saved]


def minutes(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def overlap(a, b):
    return minutes(a["start_time"]) < minutes(b["end_time"]) + 30 and minutes(b["start_time"]) < minutes(a["end_time"]) + 30


def selection_of(details):
    return [{"day": d["day"], "activity_id": a["activity_id"]} for d in details["days"] for a in d["activities"]
            if a["selected"]]


def fixed_cost(details):
    return sum(Decimal(f["price"]) for f in details["flights"]) + Decimal(details["hotel"]["price"])


# --- GET /api/itineraries/{id} --------------------------------------------------------------------------------

def test_details_match_the_saved_itinerary(client, japan, trip):
    _, [first, *_] = trip
    it = japan.get(Itinerary, first)
    details = client.get(f"/api/itineraries/{first}").json()

    assert (details["itinerary_id"], details["variant"], details["status"]) == (first, it.variant, "proposed")
    assert Decimal(details["total"]) == it.total_cost == sum(i.price for i in it.items)
    assert Decimal(details["budget"]) == Decimal("6000")
    chosen = sum(Decimal(a["price"]) for d in details["days"] for a in d["activities"] if a["selected"])
    assert fixed_cost(details) + chosen == it.total_cost

    out, back = details["flights"]
    assert (out["kind"], back["kind"]) == ("flight_out", "flight_return")
    assert out["origin"] == back["destination"] == "NAP" and out["seats"] == 2
    hotel_nights = sorted({i.day for i in it.items if i.kind == "hotel_night"})
    assert details["hotel"]["nights"] == len(hotel_nights)
    assert [d["day"] for d in details["days"]] == [n.isoformat() for n in hotel_nights[1:]]  # full days only

    activity_items = {(i.day.isoformat(), i.activity_id) for i in it.items if i.kind == "activity"}
    assert {(s["day"], s["activity_id"]) for s in selection_of(details)} == activity_items
    for day in details["days"]:
        starts = [a["start_time"] for a in day["activities"]]
        assert starts == sorted(starts) and all(len(s) == 5 for s in starts)  # "HH:MM", in order
        for a in day["activities"]:
            assert japan.get(Activity, a["activity_id"]).city == details["city"]
            assert Decimal(a["price"]) == Decimal(a["price_per_person"]) * 2
    assert any(not a["selected"] for d in details["days"] for a in d["activities"])  # alternatives are offered


def test_details_need_login_and_ownership(client, trip):
    _, [first, *_] = trip
    assert client.get(f"/api/itineraries/{first + 1000}").status_code == 404
    login(client, "mario")
    assert client.get(f"/api/itineraries/{first}").status_code == 404
    client.cookies.clear()
    assert client.get(f"/api/itineraries/{first}").status_code == 401


# --- PUT /api/itineraries/{id}/activities ---------------------------------------------------------------------

def test_new_selection_recomputes_the_total(client, japan, trip):
    _, [first, *_] = trip
    details = client.get(f"/api/itineraries/{first}").json()
    day = details["days"][0]
    alternative = next(a for a in day["activities"] if not a["selected"])

    r = client.put(f"/api/itineraries/{first}/activities",
                   json=[{"day": day["day"], "activity_id": alternative["activity_id"]}])

    assert r.status_code == 200
    saved = r.json()
    assert selection_of(saved) == [{"day": day["day"], "activity_id": alternative["activity_id"]}]
    assert Decimal(saved["total"]) == fixed_cost(details) + Decimal(alternative["price"])
    it = japan.get(Itinerary, first)
    japan.refresh(it)
    assert it.total_cost == Decimal(saved["total"]) == sum(i.price for i in it.items)
    assert client.get(f"/api/itineraries/{first}").json() == saved


def test_empty_selection_leaves_flights_and_hotel(client, trip):
    _, [first, *_] = trip
    details = client.get(f"/api/itineraries/{first}").json()
    saved = client.put(f"/api/itineraries/{first}/activities", json=[]).json()
    assert Decimal(saved["total"]) == fixed_cost(details)
    assert selection_of(saved) == []


def rejected(client, itinerary_id, selection, status, code):
    before = client.get(f"/api/itineraries/{itinerary_id}").json()
    r = client.put(f"/api/itineraries/{itinerary_id}/activities", json=selection)
    assert (r.status_code, r.json()["detail"]["code"]) == (status, code)
    assert client.get(f"/api/itineraries/{itinerary_id}").json() == before  # nothing saved


def test_overlapping_activities_are_rejected(client, trip):
    _, [first, *_] = trip
    details = client.get(f"/api/itineraries/{first}").json()
    day, a, b = next((d, a, b) for d in details["days"] for i, a in enumerate(d["activities"])
                     for b in d["activities"][i + 1:] if overlap(a, b))
    rejected(client, first, [{"day": day["day"], "activity_id": x["activity_id"]} for x in (a, b)], 422, "overlap")


def test_over_budget_is_rejected(client, japan, trip):
    _, [first, *_] = trip
    details = client.get(f"/api/itineraries/{first}").json()
    japan.get(Itinerary, first).budget = fixed_cost(details) + Decimal("1")
    japan.flush()
    day = details["days"][0]
    rejected(client, first, [{"day": day["day"], "activity_id": day["activities"][0]["activity_id"]}],
             422, "over_budget")


def test_the_same_activity_on_two_days_is_rejected(client, trip):
    _, [first, *_] = trip
    details = client.get(f"/api/itineraries/{first}").json()
    days_of = {}
    for d in details["days"]:
        for a in d["activities"]:
            days_of.setdefault(a["activity_id"], []).append(d["day"])
    activity, days = next((a, ds) for a, ds in days_of.items() if len(ds) > 1)  # it runs on several days
    rejected(client, first, [{"day": day, "activity_id": activity} for day in days[:2]], 422, "duplicate")


def test_days_outside_the_full_days_are_rejected(client, trip):
    _, [first, *_] = trip
    details = client.get(f"/api/itineraries/{first}").json()
    arrival_day = (date.fromisoformat(details["days"][0]["day"]) - timedelta(days=1)).isoformat()
    activity = details["days"][0]["activities"][0]["activity_id"]
    rejected(client, first, [{"day": arrival_day, "activity_id": activity}], 422, "invalid_day")


def test_activities_of_another_city_are_rejected(client, japan, trip):
    _, [first, *_] = trip
    details = client.get(f"/api/itineraries/{first}").json()
    elsewhere = japan.scalars(select(Activity.id).where(Activity.city != details["city"])).first()
    rejected(client, first, [{"day": details["days"][0]["day"], "activity_id": elsewhere}], 409, "unavailable")


def test_booked_and_superseded_proposals_are_read_only(client, japan, trip):
    user_id, [first, second, *_] = trip
    book_itinerary(japan, user_id=user_id, itinerary_id=first)
    for itinerary_id in (first, second):
        rejected(client, itinerary_id, [], 409, "not_editable")


def test_someone_elses_itinerary_cannot_be_changed(client, trip):
    _, [first, *_] = trip
    login(client, "mario")
    assert client.put(f"/api/itineraries/{first}/activities", json=[]).status_code == 404


# --- GET /api/bookings ----------------------------------------------------------------------------------------

def test_bookings_lists_only_your_own(client, japan, trip):
    user_id, [first, *_] = trip
    assert client.get("/api/bookings").json() == []
    booking = book_itinerary(japan, user_id=user_id, itinerary_id=first)
    japan.flush()

    [listed] = client.get("/api/bookings").json()
    details = client.get(f"/api/itineraries/{first}").json()
    assert (listed["booking_id"], listed["status"]) == (booking.id, "confirmed")
    summary = listed["itinerary"]
    assert (summary["itinerary_id"], summary["variant"], summary["total"]) == (first, details["variant"], details["total"])
    assert (summary["origin"], summary["destination"]) == (details["flights"][0]["origin"],
                                                           details["flights"][0]["destination"])
    assert details["status"] == "booked"

    login(client, "mario")
    assert client.get("/api/bookings").json() == []
