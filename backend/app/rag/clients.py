"""The shared Qdrant client, embedder and ranker, created once from the settings."""

from functools import lru_cache

from qdrant_client import QdrantClient

from app.config import get_settings
from app.planner.planner import Ranker
from app.rag.embeddings import FastEmbedder
from app.rag.ranker import semantic_ranker


@lru_cache
def get_qdrant() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url, timeout=10)


@lru_cache
def get_embedder() -> FastEmbedder:
    return FastEmbedder(get_settings().embedding_model)


def get_ranker() -> Ranker:
    return semantic_ranker(get_qdrant(), get_embedder())
