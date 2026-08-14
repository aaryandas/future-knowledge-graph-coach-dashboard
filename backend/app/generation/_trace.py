from dataclasses import dataclass, field
from typing import Literal

from app.generation._model import Section
from app.resolver import Candidate as ResolutionCandidate
from app.resolver import Pass
from app.safety import WalkedPath

type PackingAction = Literal["filtered", "selected", "cut"]


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
class VerdictTraceEvent:
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
    used: tuple[str, ...]
    kind: Literal["verdict"] = field(default="verdict", init=False)
    was_generated_by: Literal["evaluate_safety"] = field(
        default="evaluate_safety", init=False
    )
    was_attributed_to: Literal["graph", "agent"] = "graph"


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


type TraceEvent = ResolutionTraceEvent | VerdictTraceEvent | PackingTraceEvent
