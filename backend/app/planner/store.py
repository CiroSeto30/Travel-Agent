"""Save the planner's proposals as itineraries, so the panel, the activity choice and the booking can use them."""

import uuid

from sqlalchemy.orm import Session

from app.db.models import Itinerary, ItineraryItem
from app.planner.planner import Proposal, TripRequest


def _items(p: Proposal) -> list[ItineraryItem]:
    items = [
        ItineraryItem(kind="flight_out", flight_id=p.outbound.flight_id, quantity=p.travelers,
                      day=p.outbound.departure_at.date(), price=p.outbound.total),
        ItineraryItem(kind="flight_return", flight_id=p.inbound.flight_id, quantity=p.travelers,
                      day=p.inbound.departure_at.date(), price=p.inbound.total),
    ]
    for room in p.hotel.rooms:
        items += [ItineraryItem(kind="hotel_night", room_type_id=room.option.room_type_id, quantity=room.quantity,
                                day=night, price=price * room.quantity)
                  for night, price in room.option.nightly]
    for day in p.days:
        items += [ItineraryItem(kind="activity", activity_id=a.activity_id, quantity=p.travelers, day=day.day,
                                price=a.total)
                  for a in day.chosen]
    return items


def save_proposals(s: Session, *, user_id: int, conversation_id: int | None, request: TripRequest,
                   proposals: list[Proposal]) -> list[Itinerary]:
    """One itinerary per proposal, all with the same proposal_set_id. Flushes; the caller commits."""
    set_id = str(uuid.uuid4())
    itineraries = []
    for p in proposals:
        itinerary = Itinerary(
            user_id=user_id, conversation_id=conversation_id, proposal_set_id=set_id, variant=p.variant,
            travelers=p.travelers, budget=request.budget, total_cost=p.total,
            start_date=p.outbound.departure_at.date(), end_date=p.inbound.departure_at.date(),
        )
        itinerary.items = _items(p)
        s.add(itinerary)
        itineraries.append(itinerary)
    s.flush()
    return itineraries