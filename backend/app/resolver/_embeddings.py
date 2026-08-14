from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Self

from openai import OpenAIError

from ._model import Embedding

EMBEDDING_SCHEMA_VERSION = 1


class EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> Sequence[float] | None: ...


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
        try:
            embedding = self._provider.embed_query(text)
        except (ConnectionError, OpenAIError, TimeoutError):
            return None
        if embedding is None:
            return None
        return _optional_embedding(embedding, self.dimensions)

    def concept(self, concept_id: str) -> Embedding | None:
        return self._concept_embeddings.get(concept_id)


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
