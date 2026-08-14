from dataclasses import dataclass, field
from typing import Literal

from app.generation._model import Section

type PackingAction = Literal["filtered", "selected", "cut"]


@dataclass(frozen=True)
class TraceEvent:
    action: PackingAction
    section: Section | None
    exercise_id: str
    reason: str
    used: tuple[str, ...]
    score: int | None = None
    kind: Literal["packing"] = field(default="packing", init=False)
    was_generated_by: Literal["pack"] = field(default="pack", init=False)
    was_attributed_to: Literal["graph"] = field(default="graph", init=False)
