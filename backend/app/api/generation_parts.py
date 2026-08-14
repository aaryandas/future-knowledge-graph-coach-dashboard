from __future__ import annotations

from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from app.generation import GenerationTurn
from app.graph import GraphEdgeKind, GraphNodeKind
from app.resolver import Pass


class ResolutionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    concept_id: str
    preferred_term: str
    confidence: float


class ResolvedMention(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    purpose: Literal[
        "target",
        "exclusion",
        "session injury",
        "equipment override",
    ]
    vocabulary: Literal[
        "Exercise",
        "MuscleGroup",
        "Joint",
        "MovementPattern",
        "Equipment",
        "AnatomicalStructure",
        "ClinicalFinding",
    ]
    raw_text: str
    concept_id: str | None
    confidence: float
    pass_: Pass = Field(alias="pass")
    candidates: list[ResolutionCandidate]
    modifiers: list[str]
    enforced: bool
    message: str | None


class ConstraintSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    exclusions: list[ResolvedMention]
    session_injuries: list[ResolvedMention]
    equipment_override: list[ResolvedMention] | None


class GenerationFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: Literal[
        "llm-unavailable",
        "provider-error",
        "invalid-output",
        "member-not-found",
        "empty-section",
        "minimum-plan-exceeds-window",
    ]
    message: str
    section: Literal["warm-up", "main", "cool-down"] | None
    attempts: int | None


class PlanEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    exercise_id: str
    name: str
    sets: int
    reps: int | None
    hold_minutes: float | None
    rest_minutes: float
    per_side: bool
    supports_weight: bool
    verdict: Literal["exclude", "caution", "clear"]
    caution_note: str | None
    minutes: float


class PlanSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    section: Literal["warm-up", "main", "cool-down"]
    entries: list[PlanEntry]
    minutes: float


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)

    warm_up: PlanSection
    main: PlanSection
    cool_down: PlanSection
    requested_minutes: int
    packed_minutes: float


class DataPlanPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-plan"] = "data-plan"
    id: Literal["generation-plan"] = "generation-plan"
    data: Plan


class WalkedNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    kind: GraphNodeKind
    name: str | None


class WalkedEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    edge_id: str
    kind: GraphEdgeKind
    source_id: str
    target_id: str


class WalkedPath(BaseModel):
    model_config = ConfigDict(frozen=True)

    nodes: list[WalkedNode]
    edges: list[WalkedEdge]


class ResolutionTraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    kind: Literal["resolution"] = "resolution"
    purpose: Literal[
        "target",
        "exclusion",
        "session injury",
        "equipment override",
    ]
    vocabulary: Literal[
        "Exercise",
        "MuscleGroup",
        "Joint",
        "MovementPattern",
        "Equipment",
        "AnatomicalStructure",
        "ClinicalFinding",
    ]
    raw_text: str
    concept_id: str | None
    confidence: float
    pass_: Pass = Field(alias="pass")
    candidates: list[ResolutionCandidate]
    modifiers: list[str]
    enforced: bool
    reason: str
    used: list[str]
    was_generated_by: Literal["resolve"] = Field(alias="wasGeneratedBy")
    was_attributed_to: Literal["graph"] = Field(alias="wasAttributedTo")


class VerdictTraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    kind: Literal["verdict"] = "verdict"
    exercise_id: str
    status: Literal["exclude", "caution", "clear"]
    layer: (
        Literal[
            "clinical directive",
            "contraindication",
            "SNOMED anatomical fallback",
        ]
        | None
    )
    reason: str
    walked_path: WalkedPath
    used: list[str]
    was_generated_by: Literal["evaluate_safety"] = Field(alias="wasGeneratedBy")
    was_attributed_to: Literal["graph", "agent"] = Field(alias="wasAttributedTo")


class PackingTraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    kind: Literal["packing"] = "packing"
    action: Literal["filtered", "selected", "cut"]
    section: Literal["warm-up", "main", "cool-down"] | None
    exercise_id: str
    reason: str
    used: list[str]
    score: int | None
    was_generated_by: Literal["pack"] = Field(alias="wasGeneratedBy")
    was_attributed_to: Literal["graph"] = Field(alias="wasAttributedTo")


class SubstitutionTraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    kind: Literal["substitution"] = "substitution"
    dropped_exercise_id: str
    replacement_exercise_id: str
    basis: Literal["movement pattern", "muscle overlap"]
    shared_movement_pattern_ids: list[str]
    shared_muscle_group_ids: list[str]
    reason: str
    used: list[str]
    was_generated_by: Literal["pair_substitutions"] = Field(alias="wasGeneratedBy")
    was_attributed_to: Literal["graph"] = Field(alias="wasAttributedTo")


