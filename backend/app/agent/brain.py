"""What the agent asks of the LLM: two jobs, both replaceable by a fake in the tests.

1. extract: read the last message and say what it adds to the requirements and what the user wants to do;
2. reply: write the answer from the facts the graph has established (never inventing prices or dates).

Everything in between (validation, planning, booking) is code in the graph.
"""

from collections.abc import Callable
from typing import Literal, Protocol

from langchain_core.messages import AIMessage, AnyMessage
from pydantic import BaseModel, Field

from app.agent.requirements import CatalogInfo, Requirements

Intent = Literal["trip", "choose", "confirm", "other"]
Variant = Literal["Economica", "Bilanciata", "Comfort"]


class Turn(BaseModel):
    """What one user message means."""

    requirements: Requirements = Field(default_factory=Requirements)  # only what this message says
    intent: Intent = Field(
        default="trip",
        description="trip: gives or changes requirements; choose: picks one of the proposals; "
                    "confirm: says yes to the booking summary just shown; other: anything else")
    choice: Variant | None = None  # the proposal picked, with intent "choose"


class Brain(Protocol):
    def extract(self, messages: list[AnyMessage], known: Requirements, catalog: CatalogInfo) -> Turn: ...

    def reply(self, messages: list[AnyMessage], facts: dict, on_token: Callable[[str], None]) -> AIMessage:
        """Write the answer, passing each piece of text to `on_token` as it is generated."""
        ...
