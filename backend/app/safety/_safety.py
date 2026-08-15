from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, cast

from neo4j import Query, Record, Session
from neo4j.graph import Node, Path, Relationship

from app.graph.schema import EdgeType, NodeLabel
from app.graph.store import neo4j_session

from ._model import (
    AgentDecision,
    GraphDecision,
    SafetyLayer,
    SessionInjury,
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

type _InjuryKind = Literal[
    "MemberInjury",
    "Joint",
    "AnatomicalStructure",
    "ClinicalFinding",
]


@dataclass(frozen=True)
class _InjuryValue:
    source_id: str
    kind: _InjuryKind
    member_injury_id: str
    status: str
    severity: str | None


def evaluate_safety(
    member_id: str,
    exercise_ids: tuple[str, ...],
    *,
    session_injuries: tuple[SessionInjury, ...] = (),
    agent_decisions: tuple[AgentDecision, ...] = (),
) -> tuple[Verdict, ...]:
    """Return deterministic verdicts in the same order as the exercise ids."""
    with neo4j_session() as session:
        injuries = _injury_values(session, member_id, session_injuries)
        decisions = (
            *_clear_decisions(session, exercise_ids),
            *_snomed_fallback_decisions(session, exercise_ids, injuries),
            *_authored_contraindication_decisions(session, exercise_ids, injuries),
            *_clinical_directive_decisions(session, exercise_ids, injuries),
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


def _injury_values(
    session: Session,
    member_id: str,
    session_injuries: tuple[SessionInjury, ...],
) -> tuple[_InjuryValue, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:has]->(injury:MemberInjury) "
        "RETURN injury.id AS injury_id, injury.status AS status, "
        "injury.severity AS severity ORDER BY injury_id",
        member_id=member_id,
    )
    recorded = tuple(
        _InjuryValue(
            source_id=cast(str, record["injury_id"]),
            kind="MemberInjury",
            member_injury_id=cast(str, record["injury_id"]),
            status=cast(str, record["status"]),
            severity=cast(str | None, record["severity"]),
        )
        for record in records
    )
    scoped = tuple(
        _InjuryValue(
            source_id=injury.concept_id,
            kind=injury.kind,
            member_injury_id=f"session:{injury.concept_id}",
            status="active",
            severity=None,
        )
        for injury in session_injuries
    )
    return (*recorded, *scoped)


def _snomed_fallback_decisions(
    session: Session,
    exercise_ids: tuple[str, ...],
    injuries: tuple[_InjuryValue, ...],
) -> tuple[GraphDecision, ...]:
    decisions: list[GraphDecision] = []
    for injury in injuries:
        if injury.kind == "MemberInjury":
            match = (
                "MATCH path=(source:MemberInjury {id: $source_id})"
                "-[:exactMatch]->(finding:ClinicalFinding)-"
                "[:findingSite]->(:AnatomicalStructure)-[:isA*0..]->(anatomy)"
                "<-[:exactMatch]-(joint:Joint)<-[:loads]-(exercise:Exercise) "
            )
        elif injury.kind == "ClinicalFinding":
            match = (
                "MATCH path=(source:ClinicalFinding {id: $source_id})-"
                "[:findingSite]->(:AnatomicalStructure)-[:isA*0..]->(anatomy)"
                "<-[:exactMatch]-(joint:Joint)<-[:loads]-(exercise:Exercise) "
            )
        elif injury.kind == "AnatomicalStructure":
            match = (
                "MATCH path=(source:AnatomicalStructure {id: $source_id})-"
                "[:isA*0..]->(anatomy)<-[:exactMatch]-(joint:Joint)"
                "<-[:loads]-(exercise:Exercise) "
            )
        else:
            match = (
                "MATCH path=(joint:Joint {id: $source_id})"
                "<-[:loads]-(exercise:Exercise) "
            )
        records = session.run(
            Query(
                match + "WHERE exercise.id IN $exercise_ids "
                "RETURN exercise.id AS exercise_id, joint.name AS joint_name, path "
                "ORDER BY exercise_id, length(path), joint.id"
            ),
            source_id=injury.source_id,
            exercise_ids=list(exercise_ids),
        )
        seen: set[str] = set()
        for record in records:
            exercise_id = cast(str, record["exercise_id"])
            if exercise_id in seen:
                continue
            seen.add(exercise_id)
            reason = (
                f"SNOMED anatomical fallback through {cast(str, record['joint_name'])}"
            )
            if injury.kind != "MemberInjury":
                reason = (
                    "Session injury used the SNOMED anatomical fallback through "
                    f"{cast(str, record['joint_name'])}."
                )
            decisions.append(
                _injury_decision(
                    record,
                    injury,
                    status="caution",
                    layer="SNOMED anatomical fallback",
                    reason=reason,
                )
            )
    return tuple(decisions)


def _authored_contraindication_decisions(
    session: Session,
    exercise_ids: tuple[str, ...],
    injuries: tuple[_InjuryValue, ...],
) -> tuple[GraphDecision, ...]:
    decisions: list[GraphDecision] = []
    for injury in injuries:
        if injury.kind == "MemberInjury":
            match = (
                "MATCH path=(source:MemberInjury {id: $source_id})"
                "-[:exactMatch]->(finding:ClinicalFinding)"
                "<-[:exactMatch]-(authored:Injury)-"
                "[contraindication:contraindicates]->(target)"
                "<-[:performs|loads]-(exercise:Exercise) "
            )
        elif injury.kind == "ClinicalFinding":
            match = (
                "MATCH path=(source:ClinicalFinding {id: $source_id})"
                "<-[:exactMatch]-(authored:Injury)-"
                "[contraindication:contraindicates]->(target)"
                "<-[:performs|loads]-(exercise:Exercise) "
            )
        else:
            continue
        records = session.run(
            Query(
                match + "WHERE exercise.id IN $exercise_ids "
                "RETURN exercise.id AS exercise_id, "
                "contraindication.level AS level, contraindication.note AS note, path "
                "ORDER BY exercise_id, authored.id, target.id"
            ),
            source_id=injury.source_id,
            exercise_ids=list(exercise_ids),
        )
        for record in records:
            reason = cast(str, record["note"])
            if injury.kind != "MemberInjury":
                reason = f"Session injury: {reason}"
            decisions.append(
                _injury_decision(
                    record,
                    injury,
                    status=_authored_status(cast(str, record["level"])),
                    layer="contraindication",
                    reason=reason,
                )
            )
    return tuple(decisions)


def _clinical_directive_decisions(
    session: Session,
    exercise_ids: tuple[str, ...],
    injuries: tuple[_InjuryValue, ...],
) -> tuple[GraphDecision, ...]:
    decisions: list[GraphDecision] = []
    for injury in injuries:
        if injury.kind == "MemberInjury":
            records = session.run(
                "MATCH path=(source:MemberInjury {id: $source_id})"
                "-[directive:clinicalDirective]->(target)"
                "<-[:performs|loads]-(exercise:Exercise) "
                "WHERE exercise.id IN $exercise_ids "
                "RETURN exercise.id AS exercise_id, "
                "directive.status AS directive_status, "
                "directive.raw_text AS raw_text, path "
                "ORDER BY exercise_id, directive.id",
                source_id=injury.source_id,
                exercise_ids=list(exercise_ids),
            )
            for record in records:
                directive_status = _stored_directive_status(record["directive_status"])
                decisions.append(
                    _injury_decision(
                        record,
                        injury,
                        status=directive_status,
                        layer="clinical directive",
                        reason=(
                            "Clinical directive: "
                            f"{directive_status} {cast(str, record['raw_text'])}"
                        ),
                    )
                )
        elif injury.kind == "Joint":
            records = session.run(
                "MATCH path=(joint:Joint {id: $source_id})"
                "<-[:loads]-(exercise:Exercise) "
                "WHERE exercise.id IN $exercise_ids "
                "RETURN exercise.id AS exercise_id, joint.name AS joint_name, path "
                "ORDER BY exercise_id",
                source_id=injury.source_id,
                exercise_ids=list(exercise_ids),
            )
            decisions.extend(
                _injury_decision(
                    record,
                    injury,
                    status="caution",
                    layer="clinical directive",
                    reason=(
                        "Session injury clinical directive through "
                        f"{cast(str, record['joint_name'])}."
                    ),
                )
                for record in records
            )
    return tuple(decisions)


def _injury_decision(
    record: Record,
    injury: _InjuryValue,
    *,
    status: VerdictStatus,
    layer: SafetyLayer,
    reason: str,
) -> GraphDecision:
    return GraphDecision(
        exercise_id=cast(str, record["exercise_id"]),
        status=_modulated_status(status, injury.status, injury.severity),
        layer=layer,
        member_injury_id=injury.member_injury_id,
        injury_status=injury.status,
        injury_severity=injury.severity,
        reason=reason,
        walked_path=_walked_path(record),
    )


def _authored_status(level: str) -> VerdictStatus:
    if level == "avoid":
        return "exclude"
    if level == "caution":
        return "caution"
    raise RuntimeError(f"Unknown contraindication level: {level}")


def _modulated_status(
    status: VerdictStatus, injury_status: str, injury_severity: str | None
) -> VerdictStatus:
    if injury_status == "resolved":
        return "clear"
    if status == "caution" and (
        injury_status == "active" or injury_severity in {"moderate", "severe"}
    ):
        return "exclude"
    return status


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
