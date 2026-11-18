"""Conversations and their messages, as the chat page reads them."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str  # "user" or "assistant"
    content: str
    payload: dict[str, Any] | None  # the structured events of an assistant reply, to rebuild the tickets
    created_at: datetime


class ConversationDetails(ConversationOut):
    messages: list[MessageOut]


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
