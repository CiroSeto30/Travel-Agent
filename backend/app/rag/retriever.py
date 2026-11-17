"""Find the activities of a city that best match what the user wrote."""

from qdrant_client import QdrantClient, models

from app.rag.embeddings import Embedder
from app.rag.index import COLLECTION


def relevant_activities(client: QdrantClient, embedder: Embedder, text: str, *, city: str,
                        limit: int) -> list[tuple[int, float]]:
    """(activity id, similarity) pairs from the most similar, only for activities in `city`."""
    [vector] = embedder.embed([text])
    hits = client.query_points(
        COLLECTION, query=vector, limit=limit,
        query_filter=models.Filter(must=[models.FieldCondition(key="city", match=models.MatchValue(value=city))]),
    ).points
    return [(int(h.id), h.score) for h in hits]