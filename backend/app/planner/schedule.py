"""Which activities to do on each day: relevant, affordable, never overlapping."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

GAP_MINUTES = 30  # time to move between two activities of the same day
PER_DAY = 2


@dataclass(frozen=True)
class Slot:
    """An activity available on a given day."""

    activity_id: int
    name: str
    start: time
    end: time
    unit_price: Decimal  # per person


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def overlaps(a: Slot, b: Slot) -> bool:
    return (_minutes(a.start) < _minutes(b.end) + GAP_MINUTES
            and _minutes(b.start) < _minutes(a.end) + GAP_MINUTES)


def choose_activities(days: dict[date, list[Slot]], ranking: list[int], travelers: int,
                      money: Decimal) -> dict[date, list[Slot]]:
    """Up to PER_DAY activities a day, the most relevant first.

    Days are filled in rounds (first choice of every day, then the second), so the money left is shared
    across the trip instead of being spent on the first days. An activity is chosen at most once per trip.
    """
    order = {activity_id: i for i, activity_id in enumerate(ranking)}
    chosen: dict[date, list[Slot]] = {day: [] for day in days}
    used: set[int] = set()
    for _ in range(PER_DAY):
        for day in sorted(days):
            candidates = sorted(days[day], key=lambda s: order.get(s.activity_id, len(order)))
            for slot in candidates:
                cost = slot.unit_price * travelers
                if (slot.activity_id in used or cost > money
                        or any(overlaps(slot, other) for other in chosen[day])):
                    continue
                chosen[day].append(slot)
                used.add(slot.activity_id)
                money -= cost
                break
    for day in chosen:
        chosen[day].sort(key=lambda s: s.start)
    return chosen