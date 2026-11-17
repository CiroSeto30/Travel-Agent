"""The cheapest set of hotel rooms that gives every traveler a bed."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import product


@dataclass(frozen=True)
class RoomOption:
    """A room type that is free every night of the stay."""

    room_type_id: int
    name: str
    beds: int
    available: int  # rooms free on every night of the stay
    cost: Decimal  # one room for the whole stay
    nightly: tuple[tuple[date, Decimal], ...]  # price of one room, night by night


@dataclass(frozen=True)
class RoomPick:
    option: RoomOption
    quantity: int


def cheapest_rooms(options: list[RoomOption], travelers: int) -> list[RoomPick] | None:
    """Try every combination: at most 4 room types and 6 travelers, so a few hundred at most.

    Cheapest first; at equal cost fewer empty beds, then fewer rooms. None if no combination has enough beds.
    """
    best, best_key = None, None
    for quantities in product(*(range(min(o.available, travelers) + 1) for o in options)):
        beds = sum(q * o.beds for q, o in zip(quantities, options))
        rooms = sum(quantities)
        if beds < travelers or rooms > travelers:
            continue
        key = (sum(q * o.cost for q, o in zip(quantities, options)), beds - travelers, rooms)
        if best_key is None or key < best_key:
            best, best_key = quantities, key
    if best is None:
        return None
    return [RoomPick(option=o, quantity=q) for o, q in zip(options, best) if q]