from decimal import Decimal

from app.planner.rooms import RoomOption, cheapest_rooms


def option(room_type_id, name, beds, cost, available=2):
    return RoomOption(room_type_id=room_type_id, name=name, beds=beds, available=available,
                      cost=Decimal(cost), nightly=())


SINGLE, DOUBLE, TRIPLE, FAMILY = (option(1, "Singola", 1, "75"), option(2, "Doppia", 2, "100"),
                                  option(3, "Tripla", 3, "130"), option(4, "Familiare", 4, "160"))


def picked(rooms):
    return sorted((r.option.name, r.quantity) for r in rooms)


def test_five_people_take_the_cheapest_combination():
    # familiare + singola = 235, tripla + doppia = 230
    assert picked(cheapest_rooms([SINGLE, DOUBLE, TRIPLE, FAMILY], 5)) == [("Doppia", 1), ("Tripla", 1)]


def test_one_person_takes_a_single():
    assert picked(cheapest_rooms([SINGLE, DOUBLE], 1)) == [("Singola", 1)]


def test_same_cost_prefers_fewer_empty_beds():
    cheap_double = option(2, "Doppia", 2, "75")
    assert picked(cheapest_rooms([SINGLE, cheap_double], 1)) == [("Singola", 1)]


def test_availability_limits_the_rooms():
    only_one_triple = option(3, "Tripla", 3, "130", available=1)
    assert picked(cheapest_rooms([only_one_triple, DOUBLE], 6)) == [("Doppia", 2), ("Tripla", 1)]


def test_not_enough_beds_gives_none():
    assert cheapest_rooms([option(2, "Doppia", 2, "100", available=1)], 3) is None