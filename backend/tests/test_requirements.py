from decimal import Decimal

import pytest

from app.agent.requirements import CatalogInfo, Requirements, load_catalog_info, merge, review

CATALOG = CatalogInfo(
    countries={"Giappone": ["Kyoto", "Osaka", "Tokyo"], "Spagna": ["Barcellona", "Madrid", "Siviglia"]},
    departures={"FCO": "Roma", "MXP": "Milano", "NAP": "Napoli"},
)
COMPLETE = Requirements(budget=Decimal("4000"), country="Giappone", month=4, nights=5, travelers=2, origin="NAP")


def test_nothing_said_yet_everything_is_missing():
    r = review(Requirements(), CATALOG)
    assert r.missing == ["budget", "country", "month", "nights", "travelers", "origin"]
    assert not r.complete and r.problems == {}


def test_complete_and_valid_gives_a_trip_request():
    r = review(COMPLETE.model_copy(update={"preferences": "buon cibo", "categories": ["food"]}), CATALOG)
    assert r.complete
    trip = r.trip_request()
    assert (trip.country, trip.month, trip.nights, trip.travelers, trip.origin) == ("Giappone", 4, 5, 2, "NAP")
    assert trip.budget == Decimal("4000") and trip.preferences == "buon cibo" and trip.categories == ("food",)


def test_later_messages_change_one_thing_at_a_time():
    first = merge(Requirements(), Requirements(country="Giappone", month=4))
    second = merge(first, Requirements(budget=Decimal("3000"), month=5))
    assert (second.country, second.month, second.budget) == ("Giappone", 5, Decimal("3000"))
    assert merge(second, Requirements()) == second  # saying nothing new changes nothing


@pytest.mark.parametrize("said, canonical", [("giappone", "Giappone"), (" SPAGNA ", "Spagna")])
def test_country_names_are_matched_without_case(said, canonical):
    assert review(COMPLETE.model_copy(update={"country": said}), CATALOG).requirements.country == canonical


@pytest.mark.parametrize("said", ["NAP", "nap", "Napoli", "napoli"])
def test_departure_by_code_or_city(said):
    r = review(COMPLETE.model_copy(update={"origin": said}), CATALOG)
    assert r.complete and r.requirements.origin == "NAP"


@pytest.mark.parametrize("field, value, problem", [
    ("country", "Australia", "not_available"),
    ("origin", "Bari", "not_available"),
    ("budget", Decimal("0"), "out_of_range"),
    ("month", 13, "out_of_range"),
    ("nights", 1, "out_of_range"),
    ("nights", 15, "out_of_range"),
    ("travelers", 7, "out_of_range"),
    ("categories", ["shopping"], "unknown"),
])
def test_invalid_values_are_reported_not_used(field, value, problem):
    r = review(COMPLETE.model_copy(update={field: value}), CATALOG)
    assert r.problems == {field: problem}
    assert not r.complete


def test_catalog_info_is_read_from_the_database(japan):
    info = load_catalog_info(japan)
    assert info.countries == {"Giappone": ["Osaka", "Sapporo", "Tokyo"]}
    assert info.departures == {"FCO": "Roma", "MXP": "Milano", "NAP": "Napoli"}
