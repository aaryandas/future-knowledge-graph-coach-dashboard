from __future__ import annotations

from dataclasses import replace
from typing import cast

from neo4j import Record, Session
from neo4j.graph import Node, Path, Relationship

from app.graph.schema import EdgeType, NodeLabel
from app.graph.store import neo4j_session

from ._model import (
    AgentDecision,
    GraphDecision,
    Verdict,
    VerdictStatus,
    VerdictTraceEvent,
    WalkedEdge,
    WalkedNode,
    WalkedPath,
)

_STATUS_RANK = {"clear": 0, "caution": 1, "exclude": 2}
_LAYER_RANK = {
    None: 0,
    "SNOMED anatomical fallback": 1,
    "contraindication": 2,
    "clinical directive": 3,
}


def evaluate_safety(
    member_id: str,
    exercise_ids: tuple[str, ...],
    *,
    agent_decisions: tuple[AgentDecision, ...] = (),
) -> tuple[Verdict, ...]:
    """Return deterministic verdicts in the same order as the exercise ids."""
    with neo4j_session() as session:
        decisions = (
            *_clear_decisions(session, exercise_ids),
            *_snomed_fallback_decisions(session, member_id, exercise_ids),
            *_authored_contraindication_decisions(session, member_id, exercise_ids),
            *_clinical_directive_decisions(session, member_id, exercise_ids),
        )

    verdicts = _graph_verdicts(exercise_ids, decisions)
    _apply_agent_decisions(verdicts, agent_decisions)
    return tuple(verdicts[exercise_id] for exercise_id in exercise_ids)


def _graph_verdicts(
    exercise_ids: tuple[str, ...], decisions: tuple[GraphDecision, ...]
) -> dict[str, Verdict]:
    baseline_by_exercise: dict[str, GraphDecision] = {}
    by_injury: dict[tuple[str, str], GraphDecision] = {}
    for decision in decisions:
        if decision.member_injury_id is None:
            baseline_by_exercise[decision.exercise_id] = decision
            continue
        key = (decision.exercise_id, decision.member_injury_id)
        current = by_injury.get(key)
        if current is None or _decision_precedes(decision, current):
            by_injury[key] = decision

    relevant_by_exercise: dict[str, list[GraphDecision]] = {}
    for decision in by_injury.values():
        relevant_by_exercise.setdefault(decision.exercise_id, []).append(decision)

    verdicts: dict[str, Verdict] = {}
    for exercise_id in exercise_ids:
        relevant = relevant_by_exercise.get(exercise_id)
        if relevant is None:
            relevant = [baseline_by_exercise[exercise_id]]
        ordered = tuple(
            sorted(
                relevant,
                key=lambda decision: (
                    _STATUS_RANK[decision.status],
                    _LAYER_RANK[decision.layer],
                    decision.member_injury_id or "",
                ),
                reverse=True,
            )
        )
        verdicts[exercise_id] = Verdict(
            exercise_id=exercise_id,
            status=ordered[0].status,
            walked_path=ordered[0].walked_path,
            decisions=ordered,
            trace=tuple(_graph_trace_event(decision) for decision in ordered),
        )
    return verdicts


def _decision_precedes(candidate: GraphDecision, current: GraphDecision) -> bool:
    candidate_layer = _LAYER_RANK[candidate.layer]
    current_layer = _LAYER_RANK[current.layer]
    if candidate_layer != current_layer:
        return candidate_layer > current_layer
    return _STATUS_RANK[candidate.status] > _STATUS_RANK[current.status]


def _apply_agent_decisions(
    verdicts: dict[str, Verdict], agent_decisions: tuple[AgentDecision, ...]
) -> None:
    for decision in agent_decisions:
        verdict = verdicts.get(decision.exercise_id)
        if verdict is None:
            raise ValueError(
                f"Agent decision references unknown exercise: {decision.exercise_id}"
            )
        if decision.status not in {"caution", "exclude"}:
            raise ValueError("Agent decisions can only tighten the safety floor")
        if _STATUS_RANK[decision.status] <= _STATUS_RANK[verdict.status]:
            continue
        verdicts[decision.exercise_id] = replace(
            verdict,
            status=decision.status,
            decisions=(*verdict.decisions, decision),
            trace=(
                *verdict.trace,
                VerdictTraceEvent(
                    exercise_id=decision.exercise_id,
                    status=decision.status,
                    layer=None,
                    reason=decision.reason,
                    walked_path=verdict.walked_path,
                    used=tuple(node.node_id for node in verdict.walked_path.nodes),
                    was_attributed_to="agent",
                ),
            ),
        )


