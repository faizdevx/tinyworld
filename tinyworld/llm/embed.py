"""Text embeddings behind a small interface.

``HashEmbedder`` needs no model download and is deterministic, which makes it
the default for tests and offline runs. It captures word and character-trigram
overlap, not meaning. ``SentenceTransformerEmbedder`` is the semantic option
when the ``sentence-transformers`` package is installed.
"""

import re
import zlib
from typing import Protocol

import numpy as np

_WORD = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class HashEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[tuple[str, float]]:
        words = _WORD.findall(text.lower())
        features = [(f"w:{word}", 1.0) for word in words]
        for word in words:
            padded = f"^{word}$"
            features.extend(
                (f"t:{padded[i:i + 3]}", 0.3) for i in range(len(padded) - 2)
            )
        return features

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature, weight in self._features(text):
                digest = zlib.crc32(feature.encode())
                sign = 1.0 if (digest >> 31) & 1 else -1.0
                matrix[row, digest % self.dim] += sign * weight
        return _normalize(matrix)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> np.ndarray:
        return _normalize(np.asarray(self._model.encode(texts), dtype=np.float32))


def to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_bytes(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two already-normalized vectors."""
    return float(np.dot(a, b))
