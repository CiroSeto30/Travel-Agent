"""The Qdrant collection of activities (docs/design.md §5, vector database)."""

from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from app.db.models import Activity
from app.rag.embeddings import Embedder

COLLECTION = "activities"
BATCH = 64

TARGET_LABELS = {"families": "famiglie", "young": "giovani", "couples": "coppie", "sporty": "sportivi"}


def activity_text(a: Activity) -> str:
    return f"{a.name}. {a.description} Ideale per {TARGET_LABELS[a.target]}."


def index_activities(client: QdrantClient, embedder: Embedder, activities: Sequence[Activity]) -> int:
    """Rebuild the collection from scratch: one point per activity, with the activity id as point id."""
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        COLLECTION, vectors_config=models.VectorParams(size=embedder.dim, distance=models.Distance.COSINE))
    for field in ("country", "city", "category"):
        client.create_payload_index(COLLECTION, field, models.PayloadSchemaType.KEYWORD)

    for start in range(0, len(activities), BATCH):
        batch = activities[start:start + BATCH]
        vectors = embedder.embed([activity_text(a) for a in batch])
        client.upsert(COLLECTION, [
                models.PointStruct(id=a.id, vector=v, payload={
                "activity_id": a.id, "name": a.name, "description": a.description, "country": a.country,
                "city": a.city, "category": a.category, "target": a.target, "price": float(a.price)})
            for a, v in zip(batch, vectors)
        ])
    return client.count(COLLECTION).count