def _graph_trace_event(decision: GraphDecision) -> VerdictTraceEvent:
    return VerdictTraceEvent(
        exercise_id=decision.exercise_id,
        status=decision.status,
        layer=decision.layer,
        reason=decision.reason,
        walked_path=decision.walked_path,
        used=tuple(node.node_id for node in decision.walked_path.nodes),
    )


def _clear_decisions(
    session: Session, exercise_ids: tuple[str, ...]
) -> tuple[GraphDecision, ...]:
    records = session.run(
        "MATCH path=(exercise:Exercise) "
        "WHERE exercise.id IN $exercise_ids "
        "RETURN exercise.id AS exercise_id, path ORDER BY exercise_id",
        exercise_ids=list(exercise_ids),
    )
    return tuple(
        GraphDecision(
            exercise_id=cast(str, record["exercise_id"]),
            status="clear",
            layer=None,
            member_injury_id=None,
            injury_status=None,
            injury_severity=None,
            reason="No safety constraint matched",
            walked_path=_walked_path(record),
        )
        for record in records
    )


def _snomed_fallback_decisions(
    session: Session, member_id: str, exercise_ids: tuple[str, ...]
) -> tuple[GraphDecision, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:has]->(member_injury:MemberInjury) "
        "MATCH path=(member_injury)-[:exactMatch]->(finding:ClinicalFinding)-"
        "[:findingSite]->(:AnatomicalStructure)-[:isA*0..]->(anatomy)"
        "<-[:exactMatch]-(joint:Joint)<-[:loads]-(exercise:Exercise) "
        "WHERE exercise.id IN $exercise_ids "
        "RETURN exercise.id AS exercise_id, "
        "member_injury.id AS member_injury_id, "
        "member_injury.status AS injury_status, "
        "member_injury.severity AS injury_severity, joint.name AS joint_name, path "
        "ORDER BY exercise_id, member_injury_id, length(path), joint.id",
        member_id=member_id,
        exercise_ids=list(exercise_ids),
    )
    decisions: list[GraphDecision] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        exercise_id = cast(str, record["exercise_id"])
        member_injury_id = cast(str, record["member_injury_id"])
        injury_status = cast(str, record["injury_status"])
        injury_severity = cast(str, record["injury_severity"])
        key = (exercise_id, member_injury_id)
        if key in seen:
            continue
        seen.add(key)
        decisions.append(
            GraphDecision(
                exercise_id=exercise_id,
                status=_modulated_status("caution", injury_status, injury_severity),
                layer="SNOMED anatomical fallback",
                member_injury_id=member_injury_id,
                injury_status=injury_status,
                injury_severity=injury_severity,
                reason=(
                    "SNOMED anatomical fallback through "
                    f"{cast(str, record['joint_name'])}"
                ),
                walked_path=_walked_path(record),
            )
        )
    return tuple(decisions)


