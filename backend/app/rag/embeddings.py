"""Turn text into vectors. The RAG code depends on the Embedder shape, so the tests can pass a lighter one."""

from typing import Protocol

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedder:
    """A local multilingual model run by fastembed: no API key; Italian and English text in the same space."""

    dim = 384

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:  # loaded on first use: about 220 MB, downloaded once and then cached
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self.model_name)
        return [v.tolist() for v in self._model.embed(texts)]
