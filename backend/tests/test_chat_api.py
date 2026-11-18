"""The chat over HTTP: conversations, the event stream, and the messages saved for the history."""

import json
from decimal import Decimal

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.brain import Turn
from app.agent.graph import build_graph
from app.agent.requirements import Requirements
from app.agent.runtime import get_agent
from app.api.conversations import get_ranker, get_today
from app.main import app
from app.planner.planner import rank_by_category
from tests.conftest import TODAY
from tests.fake_brain import ScriptedBrain
from tests.test_itineraries_api import login

TRIP = Requirements(budget=Decimal("6000"), country="Giappone", month=4, nights=5, travelers=2, origin="NAP")


@pytest.fixture
def brain(client, japan):
    brain = ScriptedBrain()
    graph = build_graph(brain, checkpointer=InMemorySaver())
    app.dependency_overrides |= {get_agent: lambda: graph, get_today: lambda: TODAY,
                                 get_ranker: lambda: rank_by_category}
    login(client)
    return brain


def events(response):
    """The stream as (event, data) pairs."""
    assert response.headers["content-type"].startswith("text/event-stream")
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def send(client, brain, conversation_id, text, turn):
    brain.turns.append(turn)
    return events(client.post(f"/api/conversations/{conversation_id}/messages", json={"content": text}))


def test_conversations_belong_to_their_user(client, brain):
    created = client.post("/api/conversations").json()
    assert [c["id"] for c in client.get("/api/conversations").json()] == [created["id"]]
    login(client, "mario")
    assert client.get("/api/conversations").json() == []
    assert client.get(f"/api/conversations/{created['id']}").status_code == 404
    r = client.post(f"/api/conversations/{created['id']}/messages", json={"content": "ciao"})
    assert r.status_code == 404


def test_a_message_streams_events_then_text_then_done(client, brain):
    conversation = client.post("/api/conversations").json()["id"]
    stream = send(client, brain, conversation, "Giappone ad aprile", Turn(requirements=Requirements(country="Giappone")))

    kinds = [e for e, _ in stream]
    assert kinds[0] == "requirements" and kinds[-1] == "done"
    assert "".join(d["text"] for e, d in stream if e == "token") == "ok: ask"
    assert stream[0][1]["country"] == "Giappone" and "month" in stream[0][1]["missing"]


def test_the_whole_trip_over_http(client, brain):
    conversation = client.post("/api/conversations").json()["id"]

    stream = send(client, brain, conversation, "Giappone ad aprile, 5 notti, in due, 6000 euro, da Napoli",
                  Turn(requirements=TRIP))
    kinds = [e for e, _ in stream]
    assert kinds.index("tool_start") < kinds.index("tool_end") < kinds.index("itinerary") < kinds.index("token")
    [proposals] = [d for e, d in stream if e == "itinerary"]
    assert [o["variant"] for o in proposals["options"]] == ["Economica", "Bilanciata", "Comfort"]

    send(client, brain, conversation, "Prenota l'opzione bilanciata", Turn(intent="choose", choice="Bilanciata"))
    assert client.get("/api/bookings").json() == []  # a summary, not a booking

    stream = send(client, brain, conversation, "Sì, confermo", Turn(intent="confirm"))
    [booking] = [d for e, d in stream if e == "booking"]
    [listed] = client.get("/api/bookings").json()
    assert listed["booking_id"] == booking["booking_id"]
    assert listed["itinerary"]["variant"] == "Bilanciata"


def test_messages_are_saved_to_rebuild_the_chat(client, brain):
    conversation = client.post("/api/conversations").json()["id"]
    stream = send(client, brain, conversation, "Giappone ad aprile, 5 notti, in due, 6000 euro, da Napoli",
                  Turn(requirements=TRIP))

    details = client.get(f"/api/conversations/{conversation}").json()
    assert details["title"] == "Giappone ad aprile, 5 notti, in due, 6000 euro, da Napoli"
    user, assistant = details["messages"]
    assert (user["role"], assistant["role"]) == ("user", "assistant")
    assert assistant["content"] == "ok: proposals"
    assert [e["type"] for e in assistant["payload"]["events"]] == ["requirements", "itinerary"]
    assert stream[-1] == ("done", {"message_id": assistant["id"]})


def test_an_agent_failure_becomes_an_error_event(client, brain):
    conversation = client.post("/api/conversations").json()["id"]
    brain.extract = lambda *args: 1 / 0  # the LLM call fails, as on a network or quota error
    stream = events(client.post(f"/api/conversations/{conversation}/messages", json={"content": "ciao"}))
    assert stream[-1][0] == "error" and stream[-1][1]["code"] == "agent_error"


def test_empty_messages_are_rejected(client, brain):
    conversation = client.post("/api/conversations").json()["id"]
    assert client.post(f"/api/conversations/{conversation}/messages", json={"content": ""}).status_code == 422
