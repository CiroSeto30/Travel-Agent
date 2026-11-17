"""The planner's ranker backed by the RAG: the user's words decide which activities come first."""

import logging

from qdrant_client import QdrantClient

from app.db.models import Activity
from app.planner.planner import Ranker, TripRequest, rank_by_category
from app.rag.embeddings import Embedder
from app.rag.retriever import relevant_activities

log = logging.getLogger(__name__)

CATEGORY_BONUS = 0.1  # a chosen category is worth this much similarity (cosine, from -1 to 1)


def semantic_ranker(client: QdrantClient, embedder: Embedder) -> Ranker:
    def rank(activities: list[Activity], req: TripRequest) -> list[int]:
        if not activities or not req.preferences.strip():
            return rank_by_category(activities, req)
        try:
            similarity = dict(relevant_activities(
                client, embedder, req.preferences, city=activities[0].city, limit=len(activities)))
        except Exception:  # the RAG improves the order; it is never a reason for the search to fail
            log.warning("RAG unavailable, ranking by category", exc_info=True)
            return rank_by_category(activities, req)

        def score(a: Activity) -> float:
            return similarity.get(a.id, -1.0) + CATEGORY_BONUS * (a.category in req.categories)

        return [a.id for a in sorted(activities, key=lambda a: (-score(a), a.id))]

    return rank