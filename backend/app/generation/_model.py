from dataclasses import dataclass
from typing import Literal

from app.safety import Verdict

type Section = Literal["warm-up", "main", "cool-down"]


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
