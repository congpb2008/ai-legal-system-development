from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

import httpx
import numpy as np
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.runtime_config import get_effective_embedding_config
from app.services.text import tokenize


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local fallback.

    This is not a semantic model. It exists so ingestion, indexing, and tests work
    without downloading a model or calling an API. Production should use an
    OpenAI-compatible embedding endpoint or a local sentence-transformer.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vector = np.zeros(self.dim, dtype=np.float32)
        counts: dict[str, int] = {}
        for token in tokenize(text):
            counts[token] = counts.get(token, 0) + 1
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dim
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign * (1.0 + math.log(count))
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str, api_key: str, model: str, dim: int = 384) -> None:
        base = base_url.rstrip("/")
        self.endpoint = base if base.endswith("/embeddings") else f"{base}/embeddings"
        self.api_key = api_key
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            self.endpoint,
            headers=headers,
            json={"model": self.model, "input": texts},
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload["data"], key=lambda item: item.get("index", 0))
        vectors = [item["embedding"] for item in data]
        if vectors:
            self.dim = len(vectors[0])
        return vectors


def get_embedding_provider(db: Session | None = None) -> EmbeddingProvider:
    config = get_effective_embedding_config(db)
    provider = (config.get("provider") or "hash").lower()
    if provider == "openai" and config.get("base_url"):
        return OpenAIEmbeddingProvider(
            config.get("base_url") or "",
            config.get("api_key") or "",
            config.get("model") or "text-embedding-3-small",
            int(config.get("dim") or 384),
        )
    return HashEmbeddingProvider(int(config.get("dim") or 384))
