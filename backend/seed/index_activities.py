"""Index the catalog's activities in Qdrant. Run after load_db: python -m seed.index_activities"""

from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Activity
from app.rag.embeddings import Embedder
from app.rag.index import COLLECTION, index_activities


def index_catalog(session: Session, client: QdrantClient, embedder: Embedder) -> int | None:
    """Index every activity; None when the collection already holds one point per activity."""
    activities = list(session.scalars(select(Activity).order_by(Activity.id)))
    if client.collection_exists(COLLECTION) and client.count(COLLECTION).count == len(activities):
        return None
    return index_activities(client, embedder, activities)


def main() -> None:
    from app.db.session import SessionLocal
    from app.rag.clients import get_embedder, get_qdrant

    with SessionLocal() as session:
        indexed = index_catalog(session, get_qdrant(), get_embedder())
    print("Activities already indexed, nothing to do" if indexed is None else f"Indexed {indexed} activities")


if __name__ == "__main__":
    main()
