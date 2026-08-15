from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.generation._model import (
    ConstraintSet,
    DerivedExclusionRule,
    ResolutionPurpose,
    ResolutionVocabulary,
    ResolvedIntent,
    ResolvedMention,
)
from app.generation._trace import ResolutionTraceEvent
from app.generation.intent import Intent
from app.graph import get_exercise_movement_pattern_ids
from app.resolver import (
    ArtifactVocabulary,
    Resolution,
    VocabularyConcept,
    resolve,
)

_DATA_DIRECTORY = Path(__file__).resolve().parents[3] / "data"
type TokenAlias = tuple[tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True)
class _GenerationVocabulary:
    _concepts: tuple[VocabularyConcept, ...]
    _token_aliases: tuple[TokenAlias, ...]
    _kind_by_concept_id: dict[str, ResolutionVocabulary]
    _unresolved_kind: ResolutionVocabulary

    def concepts(self) -> Iterable[VocabularyConcept]:
        return self._concepts

    def token_aliases(self) -> Iterable[TokenAlias]:
        return self._token_aliases

    def embeddings(self) -> None:
        return None

    def kind_for(self, resolution: Resolution) -> ResolutionVocabulary:
        if resolution.concept_id is None:
            return self._unresolved_kind
        return self._kind_by_concept_id[resolution.concept_id]

    def derived_exclusion_rule(
        self, resolution: Resolution
    ) -> DerivedExclusionRule | None:
        if (
            resolution.concept_id is None
            or resolution.pass_ == "exact"
            or self.kind_for(resolution) != "Exercise"
        ):
            return None

        exercise_ids = (
            resolution.concept_id,
            *(
                candidate.concept_id
                for candidate in resolution.candidates
                if candidate.confidence == resolution.confidence
                and self._kind_by_concept_id[candidate.concept_id] == "Exercise"
            ),
        )
        movement_pattern_sets = tuple(
            get_exercise_movement_pattern_ids(exercise_id)
            for exercise_id in exercise_ids
        )
        if len(movement_pattern_sets) < 2 or not all(movement_pattern_sets):
            return None

        shared_movement_pattern_ids = frozenset.intersection(*movement_pattern_sets)
        if len(shared_movement_pattern_ids) != 1:
            return None
        return DerivedExclusionRule(
            vocabulary="MovementPattern",
            concept_id=next(iter(shared_movement_pattern_ids)),
        )


@dataclass(frozen=True)
class GenerationVocabularies:
    targets: _GenerationVocabulary
    exclusions: _GenerationVocabulary
    session_injuries: _GenerationVocabulary
    equipment_override: _GenerationVocabulary


def resolve_intent(
    intent: Intent,
    vocabularies: GenerationVocabularies | None = None,
) -> tuple[ResolvedIntent, tuple[ResolutionTraceEvent, ...]]:
    generation_vocabularies = vocabularies or load_generation_vocabularies()
    targets, target_events = _resolve_mentions(
        intent.targets,
        purpose="target",
        vocabulary=generation_vocabularies.targets,
        enforce_matches=True,
    )
    exclusions, exclusion_events = _resolve_mentions(
        intent.exclusions,
        purpose="exclusion",
        vocabulary=generation_vocabularies.exclusions,
        enforce_matches=True,
    )
    session_injuries, injury_events = _resolve_mentions(
        intent.injuries,
        purpose="session injury",
        vocabulary=generation_vocabularies.session_injuries,
        enforce_matches=True,
    )
    equipment_override: tuple[ResolvedMention, ...] | None = None
    equipment_events: tuple[ResolutionTraceEvent, ...] = ()
    if intent.equipment:
        equipment_override, equipment_events = _resolve_mentions(
            intent.equipment,
            purpose="equipment override",
            vocabulary=generation_vocabularies.equipment_override,
            enforce_matches=True,
        )

    return (
        ResolvedIntent(
            targets=targets,
            constraints=ConstraintSet(
                exclusions=exclusions,
                session_injuries=session_injuries,
                equipment_override=equipment_override,
            ),
        ),
        (*target_events, *exclusion_events, *injury_events, *equipment_events),
    )


