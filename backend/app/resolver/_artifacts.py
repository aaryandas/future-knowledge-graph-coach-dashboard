from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self, TypeAlias

from ._model import TokenAlias, VocabularyConcept

KG1NodeKind: TypeAlias = Literal[
    "Exercise",
    "MuscleGroup",
    "Joint",
    "MovementPattern",
    "Equipment",
    "Injury",
    "AnatomicalStructure",
    "ClinicalFinding",
]

_EXERCISE_KIND: KG1NodeKind = "Exercise"
_EXERCISE_FACETS: dict[KG1NodeKind, tuple[str, str]] = {
    "MuscleGroup": ("muscle_groups", "muscle-group"),
    "Joint": ("joints_loaded", "joint"),
    "MovementPattern": ("movement_patterns", "movement-pattern"),
    "Equipment": ("equipment_required", "equipment"),
}
_SLUG_CHARACTER = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ArtifactVocabulary:
    _concepts: tuple[VocabularyConcept, ...]
    _token_aliases: tuple[TokenAlias, ...]

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        kind: KG1NodeKind,
        synonyms_path: str | Path,
    ) -> Self:
        artifact = json.loads(Path(path).read_text())
        synonyms = json.loads(Path(synonyms_path).read_text())
        concepts = (
            _exercise_concepts(artifact, kind)
            if isinstance(artifact, list)
            else _ontology_concepts(artifact, kind)
        )
        return cls(
            _concepts=tuple(concepts),
            _token_aliases=_token_aliases(synonyms),
        )

    def concepts(self) -> Iterable[VocabularyConcept]:
        return self._concepts

    def token_aliases(self) -> Iterable[TokenAlias]:
        return self._token_aliases


def _exercise_concepts(artifact: Any, kind: KG1NodeKind) -> Iterable[VocabularyConcept]:
    if not isinstance(artifact, list):
        raise TypeError("exercise artifact must contain a list")
    if kind == _EXERCISE_KIND:
        for record in artifact:
            yield VocabularyConcept(
                concept_id=_required_string(record, "id"),
                preferred_term=_required_string(record, "name"),
            )
        return

    facet = _EXERCISE_FACETS.get(kind)
    if facet is None:
        raise ValueError(f"unsupported exercise vocabulary kind: {kind}")
    field, id_segment = facet
    terms = {
        term for record in artifact for term in _required_string_list(record, field)
    }
    for term in sorted(terms, key=str.lower):
        yield VocabularyConcept(
            concept_id=f"fkg:{id_segment}/{_slug(term)}",
            preferred_term=term,
        )


def _ontology_concepts(artifact: Any, kind: KG1NodeKind) -> Iterable[VocabularyConcept]:
    if not isinstance(artifact, dict):
        raise TypeError("ontology artifact must contain an object")
    records = next(
        (
            collection
            for key in ("concepts", "classes", "terms")
            if isinstance((collection := artifact.get(key)), list)
        ),
        None,
    )
    if records is None:
        raise ValueError("ontology artifact has no concept collection")
    for record in records:
        if not isinstance(record, dict) or record.get("kind") != kind:
            continue
        yield VocabularyConcept(
            concept_id=_required_string(record, "id"),
            preferred_term=_required_string(record, "preferred_term"),
            aliases=_aliases(record),
        )


def _aliases(record: dict[str, Any]) -> tuple[str, ...]:
    aliases = _optional_string_list(record, "aliases")
    synonyms = _optional_string_list(record, "synonyms")
    return tuple(dict.fromkeys((*aliases, *synonyms)))


def _token_aliases(artifact: Any) -> tuple[TokenAlias, ...]:
    if not isinstance(artifact, dict) or not all(
        isinstance(alias, str) and isinstance(replacement, str)
        for alias, replacement in artifact.items()
    ):
        raise TypeError("synonyms artifact must map strings to strings")
    return tuple(
        (tuple(alias.split()), tuple(replacement.split()))
        for alias, replacement in artifact.items()
    )


def _required_string(record: Any, field: str) -> str:
    if not isinstance(record, dict) or not isinstance(
        (value := record.get(field)), str
    ):
        raise TypeError(f"artifact record requires string field {field!r}")
    return value


def _required_string_list(record: Any, field: str) -> tuple[str, ...]:
    if not isinstance(record, dict) or not isinstance(record.get(field), list):
        raise TypeError(f"artifact record requires list field {field!r}")
    return _string_list(record[field], field)


def _optional_string_list(record: dict[str, Any], field: str) -> tuple[str, ...]:
    values = record.get(field, [])
    if not isinstance(values, list):
        raise TypeError(f"artifact record field {field!r} must be a list")
    return _string_list(values, field)


def _string_list(values: list[Any], field: str) -> tuple[str, ...]:
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"artifact record field {field!r} must contain strings")
    return tuple(values)


def _slug(term: str) -> str:
    return _SLUG_CHARACTER.sub("-", term.lower()).strip("-")
