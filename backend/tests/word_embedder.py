"""A tiny deterministic embedder for the tests: no model to download, and similar words give similar vectors."""

import math
import re
import zlib

DIM = 256


class WordEmbedder:
    """Each word longer than 3 letters lights up one dimension; texts sharing words point the same way."""

    dim = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for word in re.findall(r"\w{4,}", text.lower()):
            v[zlib.crc32(word.encode()) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]
