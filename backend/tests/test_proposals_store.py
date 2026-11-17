from datetime import date
from decimal import Decimal

from app.db.models import Itinerary, User
from app.planner.planner import TripRequest, plan
from app.planner.store import save_proposals
from tests.conftest import TODAY


def test_saved_itineraries_match_the_proposals(japan):
    user = User(email="ciro@example.com", password_hash="x", first_name="Ciro", last_name="Setolino")
    japan.add(user)
    japan.flush()
    req = TripRequest(country="Giappone", month=4, nights=5, travelers=3, budget=Decimal("6000"), origin="NAP")
    proposals = plan(japan, req, today=TODAY)

    saved = save_proposals(japan, user_id=user.id, conversation_id=None, request=req, proposals=proposals)

    assert len(saved) == len(proposals)
    assert len({it.proposal_set_id for it in saved}) == 1
    for it, p in zip(saved, proposals):
        it = japan.get(Itinerary, it.id)
        assert (it.variant, it.status, it.travelers, it.budget) == (p.variant, "proposed", 3, Decimal("6000"))
        assert it.total_cost == p.total == sum(item.price for item in it.items)
        assert it.start_date == p.outbound.departure_at.date()
        assert it.end_date == p.inbound.departure_at.date()
        kinds = [item.kind for item in it.items]
        assert kinds.count("flight_out") == kinds.count("flight_return") == 1
        nights = (p.hotel.check_out - p.hotel.check_in).days
        assert kinds.count("hotel_night") == nights * len(p.hotel.rooms)
        assert kinds.count("activity") == sum(len(d.chosen) for d in p.days)
        assert all(item.quantity == 3 for item in it.items if item.kind != "hotel_night")
        assert it.items[0].day >= date(2027, 4, 1)