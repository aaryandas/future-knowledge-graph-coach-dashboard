from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

ResolutionMethod: TypeAlias = Literal["exact", "fuzzy", "vector", "none"]


@dataclass(frozen=True)
class VocabularyConcept:
    concept_id: str
    preferred_term: str
    aliases: tuple[str, ...] = ()


class Vocabulary(Protocol):
    def concepts(self) -> Iterable[VocabularyConcept]: ...


@dataclass(frozen=True)
class Candidate:
    concept_id: str
    preferred_term: str
    confidence: float


@dataclass(frozen=True)
class Resolution:
    concept_id: str | None
    confidence: float
    method: ResolutionMethod
    candidates: tuple[Candidate, ...]
    raw_text: str
    modifiers: tuple[str, ...]