type TraceEvent = Annotated[
    ResolutionTraceEvent
    | VerdictTraceEvent
    | PackingTraceEvent
    | SubstitutionTraceEvent,
    Field(discriminator="kind"),
]


class DataTracePart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-trace"] = "data-trace"
    id: Literal["generation-trace"] = "generation-trace"
    data: list[TraceEvent]


class OmissionChip(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_text: str
    purpose: Literal["target", "exclusion", "equipment override"]
    candidates: list[ResolutionCandidate]
    message: str


class NotEnforcedFlag(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_text: str
    purpose: Literal["session injury"] = "session injury"
    candidates: list[ResolutionCandidate]
    message: str


class SessionInjuryPersistenceSuggestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_text: str
    concept_id: str
    vocabulary: Literal["Joint", "AnatomicalStructure", "ClinicalFinding"]
    action: Literal["persist session injury"] = "persist session injury"
    requires_confirmation: Literal[True] = True
    message: str


class ConstraintsData(BaseModel):
    model_config = ConfigDict(frozen=True)

    targets: list[ResolvedMention]
    constraints: ConstraintSet
    omissions: list[OmissionChip]
    not_enforced: list[NotEnforcedFlag]
    session_injury_persistence_suggestions: list[SessionInjuryPersistenceSuggestion]
    failure: GenerationFailure | None


class DataConstraintsPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-constraints"] = "data-constraints"
    id: Literal["generation-constraints"] = "generation-constraints"
    data: ConstraintsData


type GenerationDataPart = DataPlanPart | DataTracePart | DataConstraintsPart


def generation_data_parts(turn: GenerationTurn) -> tuple[GenerationDataPart, ...]:
    return (
        *((_data_plan_part(turn.plan),) if turn.plan is not None else ()),
        _data_trace_part(turn.trace),
        _data_constraints_part(turn),
    )


def _data_plan_part(plan) -> DataPlanPart:
    return DataPlanPart(
        data=Plan(
            warm_up=_plan_section(plan.warm_up),
            main=_plan_section(plan.main),
            cool_down=_plan_section(plan.cool_down),
            requested_minutes=plan.requested_minutes,
            packed_minutes=plan.packed_minutes,
        )
    )


def _data_trace_part(events) -> DataTracePart:
    return DataTracePart(data=[_trace_event(event) for event in events])


def _data_constraints_part(turn) -> DataConstraintsPart:
    resolved_intent = turn.resolved_intent
    failure = turn.failure
    constraint_set = (
        resolved_intent.constraints if resolved_intent is not None else None
    )
    return DataConstraintsPart(
        data=ConstraintsData(
            targets=(
                [_resolved_mention(mention) for mention in resolved_intent.targets]
                if resolved_intent is not None
                else []
            ),
            constraints=ConstraintSet(
                exclusions=(
                    [
                        _resolved_mention(mention)
                        for mention in constraint_set.exclusions
                    ]
                    if constraint_set is not None
                    else []
                ),
                session_injuries=(
                    [
                        _resolved_mention(mention)
                        for mention in constraint_set.session_injuries
                    ]
                    if constraint_set is not None
                    else []
                ),
                equipment_override=(
                    [
                        _resolved_mention(mention)
                        for mention in constraint_set.equipment_override
                    ]
                    if constraint_set is not None
                    and constraint_set.equipment_override is not None
                    else None
                ),
            ),
            omissions=_omission_chips(resolved_intent),
            not_enforced=_not_enforced_flags(resolved_intent),
            session_injury_persistence_suggestions=(
                _session_injury_persistence_suggestions(resolved_intent)
            ),
            failure=(
                GenerationFailure(
                    reason=failure.reason,
                    message=failure.message,
                    section=failure.section,
                    attempts=failure.attempts,
                )
                if failure is not None
                else None
            ),
        )
    )


def _plan_section(section) -> PlanSection:
    return PlanSection(
        section=section.section,
        entries=[
            PlanEntry(
                exercise_id=entry.exercise_id,
                name=entry.name,
                sets=entry.sets,
                reps=entry.reps,
                hold_minutes=entry.hold_minutes,
                rest_minutes=entry.rest_minutes,
                per_side=entry.per_side,
                supports_weight=entry.supports_weight,
                verdict=entry.verdict,
                caution_note=entry.caution_note,
                minutes=entry.minutes,
            )
            for entry in section.entries
        ],
        minutes=section.minutes,
    )


def _resolved_mention(mention) -> ResolvedMention:
    resolution = mention.resolution
    return ResolvedMention(
        purpose=mention.purpose,
        vocabulary=mention.vocabulary,
        raw_text=resolution.raw_text,
        concept_id=resolution.concept_id,
        confidence=resolution.confidence,
        pass_=resolution.pass_,
        candidates=[
            _resolution_candidate(candidate) for candidate in resolution.candidates
        ],
        modifiers=list(resolution.modifiers),
        enforced=mention.enforced,
        message=mention.message,
    )


def _resolution_candidate(candidate) -> ResolutionCandidate:
    return ResolutionCandidate(
        concept_id=candidate.concept_id,
        preferred_term=candidate.preferred_term,
        confidence=candidate.confidence,
    )


def _omission_chips(resolved_intent) -> list[OmissionChip]:
    if resolved_intent is None:
        return []
    constraints = resolved_intent.constraints
    mentions = (
        *resolved_intent.targets,
        *constraints.exclusions,
        *(constraints.equipment_override or ()),
    )
    return [
        OmissionChip(
            raw_text=mention.resolution.raw_text,
            purpose=cast(
                Literal["target", "exclusion", "equipment override"],
                mention.purpose,
            ),
            candidates=[
                _resolution_candidate(candidate)
                for candidate in mention.resolution.candidates
            ],
            message=mention.message or "The generator term was omitted.",
        )
        for mention in mentions
        if mention.resolution.concept_id is None
    ]


def _not_enforced_flags(resolved_intent) -> list[NotEnforcedFlag]:
    if resolved_intent is None:
        return []
    return [
        NotEnforcedFlag(
            raw_text=mention.resolution.raw_text,
            candidates=[
                _resolution_candidate(candidate)
                for candidate in mention.resolution.candidates
            ],
            message=mention.message or "Safety was not enforced.",
        )
        for mention in resolved_intent.constraints.session_injuries
        if not mention.enforced
    ]


def _session_injury_persistence_suggestions(
    resolved_intent,
) -> list[SessionInjuryPersistenceSuggestion]:
    if resolved_intent is None:
        return []
    suggestions: list[SessionInjuryPersistenceSuggestion] = []
    for mention in resolved_intent.constraints.session_injuries:
        concept_id = mention.resolution.concept_id
        if not mention.enforced or concept_id is None:
            continue
        suggestions.append(
            SessionInjuryPersistenceSuggestion(
                raw_text=mention.resolution.raw_text,
                concept_id=concept_id,
                vocabulary=cast(
                    Literal["Joint", "AnatomicalStructure", "ClinicalFinding"],
                    mention.vocabulary,
                ),
                message=(
                    mention.message
                    or "Coach confirmation is required to add this injury."
                ),
            )
        )
    return suggestions


def _trace_event(event) -> TraceEvent:
    if event.kind == "resolution":
        return ResolutionTraceEvent(
            purpose=event.purpose,
            vocabulary=event.vocabulary,
            raw_text=event.raw_text,
            concept_id=event.concept_id,
            confidence=event.confidence,
            pass_=event.pass_,
            candidates=[
                _resolution_candidate(candidate) for candidate in event.candidates
            ],
            modifiers=list(event.modifiers),
            enforced=event.enforced,
            reason=event.reason,
            used=list(event.used),
            was_generated_by=event.was_generated_by,
            was_attributed_to=event.was_attributed_to,
        )
    if event.kind == "verdict":
        return VerdictTraceEvent(
            exercise_id=event.exercise_id,
            status=event.status,
            layer=event.layer,
            reason=event.reason,
            walked_path=WalkedPath(
                nodes=[
                    WalkedNode(
                        node_id=node.node_id,
                        kind=node.kind,
                        name=node.name,
                    )
                    for node in event.walked_path.nodes
                ],
                edges=[
                    WalkedEdge(
                        edge_id=edge.edge_id,
                        kind=edge.kind,
                        source_id=edge.source_id,
                        target_id=edge.target_id,
                    )
                    for edge in event.walked_path.edges
                ],
            ),
            used=list(event.used),
            was_generated_by=event.was_generated_by,
            was_attributed_to=event.was_attributed_to,
        )
    if event.kind == "packing":
        return PackingTraceEvent(
            action=event.action,
            section=event.section,
            exercise_id=event.exercise_id,
            reason=event.reason,
            used=list(event.used),
            score=event.score,
            was_generated_by=event.was_generated_by,
            was_attributed_to=event.was_attributed_to,
        )
    if event.kind == "substitution":
        return SubstitutionTraceEvent(
            dropped_exercise_id=event.dropped_exercise_id,
            replacement_exercise_id=event.replacement_exercise_id,
            basis=event.basis,
            shared_movement_pattern_ids=list(event.shared_movement_pattern_ids),
            shared_muscle_group_ids=list(event.shared_muscle_group_ids),
            reason=event.reason,
            used=list(event.used),
            was_generated_by=event.was_generated_by,
            was_attributed_to=event.was_attributed_to,
        )
    raise RuntimeError("Generation trace contains an unknown event")
