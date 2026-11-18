"""Conversations and the chat endpoint, which answers with a stream of server-sent events (docs/design.md §10)."""

import json
import logging
import queue
import threading
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app.agent.graph import Deps
from app.agent.runtime import get_agent
from app.api.deps import CurrentUser, DbSession
from app.db.models import Conversation, Message
from app.planner.planner import Ranker
from app.schemas.conversation import ConversationDetails, ConversationOut, MessageIn

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["conversations"])

TITLE_LENGTH = 80
_END = object()


def get_today() -> date:
    return date.today()


def get_ranker() -> Ranker:
    from app.rag.clients import get_ranker as rag_ranker

    return rag_ranker()


def _own(db: DbSession, user_id: int, conversation_id: int) -> Conversation:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id,
                                                        Conversation.user_id == user_id))
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, {"code": "not_found", "message": "Conversation not found"})
    return conversation


@router.post("", status_code=status.HTTP_201_CREATED)
def create_conversation(user: CurrentUser, db: DbSession) -> ConversationOut:
    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("")
def list_conversations(user: CurrentUser, db: DbSession) -> list[ConversationOut]:
    return list(db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                           .order_by(Conversation.updated_at.desc(), Conversation.id.desc())))


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, user: CurrentUser, db: DbSession) -> ConversationDetails:
    return _own(db, user.id, conversation_id)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/{conversation_id}/messages")
def send_message(conversation_id: int, message: MessageIn, user: CurrentUser, db: DbSession,
                 agent: Annotated[Any, Depends(get_agent)], today: Annotated[date, Depends(get_today)],
                 rank: Annotated[Ranker, Depends(get_ranker)]) -> StreamingResponse:
    conversation = _own(db, user.id, conversation_id)
    if conversation.title is None:
        conversation.title = message.content[:TITLE_LENGTH]
    db.add(Message(conversation_id=conversation.id, role="user", content=message.content))
    db.commit()
    deps = Deps(db=db, user_id=user.id, conversation_id=conversation.id, today=today, rank=rank)
    config = {"configurable": {"thread_id": f"conversation-{conversation.id}"}}

    # The agent runs in its own thread and puts what it streams in a queue; the response reads the queue.
    # LangGraph's sync stream keeps its context in the thread that started it, while a streaming response
    # may resume its generator in a different thread at every step.
    chunks: queue.Queue = queue.Queue()

    def run() -> None:
        try:
            for chunk in agent.stream({"messages": [HumanMessage(message.content)]}, config, context=deps,
                                      stream_mode="custom"):
                chunks.put(chunk)
        except Exception as e:  # reported to the user as an error event, with the details in the log
            log.exception("agent failed in conversation %s", conversation.id)
            chunks.put(e)
        chunks.put(_END)

    def stream():
        threading.Thread(target=run, daemon=True).start()
        text, saved_events = [], []
        while (chunk := chunks.get()) is not _END:
            if isinstance(chunk, Exception):
                db.rollback()
                yield _sse("error", {"code": "agent_error",
                                     "message": "Non sono riuscito a rispondere. Riprova tra qualche istante."})
                return
            kind = chunk["type"]
            data = {k: v for k, v in chunk.items() if k != "type"}
            if kind == "token":
                text.append(data["text"])
            elif kind in ("requirements", "itinerary", "booking"):
                saved_events.append(chunk)
            yield _sse(kind, data)
        reply = Message(conversation_id=conversation.id, role="assistant", content="".join(text),
                        payload={"events": saved_events})
        db.add(reply)
        db.commit()
        yield _sse("done", {"message_id": reply.id})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
