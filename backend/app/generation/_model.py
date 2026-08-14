from dataclasses import dataclass
from typing import Literal

from app.resolver import Resolution
from app.safety import Verdict

type Section = Literal["warm-up", "main", "cool-down"]
type ResolutionPurpose = Literal[
    "target",
    "exclusion",
    "session injury",
    "equipment override",
]
type ResolutionVocabulary = Literal[
    "Exercise",
    "MuscleGroup",
    "Joint",
    "MovementPattern",
    "Equipment",
    "AnatomicalStructure",
    "ClinicalFinding",
]
type GenerationFailureReason = Literal[
    "llm-unavailable",
    "provider-error",
    "invalid-output",
    "member-not-found",
    "empty-section",
    "minimum-plan-exceeds-window",
]


@dataclass(frozen=True)
class ResolvedMention:
    purpose: ResolutionPurpose
    vocabulary: ResolutionVocabulary
    resolution: Resolution
    enforced: bool
    message: str | None = None


@dataclass(frozen=True)
class ConstraintSet:
    exclusions: tuple[ResolvedMention, ...]
    session_injuries: tuple[ResolvedMention, ...]
    equipment_override: tuple[ResolvedMention, ...] | None


@dataclass(frozen=True)
class ResolvedIntent:
    targets: tuple[ResolvedMention, ...]
    constraints: ConstraintSet


@dataclass(frozen=True)
class GenerationFailure:
    reason: GenerationFailureReason
    message: str
    section: Section | None = None
    attempts: int | None = None


@dataclass(frozen=True)
class CatalogExercise:
    exercise_id: str
    name: str
    movement_patterns: tuple[str, ...]
    movement_pattern_ids: tuple[str, ...]
    muscle_groups: tuple[str, ...]
    muscle_group_ids: tuple[str, ...]
    joint_ids: tuple[str, ...]
    equipment_ids: tuple[str, ...]
    priority_tier: int
    is_reps: bool
    is_duration: bool
    supports_weight: bool
    estimated_rep_duration: float
    is_bilateral: bool
    side: str | None
    bilateral_pair_id: str | None


@dataclass(frozen=True)
class GenerationMemberContext:
    equipment_ids: tuple[str, ...]
    disliked_exercise_ids: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    exercise_id: str
    name: str
    movement_patterns: tuple[str, ...]
    muscle_groups: tuple[str, ...]
    priority_tier: int
    is_reps: bool
    is_duration: bool
    supports_weight: bool
    estimated_rep_duration: float
    is_bilateral: bool
    side: str | None
    bilateral_pair_id: str | None
    verdict: Verdict
    goal_match: bool = False
    disliked: bool = False
    has_required_equipment: bool = True
    explicitly_excluded: bool = False


@dataclass(frozen=True)
class PlanEntry:
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


@dataclass(frozen=True)
class PlanSection:
    section: Section
    entries: tuple[PlanEntry, ...]
    minutes: float


@dataclass(frozen=True)
class Plan:
    warm_up: PlanSection
    main: PlanSection
    cool_down: PlanSection
    requested_minutes: int
    packed_minutes: float
