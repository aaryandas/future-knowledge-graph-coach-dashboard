from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from neo4j import Record

from ._artifacts import KG1NodeKind, _token_aliases
from ._embeddings import ArtifactEmbeddings, EmbeddingProvider
from ._model import Embeddings, TokenAlias, VocabularyConcept


@dataclass(frozen=True)
class StoreVocabulary:
    _concepts: tuple[VocabularyConcept, ...]
    _token_aliases: tuple[TokenAlias, ...]
    _embeddings: Embeddings | None = None

    @classmethod
    def from_store(
        cls,
        *,
        kind: KG1NodeKind,
        synonyms_path: str | Path,
        embeddings: Embeddings | None = None,
        embeddings_path: str | Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> Self:
        if embeddings is not None and embeddings_path is not None:
            raise ValueError("provide embeddings or embeddings_path, not both")
        if embedding_provider is not None and embeddings_path is None:
            raise ValueError("embedding_provider requires embeddings_path")

        from app.graph.store import neo4j_session

        with neo4j_session() as session:
            records = session.run(
                f"MATCH (concept:`{kind}`) "
                "RETURN concept.id AS concept_id, "
                "coalesce(concept.preferred_term, concept.name) AS preferred_term, "
                "coalesce(concept.aliases, []) + coalesce(concept.synonyms, []) "
                "AS aliases "
                "ORDER BY toLower(preferred_term), concept_id"
            )
            concepts = tuple(_concept(record, kind) for record in records)

        synonyms = json.loads(Path(synonyms_path).read_text())
        loaded_embeddings = (
            ArtifactEmbeddings.from_file(
                embeddings_path,
                provider=embedding_provider,
            )
            if embeddings_path is not None
            else embeddings
        )
        return cls(
            _concepts=concepts,
            _token_aliases=_token_aliases(synonyms),
            _embeddings=loaded_embeddings,
        )

    def concepts(self) -> tuple[VocabularyConcept, ...]:
        return self._concepts

    def token_aliases(self) -> tuple[TokenAlias, ...]:
        return self._token_aliases

    def embeddings(self) -> Embeddings | None:
        return self._embeddings


def _concept(record: Record, kind: KG1NodeKind) -> VocabularyConcept:
    concept_id = record["concept_id"]
    preferred_term = record["preferred_term"]
    aliases: Any = record["aliases"]
    if not isinstance(concept_id, str) or not concept_id:
        raise TypeError(f"{kind} store concept requires a non-empty id")
    if not isinstance(preferred_term, str) or not preferred_term:
        raise TypeError(f"{kind} store concept {concept_id} requires a preferred term")
    if not isinstance(aliases, list) or not all(
        isinstance(alias, str) for alias in aliases
    ):
        raise TypeError(f"{kind} store concept {concept_id} aliases must be strings")
    return VocabularyConcept(
        concept_id=concept_id,
        preferred_term=preferred_term,
        aliases=tuple(dict.fromkeys(aliases)),
    )
