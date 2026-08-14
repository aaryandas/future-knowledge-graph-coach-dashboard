from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

Embedding: TypeAlias = tuple[float, ...]
Pass: TypeAlias = Literal["exact", "fuzzy", "vector", "none"]
TokenAlias: TypeAlias = tuple[tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True)
class VocabularyConcept:
    concept_id: str
    preferred_term: str
    aliases: tuple[str, ...] = ()


class Vocabulary(Protocol):
    def concepts(self) -> Iterable[VocabularyConcept]: ...

    def token_aliases(self) -> Iterable[TokenAlias]: ...

    def embeddings(self) -> Embeddings | None: ...


class Embeddings(Protocol):
    def query(self, text: str) -> Embedding | None: ...

    def concept(self, concept_id: str) -> Embedding | None: ...


@dataclass(frozen=True)
class Candidate:
    concept_id: str
    preferred_term: str
    confidence: float


@dataclass(frozen=True)
class Resolution:
    concept_id: str | None
    confidence: float
    pass_: Pass
    candidates: tuple[Candidate, ...]
    raw_text: str
    modifiers: tuple[str, ...]
