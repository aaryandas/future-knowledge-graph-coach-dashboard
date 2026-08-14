from __future__ import annotations

from dataclasses import replace
from typing import Literal, LiteralString, cast

from neo4j import Query, Record, Session
from neo4j.graph import Node, Path, Relationship

from app.generation._model import ResolvedMention
from app.graph.schema import EdgeType, NodeLabel
from app.graph.store import neo4j_session
from app.safety import (
    GraphDecision,
    Verdict,
    VerdictTraceEvent,
    WalkedEdge,
    WalkedNode,
    WalkedPath,
    evaluate_safety,
)

type SessionSafetyLayer = Literal[
    "contraindication",
    "SNOMED anatomical fallback",
]

_STATUS_RANK = {"clear": 0, "caution": 1, "exclude": 2}
_LAYER_RANK = {
    None: 0,
    "SNOMED anatomical fallback": 1,
    "contraindication": 2,
    "clinical directive": 3,
}


def evaluate_generation_safety(
    member_id: str,
    exercise_ids: tuple[str, ...],
    session_injuries: tuple[ResolvedMention, ...],
) -> tuple[Verdict, ...]:
    """Apply recorded and session injuries through the safety graph paths."""
    verdicts = evaluate_safety(member_id, exercise_ids)
    enforced_injuries = tuple(
        injury
        for injury in session_injuries
        if injury.enforced and injury.resolution.concept_id is not None
    )
    if not enforced_injuries:
        return verdicts

    with neo4j_session() as session:
        decisions = _session_decisions(session, exercise_ids, enforced_injuries)
    return _merge_session_decisions(verdicts, decisions)


def _session_decisions(
    session: Session,
    exercise_ids: tuple[str, ...],
    injuries: tuple[ResolvedMention, ...],
) -> tuple[GraphDecision, ...]:
    decisions: list[GraphDecision] = []
    for injury in injuries:
        if injury.vocabulary == "ClinicalFinding":
            decisions.extend(_clinical_finding_decisions(session, exercise_ids, injury))
        elif injury.vocabulary == "AnatomicalStructure":
            decisions.extend(_anatomy_decisions(session, exercise_ids, injury))
        elif injury.vocabulary == "Joint":
            decisions.extend(_joint_decisions(session, exercise_ids, injury))

    best_by_injury: dict[tuple[str, str | None], GraphDecision] = {}
    for decision in decisions:
        key = (decision.exercise_id, decision.member_injury_id)
        current = best_by_injury.get(key)
        if current is None or _LAYER_RANK[decision.layer] > _LAYER_RANK[current.layer]:
            best_by_injury[key] = decision
    return tuple(best_by_injury.values())


def _clinical_finding_decisions(
    session: Session,
    exercise_ids: tuple[str, ...],
    injury: ResolvedMention,
) -> tuple[GraphDecision, ...]:
    concept_id = _concept_id(injury)
    authored_records = session.run(
        "MATCH path=(finding:ClinicalFinding {id: $concept_id})"
        "<-[:exactMatch]-(injury:Injury)-"
        "[contraindication:contraindicates]->(target)"
        "<-[:performs|loads]-(exercise:Exercise) "
        "WHERE exercise.id IN $exercise_ids "
        "RETURN exercise.id AS exercise_id, contraindication.level AS level, "
        "contraindication.note AS note, path "
        "ORDER BY exercise_id, injury.id, target.id",
        concept_id=concept_id,
        exercise_ids=list(exercise_ids),
    )
    decisions = [
        _decision(
            record,
            injury,
            layer="contraindication",
            reason=_authored_reason(record),
        )
        for record in authored_records
    ]
    decisions.extend(
        _fallback_decisions(
            session,
            exercise_ids,
            injury,
            "MATCH path=(finding:ClinicalFinding {id: $concept_id})-"
            "[:findingSite]->(:AnatomicalStructure)-[:isA*0..]->(anatomy)"
            "<-[:exactMatch]-(joint:Joint)<-[:loads]-(exercise:Exercise) ",
        )
    )
    return tuple(decisions)


def _anatomy_decisions(
    session: Session,
    exercise_ids: tuple[str, ...],
    injury: ResolvedMention,
) -> tuple[GraphDecision, ...]:
    return _fallback_decisions(
        session,
        exercise_ids,
        injury,
        "MATCH path=(source:AnatomicalStructure {id: $concept_id})-"
        "[:isA*0..]->(anatomy)<-[:exactMatch]-(joint:Joint)"
        "<-[:loads]-(exercise:Exercise) ",
    )