@lru_cache(maxsize=1)
def load_generation_vocabularies() -> GenerationVocabularies:
    exercises_path = _DATA_DIRECTORY / "exercises.json"
    snomed_path = _DATA_DIRECTORY / "ontology" / "snomed-ct.json"
    synonyms_path = _DATA_DIRECTORY / "synonyms.json"
    exercise = _artifact_vocabulary(exercises_path, "Exercise", synonyms_path)
    muscle_group = _artifact_vocabulary(exercises_path, "MuscleGroup", synonyms_path)
    joint = _artifact_vocabulary(exercises_path, "Joint", synonyms_path)
    movement_pattern = _artifact_vocabulary(
        exercises_path, "MovementPattern", synonyms_path
    )
    equipment = _artifact_vocabulary(exercises_path, "Equipment", synonyms_path)
    anatomical_structure = _artifact_vocabulary(
        snomed_path, "AnatomicalStructure", synonyms_path
    )
    clinical_finding = _artifact_vocabulary(
        snomed_path, "ClinicalFinding", synonyms_path
    )
    return GenerationVocabularies(
        targets=_combine((muscle_group, joint), unresolved_kind="MuscleGroup"),
        exclusions=_combine(
            (exercise, movement_pattern),
            unresolved_kind="Exercise",
        ),
        session_injuries=_combine(
            (clinical_finding, joint, anatomical_structure),
            unresolved_kind="ClinicalFinding",
        ),
        equipment_override=_combine((equipment,), unresolved_kind="Equipment"),
    )


def _artifact_vocabulary(
    path: Path,
    kind: ResolutionVocabulary,
    synonyms_path: Path,
) -> tuple[ResolutionVocabulary, ArtifactVocabulary]:
    return kind, ArtifactVocabulary.from_file(
        path,
        kind=kind,
        synonyms_path=synonyms_path,
    )


def _combine(
    vocabularies: tuple[tuple[ResolutionVocabulary, ArtifactVocabulary], ...],
    *,
    unresolved_kind: ResolutionVocabulary,
) -> _GenerationVocabulary:
    concepts: list[VocabularyConcept] = []
    token_aliases: list[TokenAlias] = []
    kind_by_concept_id: dict[str, ResolutionVocabulary] = {}
    for kind, vocabulary in vocabularies:
        for concept in vocabulary.concepts():
            concepts.append(concept)
            kind_by_concept_id[concept.concept_id] = kind
        token_aliases.extend(vocabulary.token_aliases())
    return _GenerationVocabulary(
        _concepts=tuple(concepts),
        _token_aliases=tuple(dict.fromkeys(token_aliases)),
        _kind_by_concept_id=kind_by_concept_id,
        _unresolved_kind=unresolved_kind,
    )


def _resolve_mentions(
    mentions: tuple[str, ...],
    *,
    purpose: ResolutionPurpose,
    vocabulary: _GenerationVocabulary,
    enforce_matches: bool,
) -> tuple[tuple[ResolvedMention, ...], tuple[ResolutionTraceEvent, ...]]:
    resolved_mentions: list[ResolvedMention] = []
    events: list[ResolutionTraceEvent] = []
    for mention in mentions:
        resolution = resolve(mention, vocabulary)
        derived_exclusion_rule = (
            vocabulary.derived_exclusion_rule(resolution)
            if purpose == "exclusion"
            else None
        )
        resolution_kind = vocabulary.kind_for(resolution)
        enforced = enforce_matches and resolution.concept_id is not None
        message = _resolution_message(purpose, resolution, enforced)
        resolved_mentions.append(
            ResolvedMention(
                purpose=purpose,
                vocabulary=resolution_kind,
                resolution=resolution,
                enforced=enforced,
                message=message,
                derived_exclusion_rule=derived_exclusion_rule,
            )
        )
        events.append(
            ResolutionTraceEvent(
                purpose=purpose,
                vocabulary=resolution_kind,
                raw_text=resolution.raw_text,
                concept_id=resolution.concept_id,
                confidence=resolution.confidence,
                pass_=resolution.pass_,
                candidates=resolution.candidates,
                modifiers=resolution.modifiers,
                enforced=enforced,
                reason=message,
                used=(mention,),
            )
        )
    return tuple(resolved_mentions), tuple(events)


def _resolution_message(
    purpose: ResolutionPurpose,
    resolution: Resolution,
    enforced: bool,
) -> str:
    if resolution.concept_id is None:
        suffix = " Safety was not enforced." if purpose == "session injury" else ""
        return f"The {purpose} mention did not resolve.{suffix}"
    if purpose == "session injury":
        return (
            "The session injury is enforced for this session. "
            "Coach confirmation is required to add it to the member record."
        )
    return f"The {purpose} mention resolved with the {resolution.pass_} pass."
