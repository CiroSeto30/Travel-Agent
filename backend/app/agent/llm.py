"""The real Brain: a chat model through LangChain, with a fallback model for when the free quota runs out."""

import json
import logging
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage

from app.agent.brain import Turn
from app.agent.requirements import CATEGORIES, NIGHTS, CatalogInfo, Requirements
from app.config import Settings
from app.db.models.itinerary import MAX_TRAVELERS

log = logging.getLogger(__name__)

HISTORY = 12  # messages of the conversation the model sees

EXTRACT_PROMPT = """You read a travel chat and report what the user's LAST message means. Do not answer it.

Report in `requirements` only what the last message says, leaving everything else null:
- budget: total for the whole group in euro. If it is per person and the number of travelers is known,
  multiply. Never invent one.
- country: one of these, spelled exactly like this: {countries}. If the user names a city, use its country.
  If the country is not in the list, report it as the user wrote it (the code will explain it is not available).
- month: 1-12. nights: number of nights. travelers: number of people.
- origin: the departure airport, code or city as the user said it. Departures: {departures}.
- preferences: what the user likes, in their own words (e.g. "musei e buon cibo, niente di troppo faticoso").
- categories: any of {categories} that clearly match the preferences.

intent:
- "trip": gives or changes trip details, or asks to search again;
- "choose": picks one of the proposals already shown (fill `choice` with Economica, Bilanciata or Comfort;
  "the cheapest" is Economica, "the best hotel" is Comfort);
- "confirm": says yes to the booking summary shown in the previous assistant message;
- "other": anything else (questions, thanks, small talk, a no).

Known so far: {known}"""

REPLY_PROMPT = """You are the assistant of a travel agency app. You plan trips with flights, one hotel and
daily activities, and book them in the chat. Reply in the user's language (Italian by default), briefly and
warmly, in plain text without markdown tables.

Use ONLY the facts below for prices, dates, names and availability. Never invent them. Amounts are in euro.
The app shows proposals and summaries as cards: do not repeat every detail, highlight what matters.

How to use the facts, by "kind":
- ask: ask for what is missing in one friendly question. Explain any problem ("not_available": not in the
  catalog, then list what is available; "out_of_range": nights {nights_min}-{nights_max}, travelers
  1-{max_travelers}). If nights are missing, suggest 5. If the departure is missing, list the departures.
- chat: answer the user. You can say which countries and departures are available. If there are proposals,
  remind them they can open the details or say which one to book.
- proposals: introduce the options in one or two sentences (city, how they differ, totals); invite them to
  open the details and to say which one to book.
- no_solution: explain why ("over_budget": the cheapest trip costs minimum_cost; "no_flights", "no_hotel")
  and suggest what to change (budget, nights, month).
- summary: summarize the chosen itinerary (city, dates, hotel, travelers, total) and ask for an explicit
  confirmation to book. If "changed" is true, say the total changed since the last summary.
- booked: confirm the booking and say it is in "Le mie prenotazioni".
- booking_failed: say the booking did not go through because an item is no longer available; offer to
  search again.

Facts: {facts}"""


def chat_model(provider: str, model: str, api_key: str) -> BaseChatModel:
    if provider == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # few retries: on a quota error the fallback model answers sooner
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0.3, max_retries=1)
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, api_key=api_key, temperature=0.3, max_retries=1)
    raise ValueError(f"unknown LLM_PROVIDER {provider!r}: use google_genai or groq")


class LLMBrain:
    def __init__(self, primary: BaseChatModel, fallback: BaseChatModel | None = None) -> None:
        extract = primary.with_structured_output(Turn)
        self._extract = extract.with_fallbacks([fallback.with_structured_output(Turn)]) if fallback else extract
        self._reply = primary.with_fallbacks([fallback]) if fallback else primary

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMBrain":
        key = settings.llm_api_key.get_secret_value()
        if not key or not settings.llm_model:
            raise RuntimeError("Set LLM_API_KEY and LLM_MODEL in .env to use the chat")
        fallback = settings.llm_fallback_model
        return cls(chat_model(settings.llm_provider, settings.llm_model, key),
                   chat_model(settings.llm_provider, fallback, key) if fallback else None)

    def extract(self, messages: list[AnyMessage], known: Requirements, catalog: CatalogInfo) -> Turn:
        prompt = EXTRACT_PROMPT.format(
            countries=", ".join(catalog.countries), categories=", ".join(CATEGORIES),
            departures=", ".join(f"{city} ({code})" for code, city in catalog.departures.items()),
            known=known.model_dump_json(exclude_none=True))
        return self._extract.invoke([SystemMessage(prompt), *messages[-HISTORY:]])

    def reply(self, messages: list[AnyMessage], facts: dict, on_token: Callable[[str], None]) -> AIMessage:
        prompt = REPLY_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False), nights_min=NIGHTS[0],
                                     nights_max=NIGHTS[1], max_travelers=MAX_TRAVELERS)
        text = []
        for chunk in self._reply.stream([SystemMessage(prompt), *messages[-HISTORY:]]):
            piece = chunk.text if isinstance(chunk.text, str) else chunk.text()
            if piece:
                on_token(piece)
                text.append(piece)
        return AIMessage("".join(text))
