"""The agent as a LangGraph state graph (docs/design.md §8).

    understand ─┬─> plan ──────┐
                ├─> summarize ─┤
                ├─> book ──────┼─> respond
                └──────────────┘

The LLM reads and writes text in `understand` and `respond`. Which step runs in between is decided by the
code in `route`: booking is reachable only when the previous answer was the booking summary and the
user's answer is a confirmation.
"""

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.runtime import Runtime
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agent.brain import Brain, Turn
from app.agent.requirements import CatalogInfo, Requirements, load_catalog_info, merge, review
from app.booking.service import BookingError, book_itinerary
from app.db.models import Itinerary
from app.itineraries.views import itinerary_details, itinerary_summary
from app.planner.planner import NoSolution, Ranker, plan, rank_by_category
from app.planner.store import save_proposals


@dataclass
class Deps:
    """Per-request dependencies, passed as LangGraph context: never saved in the checkpoint."""

    db: Session
    user_id: int
    conversation_id: int | None
    today: date
    rank: Ranker = rank_by_category


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    requirements: dict[str, Any]  # Requirements, as JSON
    planned_for: dict[str, Any] | None  # the requirements the current proposals answer
    proposal_set_id: str | None
    proposals: list[dict[str, Any]]  # summaries of the current proposals
    pending: dict[str, Any] | None  # {"itinerary_id", "total"}: the summary waiting for a yes
    turn: dict[str, Any]  # what the last message means
    route: str
    facts: dict[str, Any]  # what the answer must say
    events: list[dict[str, Any]]  # structured events of this turn, for the stream


def _catalog_facts(catalog: CatalogInfo) -> dict[str, Any]:
    return {"countries": catalog.countries, "departures": catalog.departures}


def _summary_facts(s: Session, itinerary: Itinerary) -> tuple[dict, dict]:
    details = itinerary_details(s, itinerary).model_dump(mode="json")
    return {"kind": "summary", "itinerary": details}, {"itinerary_id": itinerary.id, "total": details["total"]}


def build_graph(brain: Brain, checkpointer=None):
    def understand(state: AgentState, runtime: Runtime[Deps]) -> dict:
        db = runtime.context.db
        catalog = load_catalog_info(db)
        known = Requirements(**state.get("requirements", {}))
        turn = brain.extract(state["messages"], known, catalog)
        r = review(merge(known, turn.requirements), catalog)
        requirements = r.requirements.model_dump(mode="json")

        choice = next((p for p in state.get("proposals", []) if p["variant"] == turn.choice), None)
        if turn.intent == "confirm" and state.get("pending"):
            route = "book"
        elif turn.intent == "choose" and choice:
            route = "summarize"
        elif r.complete and requirements != state.get("planned_for"):
            route = "plan"
        else:
            route = "respond"

        if not r.complete:
            facts = {"kind": "ask", "missing": r.missing, "problems": r.problems, **_catalog_facts(catalog)}
        else:
            facts = {"kind": "chat", "proposals": state.get("proposals", []), **_catalog_facts(catalog)}
        event = {"type": "requirements", **requirements, "missing": r.missing, "problems": r.problems}
        get_stream_writer()(event)
        return {
            "requirements": requirements, "turn": {**turn.model_dump(mode="json"), "chosen": choice},
            "route": route, "facts": facts,
            # a summary waits for the very next message only
            "pending": state.get("pending") if route == "book" else None,
            "events": [event],
        }

    def plan_trip(state: AgentState, runtime: Runtime[Deps]) -> dict:
        deps = runtime.context
        db = deps.db
        write = get_stream_writer()
        trip = review(Requirements(**state["requirements"]), load_catalog_info(db)).trip_request()
        write({"type": "tool_start", "tool": "search_itineraries", "label": "Cerco voli, hotel e attività"})
        result = plan(db, trip, today=deps.today, rank=deps.rank)
        write({"type": "tool_end", "tool": "search_itineraries"})
        if isinstance(result, NoSolution):
            return {"planned_for": state["requirements"],
                    "facts": {"kind": "no_solution", "reason": result.reason,
                              "minimum_cost": None if result.minimum_cost is None else str(result.minimum_cost),
                              "requirements": state["requirements"]}}

        old = state.get("proposal_set_id")
        if old:
            db.execute(update(Itinerary).where(Itinerary.proposal_set_id == old, Itinerary.status == "proposed")
                       .values(status="superseded"))
        saved = save_proposals(db, user_id=deps.user_id, conversation_id=deps.conversation_id, request=trip,
                               proposals=result)
        db.commit()
        options = [itinerary_summary(db, it).model_dump(mode="json") for it in saved]
        set_id = saved[0].proposal_set_id
        event = {"type": "itinerary", "proposal_set_id": set_id, "supersedes": old, "options": options}
        write(event)
        return {"planned_for": state["requirements"], "proposal_set_id": set_id, "proposals": options,
                "facts": {"kind": "proposals", "options": options, "requirements": state["requirements"]},
                "events": state["events"] + [event]}

    def summarize(state: AgentState, runtime: Runtime[Deps]) -> dict:
        db = runtime.context.db
        itinerary = db.get(Itinerary, state["turn"]["chosen"]["itinerary_id"])
        if itinerary.status != "proposed":
            return {"facts": {**state["facts"], "kind": "chat", "note": f"that proposal is {itinerary.status}"}}
        facts, pending = _summary_facts(db, itinerary)
        return {"facts": facts, "pending": pending}

    def book(state: AgentState, runtime: Runtime[Deps]) -> dict:
        deps = runtime.context
        db = deps.db
        itinerary = db.scalar(select(Itinerary).where(Itinerary.id == state["pending"]["itinerary_id"]))
        if str(itinerary.total_cost) != state["pending"]["total"]:  # changed in the panel since the summary
            facts, pending = _summary_facts(db, itinerary)
            return {"facts": {**facts, "changed": True}, "pending": pending}
        write = get_stream_writer()
        write({"type": "tool_start", "tool": "book", "label": "Prenoto voli, hotel e attività"})
        try:
            with db.begin_nested():  # an unavailable item undoes the whole booking, and only the booking
                booking = book_itinerary(db, user_id=deps.user_id, itinerary_id=itinerary.id)
        except BookingError as e:
            write({"type": "tool_end", "tool": "book"})
            return {"pending": None, "facts": {"kind": "booking_failed", "code": e.code, "item": e.item}}
        db.commit()
        write({"type": "tool_end", "tool": "book"})
        event = {"type": "booking", "booking_id": booking.id, "itinerary_id": itinerary.id, "status": booking.status}
        write(event)
        summary = itinerary_summary(db, itinerary).model_dump(mode="json")
        return {"pending": None, "facts": {"kind": "booked", "booking_id": booking.id, "itinerary": summary},
                "events": state["events"] + [event]}

    def respond(state: AgentState) -> dict:
        write = get_stream_writer()
        return {"messages": [brain.reply(state["messages"], state["facts"],
                                         lambda text: write({"type": "token", "text": text}))]}

    g = StateGraph(AgentState, context_schema=Deps)
    g.add_node("understand", understand)
    g.add_node("plan", plan_trip)
    g.add_node("summarize", summarize)
    g.add_node("book", book)
    g.add_node("respond", respond)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", lambda s: s["route"], ["plan", "summarize", "book", "respond"])
    for node in ("plan", "summarize", "book"):
        g.add_edge(node, "respond")
    g.add_edge("respond", END)
    return g.compile(checkpointer=checkpointer)
