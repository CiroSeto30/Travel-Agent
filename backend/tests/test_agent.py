"""Scripted conversations with a fake LLM: the graph, not the prompt, decides when to plan and when to book."""

from decimal import Decimal

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from app.agent.brain import Turn
from app.agent.graph import Deps, build_graph
from app.agent.requirements import Requirements
from app.db.models import Booking, Flight, Itinerary, User
from tests.conftest import TODAY
from tests.fake_brain import ScriptedBrain


@pytest.fixture
def chat(japan):
    user = User(email="ciro@example.com", password_hash="x", first_name="Ciro", last_name="Setolino")
    japan.add(user)
    japan.flush()
    brain = ScriptedBrain()
    graph = build_graph(brain, checkpointer=InMemorySaver())
    deps = Deps(db=japan, user_id=user.id, conversation_id=None, today=TODAY)

    def say(text, turn):
        brain.turns.append(turn)
        state = graph.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": "t1"}},
                             context=deps)
        return state, brain.facts[-1]

    return say, japan


TRIP = Requirements(budget=Decimal("6000"), country="Giappone", month=4, nights=5, travelers=2, origin="Napoli")


def events_of(state, kind):
    return [e for e in state["events"] if e["type"] == kind]


def test_missing_data_gets_a_question_not_a_search(chat):
    say, db = chat
    state, facts = say("Vorrei andare in Giappone ad aprile", Turn(requirements=Requirements(country="Giappone", month=4)))
    assert facts["kind"] == "ask"
    assert facts["missing"] == ["budget", "nights", "travelers", "origin"]
    assert facts["departures"] == {"FCO": "Roma", "MXP": "Milano", "NAP": "Napoli"}  # so it can suggest them
    [req] = events_of(state, "requirements")
    assert req["country"] == "Giappone" and req["missing"] == facts["missing"]
    assert db.scalar(select(func.count()).select_from(Itinerary)) == 0


def test_a_country_not_in_the_catalog_gets_the_list(chat):
    say, db = chat
    _, facts = say("Australia a maggio", Turn(requirements=Requirements(country="Australia", month=5)))
    assert facts["kind"] == "ask"
    assert facts["problems"] == {"country": "not_available"}
    assert facts["countries"] == {"Giappone": ["Osaka", "Sapporo", "Tokyo"]}


def test_requirements_add_up_across_messages_then_it_plans(chat):
    say, db = chat
    say("Giappone ad aprile", Turn(requirements=Requirements(country="Giappone", month=4)))
    state, facts = say("6000 euro, 5 notti, in due, da Napoli",
                       Turn(requirements=Requirements(budget=Decimal("6000"), nights=5, travelers=2, origin="Napoli")))
    assert facts["kind"] == "proposals"
    assert [o["variant"] for o in facts["options"]] == ["Economica", "Bilanciata", "Comfort"]
    [event] = events_of(state, "itinerary")
    assert event["supersedes"] is None and [o["itinerary_id"] for o in event["options"]] == \
        [o["itinerary_id"] for o in facts["options"]]
    assert all(Decimal(o["total"]) <= Decimal("6000") for o in facts["options"])
    saved = db.scalars(select(Itinerary)).all()
    assert len(saved) == 3 and {it.status for it in saved} == {"proposed"}


def test_changing_one_thing_plans_again_and_supersedes_the_old_proposals(chat):
    say, db = chat
    first, _ = say("...", Turn(requirements=TRIP))
    old = events_of(first, "itinerary")[0]
    state, facts = say("meglio 4 notti", Turn(requirements=Requirements(nights=4)))
    new = events_of(state, "itinerary")[0]
    assert new["supersedes"] == old["proposal_set_id"] != new["proposal_set_id"]
    assert {db.get(Itinerary, o["itinerary_id"]).status for o in old["options"]} == {"superseded"}


def test_a_question_does_not_plan_again(chat):
    say, db = chat
    say("...", Turn(requirements=TRIP))
    state, facts = say("che tempo fa a Tokyo?", Turn(intent="other"))
    assert facts["kind"] == "chat" and not events_of(state, "itinerary")
    assert db.scalar(select(func.count()).select_from(Itinerary)) == 3


def test_booking_needs_the_summary_then_an_explicit_yes(chat):
    say, db = chat
    say("...", Turn(requirements=TRIP))
    state, facts = say("prenota la bilanciata", Turn(intent="choose", choice="Bilanciata"))
    assert facts["kind"] == "summary" and facts["itinerary"]["variant"] == "Bilanciata"
    chosen = facts["itinerary"]["itinerary_id"]
    assert db.scalar(select(func.count()).select_from(Booking)) == 0  # choosing is not booking

    state, facts = say("sì, confermo", Turn(intent="confirm"))
    assert facts["kind"] == "booked"
    [event] = events_of(state, "booking")
    booking = db.get(Booking, event["booking_id"])
    assert booking.itinerary_id == chosen and db.get(Itinerary, chosen).status == "booked"