def _joint_decisions(
    session: Session,
    exercise_ids: tuple[str, ...],
    injury: ResolvedMention,
) -> tuple[GraphDecision, ...]:
    return _fallback_decisions(
        session,
        exercise_ids,
        injury,
        "MATCH path=(joint:Joint {id: $concept_id})<-[:loads]-(exercise:Exercise) ",
    )


def _fallback_decisions(
    session: Session,
    exercise_ids: tuple[str, ...],
    injury: ResolvedMention,
    match: LiteralString,
) -> tuple[GraphDecision, ...]:
    query = Query(
        match + "WHERE exercise.id IN $exercise_ids "
        "RETURN exercise.id AS exercise_id, joint.name AS joint_name, path "
        "ORDER BY exercise_id, length(path), joint.id"
    )
    records = session.run(
        query,
        concept_id=_concept_id(injury),
        exercise_ids=list(exercise_ids),
    )
    return tuple(
        _decision(
            record,
            injury,
            layer="SNOMED anatomical fallback",
            reason=(
                "Session injury used the SNOMED anatomical fallback through "
                f"{cast(str, record['joint_name'])}."
            ),
        )
        for record in records
    )


def _decision(
    record: Record,
    injury: ResolvedMention,
    *,
    layer: SessionSafetyLayer,
    reason: str,
) -> GraphDecision:
    return GraphDecision(
        exercise_id=cast(str, record["exercise_id"]),
        status="exclude",
        layer=layer,
        member_injury_id=f"session:{_concept_id(injury)}",
        injury_status="active",
        injury_severity=None,
        reason=reason,
        walked_path=_walked_path(record),
    )


def _authored_reason(record: Record) -> str:
    level = record["level"]
    if level not in {"avoid", "caution"}:
        raise RuntimeError(f"Unknown contraindication level: {level}")
    return f"Session injury: {cast(str, record['note'])}"


def _concept_id(injury: ResolvedMention) -> str:
    concept_id = injury.resolution.concept_id
    if concept_id is None:
        raise RuntimeError("An enforced session injury has no concept id")
    return concept_id


def _merge_session_decisions(
    verdicts: tuple[Verdict, ...],
    decisions: tuple[GraphDecision, ...],
) -> tuple[Verdict, ...]:
    by_exercise: dict[str, list[GraphDecision]] = {}
    for decision in decisions:
        by_exercise.setdefault(decision.exercise_id, []).append(decision)

    merged: list[Verdict] = []
    for verdict in verdicts:
        session_decisions = tuple(by_exercise.get(verdict.exercise_id, ()))
        if not session_decisions:
            merged.append(verdict)
            continue
        strongest = max(
            session_decisions,
            key=lambda decision: (
                _STATUS_RANK[decision.status],
                _LAYER_RANK[decision.layer],
                decision.member_injury_id or "",
            ),
        )
        session_precedes = _session_precedes_verdict(strongest, verdict)
        merged.append(
            replace(
                verdict,
                status=strongest.status if session_precedes else verdict.status,
                walked_path=(
                    strongest.walked_path if session_precedes else verdict.walked_path
                ),
                decisions=(*verdict.decisions, *session_decisions),
                trace=(
                    *verdict.trace,
                    *(_trace_event(decision) for decision in session_decisions),
                ),
            )
        )
    return tuple(merged)


def _session_precedes_verdict(decision: GraphDecision, verdict: Verdict) -> bool:
    decision_rank = _STATUS_RANK[decision.status]
    verdict_rank = _STATUS_RANK[verdict.status]
    if decision_rank != verdict_rank:
        return decision_rank > verdict_rank
    graph_layers = (
        stored.layer
        for stored in verdict.decisions
        if isinstance(stored, GraphDecision) and stored.status == verdict.status
    )
    strongest_layer = max((_LAYER_RANK[layer] for layer in graph_layers), default=0)
    return _LAYER_RANK[decision.layer] > strongest_layer


def _trace_event(decision: GraphDecision) -> VerdictTraceEvent:
    return VerdictTraceEvent(
        exercise_id=decision.exercise_id,
        status=decision.status,
        layer=decision.layer,
        reason=decision.reason,
        walked_path=decision.walked_path,
        used=tuple(node.node_id for node in decision.walked_path.nodes),
    )


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