def _authored_contraindication_decisions(
    session: Session, member_id: str, exercise_ids: tuple[str, ...]
) -> tuple[GraphDecision, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:has]->(member_injury:MemberInjury) "
        "MATCH path=(member_injury)-[:exactMatch]->(finding:ClinicalFinding)"
        "<-[:exactMatch]-(injury:Injury)-"
        "[contraindication:contraindicates]->(target)"
        "<-[:performs|loads]-(exercise:Exercise) "
        "WHERE exercise.id IN $exercise_ids "
        "RETURN exercise.id AS exercise_id, "
        "member_injury.id AS member_injury_id, "
        "member_injury.status AS injury_status, "
        "member_injury.severity AS injury_severity, "
        "contraindication.level AS level, contraindication.note AS note, path "
        "ORDER BY exercise_id, member_injury_id, injury.id, target.id",
        member_id=member_id,
        exercise_ids=list(exercise_ids),
    )
    decisions: list[GraphDecision] = []
    for record in records:
        injury_status = cast(str, record["injury_status"])
        injury_severity = cast(str, record["injury_severity"])
        decisions.append(
            GraphDecision(
                exercise_id=cast(str, record["exercise_id"]),
                status=_modulated_status(
                    _authored_status(cast(str, record["level"])),
                    injury_status,
                    injury_severity,
                ),
                layer="contraindication",
                member_injury_id=cast(str, record["member_injury_id"]),
                injury_status=injury_status,
                injury_severity=injury_severity,
                reason=cast(str, record["note"]),
                walked_path=_walked_path(record),
            )
        )
    return tuple(decisions)


def _authored_status(level: str) -> VerdictStatus:
    if level == "avoid":
        return "exclude"
    if level == "caution":
        return "caution"
    raise RuntimeError(f"Unknown contraindication level: {level}")


def _modulated_status(
    status: VerdictStatus, injury_status: str, injury_severity: str
) -> VerdictStatus:
    if injury_status == "resolved":
        return "clear"
    if status == "caution" and (
        injury_status == "active" or injury_severity in {"moderate", "severe"}
    ):
        return "exclude"
    return status


def _clinical_directive_decisions(
    session: Session,
    member_id: str,
    exercise_ids: tuple[str, ...],
) -> tuple[GraphDecision, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:has]->(member_injury:MemberInjury) "
        "MATCH path=(member_injury)-[directive:clinicalDirective]->(target)"
        "<-[:performs|loads]-(exercise:Exercise) "
        "WHERE exercise.id IN $exercise_ids "
        "RETURN exercise.id AS exercise_id, "
        "member_injury.id AS member_injury_id, "
        "member_injury.status AS injury_status, "
        "member_injury.severity AS injury_severity, "
        "directive.status AS directive_status, "
        "directive.raw_text AS raw_text, path "
        "ORDER BY exercise_id, member_injury_id, directive.id",
        member_id=member_id,
        exercise_ids=list(exercise_ids),
    )
    decisions: list[GraphDecision] = []
    for record in records:
        injury_status = cast(str, record["injury_status"])
        injury_severity = cast(str, record["injury_severity"])
        directive_status = _stored_directive_status(record["directive_status"])
        decisions.append(
            GraphDecision(
                exercise_id=cast(str, record["exercise_id"]),
                status=_modulated_status(
                    directive_status, injury_status, injury_severity
                ),
                layer="clinical directive",
                member_injury_id=cast(str, record["member_injury_id"]),
                injury_status=injury_status,
                injury_severity=injury_severity,
                reason=(
                    "Clinical directive: "
                    f"{directive_status} {cast(str, record['raw_text'])}"
                ),
                walked_path=_walked_path(record),
            )
        )
    return tuple(decisions)


def _stored_directive_status(value: object) -> VerdictStatus:
    if value not in {"clear", "caution", "exclude"}:
        raise RuntimeError(f"Unknown clinical directive status: {value}")
    return cast(VerdictStatus, value)


def _walked_path(record: Record) -> WalkedPath:
    path = cast(Path, record["path"])
    return WalkedPath(
        nodes=tuple(_walked_node(node) for node in path.nodes),
        edges=tuple(_walked_edge(edge) for edge in path.relationships),
    )


def _walked_node(node: Node) -> WalkedNode:
    return WalkedNode(
        node_id=cast(str, node["id"]),
        kind=cast(NodeLabel, next(iter(node.labels))),
        name=cast(str | None, node.get("name") or node.get("preferred_term")),
    )


def _walked_edge(edge: Relationship) -> WalkedEdge:
    source = edge.start_node
    target = edge.end_node
    if source is None or target is None:
        raise RuntimeError("Walked relationship has no endpoint")
    return WalkedEdge(
        edge_id=cast(str, edge["id"]),
        kind=cast(EdgeType, edge.type),
        source_id=cast(str, source["id"]),
        target_id=cast(str, target["id"]),
    )
