"""Change the activities of a proposed itinerary (docs/design.md §11 bis). The server checks every rule."""

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity, ActivitySlot, Itinerary, ItineraryItem
from app.itineraries.views import end_time, stay_of
from app.planner.schedule import Slot, overlaps


class SelectionError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status  # the HTTP status the API answers with
        self.code = code  # "not_found", "not_editable", "invalid_day", "unavailable", "overlap", "over_budget"


def update_activities(s: Session, *, user_id: int, itinerary_id: int,
                      selection: list[tuple[date, int]]) -> Itinerary:
    """Replace the itinerary's activities with `selection` (day, activity id) and recompute the total.

    Every rule is checked before anything changes, so a rejected selection leaves nothing to undo.
    Flushes; the caller commits. Locks the itinerary row, so a booking and a change never interleave.
    """
    itinerary = s.scalar(select(Itinerary).where(Itinerary.id == itinerary_id, Itinerary.user_id == user_id)
                         .with_for_update().execution_options(populate_existing=True))
    if itinerary is None:
        raise SelectionError(404, "not_found", f"itinerary {itinerary_id} not found")
    if itinerary.status != "proposed":
        raise SelectionError(409, "not_editable", f"itinerary {itinerary_id} is {itinerary.status}")

    stay = stay_of(s, itinerary)
    wanted = sorted(set(selection))
    if any(day not in stay.full_days for day, _ in wanted):
        raise SelectionError(422, "invalid_day", "activities only go on the full days of the trip")

    activities = {a.id: a for a in s.scalars(select(Activity).where(Activity.id.in_({a for _, a in wanted})))}
    by_day = defaultdict(list)
    for day, activity_id in wanted:
        a = activities.get(activity_id)
        slot = s.get(ActivitySlot, (activity_id, day))
        if a is None or a.city != stay.hotel.city or slot is None or slot.spots_left < itinerary.travelers:
            raise SelectionError(409, "unavailable", f"activity {activity_id} is not available on {day}")
        by_day[day].append(Slot(a.id, a.name, a.start_time, end_time(a.start_time, a.duration_hours), a.price))
    for slots in by_day.values():
        if any(overlaps(x, y) for i, x in enumerate(slots) for y in slots[i + 1:]):
            raise SelectionError(422, "overlap", "two activities of the same day overlap")

    kept = [i for i in itinerary.items if i.kind != "activity"]
    new = [ItineraryItem(kind="activity", activity_id=a, quantity=itinerary.travelers, day=day,
                         price=activities[a].price * itinerary.travelers) for day, a in wanted]
    total = sum(i.price for i in kept) + sum(i.price for i in new)
    if total > itinerary.budget:
        raise SelectionError(422, "over_budget", f"{total} is over the budget of {itinerary.budget}")

    for item in itinerary.items:
        if item.kind == "activity":
            s.delete(item)
    itinerary.items = kept + new
    itinerary.total_cost = total
    s.flush()
    return itinerary
