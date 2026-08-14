from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Self

from ._model import Embedding

EMBEDDING_SCHEMA_VERSION = 1
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_MODEL = "qwen/qwen3-embedding-0.6b"


class EmbeddingProvider(Protocol):
    def embed(
        self, texts: tuple[str, ...], *, model: str
    ) -> tuple[Embedding, ...] | None: ...


@dataclass(frozen=True)
class ArtifactEmbeddings:
    model: str
    dimensions: int
    _concept_embeddings: dict[str, Embedding]
    _provider: EmbeddingProvider | None = None

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        provider: EmbeddingProvider | None = None,
    ) -> Self:
        artifact = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(artifact, dict):
            raise TypeError("embedding artifact must contain an object")
        if artifact.get("schema_version") != EMBEDDING_SCHEMA_VERSION:
            raise ValueError("embedding artifact has an unsupported schema_version")

        model = artifact.get("model")
        dimensions = artifact.get("dimensions")
        raw_embeddings = artifact.get("embeddings")
        if not isinstance(model, str) or not model:
            raise TypeError("embedding artifact requires a model")
        if (
            not isinstance(dimensions, int)
            or isinstance(dimensions, bool)
            or dimensions < 1
        ):
            raise TypeError("embedding artifact requires positive dimensions")
        if not isinstance(raw_embeddings, dict):
            raise TypeError("embedding artifact requires an embeddings object")

        concept_embeddings = {
            concept_id: _embedding(vector, dimensions)
            for concept_id, vector in raw_embeddings.items()
            if isinstance(concept_id, str)
        }
        if len(concept_embeddings) != len(raw_embeddings):
            raise TypeError("embedding artifact concept ids must be strings")
        return cls(
            model=model,
            dimensions=dimensions,
            _concept_embeddings=concept_embeddings,
            _provider=provider,
        )

    def query(self, text: str) -> Embedding | None:
        if self._provider is None:
            return None
        embeddings = self._provider.embed((text,), model=self.model)
        if embeddings is None or len(embeddings) != 1:
            return None
        return _optional_embedding(embeddings[0], self.dimensions)

    def concept(self, concept_id: str) -> Embedding | None:
        return self._concept_embeddings.get(concept_id)


@dataclass(frozen=True)
class OpenRouterEmbeddingProvider:
    api_key: str | None
    timeout: float = 10.0
    _open_url: Callable[..., Any] = urllib.request.urlopen

    @classmethod
    def from_env(cls) -> Self:
        return cls(api_key=os.environ.get("OPENROUTER_API_KEY"))

    def embed(
        self, texts: tuple[str, ...], *, model: str
    ) -> tuple[Embedding, ...] | None:
        if not self.api_key or not texts:
            return None
        request = urllib.request.Request(
            OPENROUTER_EMBEDDINGS_URL,
            data=json.dumps({"model": model, "input": texts}).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "future-knowledge-graph-resolver/1",
            },
            method="POST",
        )
        try:
            with self._open_url(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
        ):
            return None
        return _response_embeddings(payload, len(texts))


def _response_embeddings(payload: Any, count: int) -> tuple[Embedding, ...] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return None
    records = payload["data"]
    if len(records) != count or not all(isinstance(record, dict) for record in records):
        return None
    by_index = {record.get("index"): record.get("embedding") for record in records}
    if set(by_index) != set(range(count)):
        return None
    embeddings = tuple(
        _unvalidated_embedding(by_index[index]) for index in range(count)
    )
    if any(embedding is None for embedding in embeddings):
        return None
    return tuple(embedding for embedding in embeddings if embedding is not None)


def _embedding(value: Any, dimensions: int) -> Embedding:
    embedding = _optional_embedding(value, dimensions)
    if embedding is None:
        raise ValueError("embedding artifact vectors must be finite and non-zero")
    return embedding


def _optional_embedding(value: Any, dimensions: int) -> Embedding | None:
    embedding = _unvalidated_embedding(value)
    if embedding is None or len(embedding) != dimensions or not any(embedding):
        return None
    return embedding


def _unvalidated_embedding(value: Any) -> Embedding | None:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(component, (int, float))
        and not isinstance(component, bool)
        and math.isfinite(component)
        for component in value
    ):
        return None
    return tuple(float(component) for component in value)