def test_yes_without_a_summary_books_nothing(chat):
    say, db = chat
    say("...", Turn(requirements=TRIP))
    _, facts = say("sì, prenota", Turn(intent="confirm"))
    assert facts["kind"] != "booked"
    assert db.scalar(select(func.count()).select_from(Booking)) == 0


def test_anything_but_a_yes_after_the_summary_cancels_it(chat):
    say, db = chat
    say("...", Turn(requirements=TRIP))
    say("la comfort", Turn(intent="choose", choice="Comfort"))
    say("aspetta, quanto costano i voli?", Turn(intent="other"))
    _, facts = say("sì", Turn(intent="confirm"))  # the summary is no longer the last thing shown
    assert facts["kind"] != "booked"
    assert db.scalar(select(func.count()).select_from(Booking)) == 0


def test_a_changed_total_is_shown_again_before_booking(chat):
    say, db = chat
    say("...", Turn(requirements=TRIP))
    _, facts = say("la economica", Turn(intent="choose", choice="Economica"))
    itinerary = db.get(Itinerary, facts["itinerary"]["itinerary_id"])
    itinerary.total_cost -= Decimal("10")  # as if the user had changed an activity in the panel
    db.flush()
    _, facts = say("sì", Turn(intent="confirm"))
    assert facts["kind"] == "summary" and Decimal(facts["itinerary"]["total"]) == itinerary.total_cost
    assert db.scalar(select(func.count()).select_from(Booking)) == 0


def test_an_item_gone_meanwhile_books_nothing_and_says_what(chat):
    say, db = chat
    say("...", Turn(requirements=TRIP))
    _, facts = say("la economica", Turn(intent="choose", choice="Economica"))
    itinerary = db.get(Itinerary, facts["itinerary"]["itinerary_id"])
    db.get(Flight, next(i.flight_id for i in itinerary.items if i.kind == "flight_out")).seats_left = 0  # someone else took the seats
    db.flush()
    _, facts = say("sì", Turn(intent="confirm"))
    assert facts["kind"] == "booking_failed" and facts["item"]
    assert db.get(Itinerary, itinerary.id).status == "proposed"
    assert db.scalar(select(func.count()).select_from(Booking)) == 0


def test_budget_too_low_says_the_minimum(chat):
    say, db = chat
    _, facts = say("...", Turn(requirements=TRIP.model_copy(update={"budget": Decimal("300")})))
    assert facts["kind"] == "no_solution" and facts["reason"] == "over_budget"
    assert Decimal(facts["minimum_cost"]) > Decimal("300")


def test_destinations_endpoint_lists_countries_and_departures(client, japan):
    r = client.get("/api/destinations")  # public: the welcome message shows it before anything else
    assert r.status_code == 200
    assert r.json() == {"countries": [{"country": "Giappone", "cities": ["Osaka", "Sapporo", "Tokyo"]}],
                        "departures": [{"iata": "FCO", "city": "Roma"}, {"iata": "MXP", "city": "Milano"},
                                       {"iata": "NAP", "city": "Napoli"}]}


@pytest.fixture(scope="session")
def checkpoint_tables(test_engine):
    """Session scope, so it runs before any test transaction is open (see setup_checkpointer)."""
    from app.agent.runtime import setup_checkpointer
    from app.config import get_settings

    setup_checkpointer(get_settings().test_database_url)


def test_the_conversation_survives_a_restart_with_the_postgres_checkpointer(checkpoint_tables, japan):
    """State lives in PostgreSQL: a new graph, as after restarting the server, continues the same thread."""
    import uuid

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    from app.agent.runtime import checkpoint_conninfo
    from app.config import get_settings

    user = User(email="ciro@example.com", password_hash="x", first_name="Ciro", last_name="Setolino")
    japan.add(user)
    japan.flush()
    deps = Deps(db=japan, user_id=user.id, conversation_id=None, today=TODAY)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    conninfo = checkpoint_conninfo(get_settings().test_database_url)
    kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}

    for turn in (Turn(requirements=Requirements(country="Giappone", month=4)),
                 Turn(requirements=Requirements(budget=Decimal("6000"), nights=5, travelers=2, origin="NAP"))):
        with ConnectionPool(conninfo, kwargs=kwargs, open=True) as pool:  # a fresh pool and graph each time
            saver = PostgresSaver(pool)
            brain = ScriptedBrain()
            brain.turns.append(turn)
            build_graph(brain, checkpointer=saver).invoke({"messages": [HumanMessage("...")]}, config, context=deps)
    assert brain.facts[-1]["kind"] == "proposals"  # the second graph remembered the first message
