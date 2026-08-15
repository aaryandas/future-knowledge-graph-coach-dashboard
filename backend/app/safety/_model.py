from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from app.graph.schema import EdgeType, NodeLabel

VerdictStatus: TypeAlias = Literal["exclude", "caution", "clear"]
AgentVerdictStatus: TypeAlias = Literal["exclude", "caution"]
SafetyLayer: TypeAlias = Literal[
    "clinical directive",
    "contraindication",
    "SNOMED anatomical fallback",
]
SessionInjuryKind: TypeAlias = Literal[
    "Joint",
    "AnatomicalStructure",
    "ClinicalFinding",
]


@dataclass(frozen=True)
class SessionInjury:
    concept_id: str
    kind: SessionInjuryKind


@dataclass(frozen=True)
class WalkedNode:
    node_id: str
    kind: NodeLabel
    name: str | None


@dataclass(frozen=True)
class WalkedEdge:
    edge_id: str
    kind: EdgeType
    source_id: str
    target_id: str


@dataclass(frozen=True)
class WalkedPath:
    nodes: tuple[WalkedNode, ...]
    edges: tuple[WalkedEdge, ...]


@dataclass(frozen=True)
class GraphDecision:
    exercise_id: str
    status: VerdictStatus
    layer: SafetyLayer | None
    member_injury_id: str | None
    injury_status: str | None
    injury_severity: str | None
    reason: str
    walked_path: WalkedPath
    kind: Literal["graph"] = field(default="graph", init=False)


@dataclass(frozen=True)
class AgentDecision:
    exercise_id: str
    status: AgentVerdictStatus
    reason: str
    kind: Literal["agent"] = field(default="agent", init=False)


type Decision = GraphDecision | AgentDecision


@dataclass(frozen=True)
class VerdictTraceEvent:
    exercise_id: str
    status: VerdictStatus
    layer: SafetyLayer | None
    reason: str
    walked_path: WalkedPath
    used: tuple[str, ...]
    kind: Literal["verdict"] = field(default="verdict", init=False)
    was_generated_by: Literal["evaluate_safety"] = field(
        default="evaluate_safety", init=False
    )
    was_attributed_to: Literal["graph", "agent"] = "graph"


@dataclass(frozen=True)
class Verdict:
    exercise_id: str
    status: VerdictStatus
    walked_path: WalkedPath
    decisions: tuple[Decision, ...]
    trace: tuple[VerdictTraceEvent, ...]
