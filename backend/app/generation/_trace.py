from dataclasses import dataclass, field
from typing import Literal

from app.generation._model import Section
from app.resolver import Candidate as ResolutionCandidate
from app.resolver import Pass
from app.safety import VerdictTraceEvent

type PackingAction = Literal["filtered", "selected", "cut"]
type SubstitutionBasis = Literal["movement pattern", "muscle overlap"]


@dataclass(frozen=True)
class ResolutionTraceEvent:
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
    pass_: Pass
    candidates: tuple[ResolutionCandidate, ...]
    modifiers: tuple[str, ...]
    enforced: bool
    reason: str
    used: tuple[str, ...]
    kind: Literal["resolution"] = field(default="resolution", init=False)
    was_generated_by: Literal["resolve"] = field(default="resolve", init=False)
    was_attributed_to: Literal["graph"] = field(default="graph", init=False)


@dataclass(frozen=True)
class PackingTraceEvent:
    action: PackingAction
    section: Section | None
    exercise_id: str
    reason: str
    used: tuple[str, ...]
    score: int | None = None
    kind: Literal["packing"] = field(default="packing", init=False)
    was_generated_by: Literal["pack"] = field(default="pack", init=False)
    was_attributed_to: Literal["graph"] = field(default="graph", init=False)


@dataclass(frozen=True)
class AgentTraceEvent:
    action: Literal["annotation"]
    reason: str
    used: tuple[str, ...]
    kind: Literal["agent"] = field(default="agent", init=False)
    was_generated_by: Literal["annotate"] = field(default="annotate", init=False)
    was_attributed_to: Literal["agent"] = field(default="agent", init=False)


@dataclass(frozen=True)
class SubstitutionTraceEvent:
    dropped_exercise_id: str
    replacement_exercise_id: str
    basis: SubstitutionBasis
    shared_movement_pattern_ids: tuple[str, ...]
    shared_muscle_group_ids: tuple[str, ...]
    reason: str
    used: tuple[str, ...]
    kind: Literal["substitution"] = field(default="substitution", init=False)
    was_generated_by: Literal["pair_substitutions"] = field(
        default="pair_substitutions", init=False
    )
    was_attributed_to: Literal["graph"] = field(default="graph", init=False)


type TraceEvent = (
    ResolutionTraceEvent
    | VerdictTraceEvent
    | PackingTraceEvent
    | AgentTraceEvent
    | SubstitutionTraceEvent
)
