from datetime import date, time
from decimal import Decimal

from app.planner.schedule import Slot, choose_activities, overlaps

D1, D2 = date(2027, 4, 11), date(2027, 4, 12)


def slot(activity_id, start, end, price="20"):
    return Slot(activity_id=activity_id, name=f"a{activity_id}", start=time(*start), end=time(*end),
                unit_price=Decimal(price))


TEA = slot(1, (11, 0), (12, 30))
SUSHI = slot(2, (11, 30), (14, 30))
ONSEN = slot(3, (15, 0), (18, 0))  # 30 minutes after the sushi class
BARS = slot(4, (20, 30), (23, 30))


def test_overlap_needs_thirty_minutes_between():
    assert overlaps(TEA, SUSHI)
    assert not overlaps(SUSHI, ONSEN)
    assert overlaps(SUSHI, slot(5, (14, 45), (16, 0)))


def test_two_relevant_activities_per_day_without_overlaps():
    chosen = choose_activities({D1: [TEA, SUSHI, ONSEN, BARS]}, ranking=[1, 2, 3, 4], travelers=2,
                               money=Decimal("1000"))
    assert [s.activity_id for s in chosen[D1]] == [1, 3]


def test_an_activity_is_chosen_once_per_trip():
    chosen = choose_activities({D1: [TEA, ONSEN], D2: [TEA, ONSEN]}, ranking=[1, 3], travelers=1,
                               money=Decimal("1000"))
    ids = [s.activity_id for day in chosen.values() for s in day]
    assert len(ids) == len(set(ids)) == 2


def test_money_is_shared_across_days():
    # 2 travelers x 20 = 40 per activity: with 80 one per day, not two on the first day
    chosen = choose_activities({D1: [TEA, ONSEN], D2: [SUSHI, BARS]}, ranking=[1, 3, 2, 4], travelers=2,
                               money=Decimal("80"))
    assert [len(chosen[D1]), len(chosen[D2])] == [1, 1]