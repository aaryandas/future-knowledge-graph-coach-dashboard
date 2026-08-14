from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import cast

from neo4j import Record, Session
from neo4j.graph import Node, Path, Relationship

from app.graph.schema import EdgeType, NodeLabel
from app.graph.store import neo4j_session
from app.resolver import Resolution, VocabularyConcept, resolve

from ._model import (
    AgentDecision,
    GraphDecision,
    Verdict,
    VerdictStatus,
    WalkedEdge,
    WalkedNode,
    WalkedPath,
)

_CLINICAL_DIRECTIVE = re.compile(
    r"\b(cleared for|clear for|allowed|allow|avoid|exclude|caution|modify|limit)"
    r"\b([^.;]*)",
    re.IGNORECASE,
)
_DIRECTIVE_SEPARATOR = re.compile(r"\s+and\s+|,")
_STATUS_RANK = {"clear": 0, "caution": 1, "exclude": 2}
_LAYER_RANK = {
    None: 0,
    "SNOMED anatomical fallback": 1,
    "contraindication": 2,
    "clinical directive": 3,
}


@dataclass(frozen=True)
class _MovementPatternVocabulary:
    values: tuple[VocabularyConcept, ...]

    def concepts(self) -> Iterable[VocabularyConcept]:
        return self.values

    def token_aliases(self) -> Iterable[tuple[tuple[str, ...], tuple[str, ...]]]:
        return ()


def evaluate_safety(
    member_id: str,
    exercise_ids: tuple[str, ...],
    *,
    agent_decisions: tuple[AgentDecision, ...] = (),
) -> tuple[Verdict, ...]:
    """Return deterministic verdicts in the same order as the exercise ids."""
    with neo4j_session() as session:
        vocabulary = _movement_pattern_vocabulary(session)
        decisions = (
            *_clear_decisions(session, exercise_ids),
            *_snomed_fallback_decisions(session, member_id, exercise_ids),
            *_authored_contraindication_decisions(session, member_id, exercise_ids),
            *_clinical_directive_decisions(
                session, member_id, exercise_ids, vocabulary
            ),
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
        )


def _movement_pattern_vocabulary(session: Session) -> _MovementPatternVocabulary:
    records = session.run(
        "MATCH (pattern:MovementPattern) "
        "RETURN pattern.id AS concept_id, pattern.name AS preferred_term "
        "ORDER BY concept_id"
    )
    return _MovementPatternVocabulary(
        tuple(
            VocabularyConcept(
                concept_id=cast(str, record["concept_id"]),
                preferred_term=cast(str, record["preferred_term"]),
                aliases=_movement_aliases(cast(str, record["preferred_term"])),
            )
            for record in records
        )
    )


def _movement_aliases(preferred_term: str) -> tuple[str, ...]:
    leaf = preferred_term.rsplit(" - ", maxsplit=1)[-1]
    plural = f"{leaf}s"
    return tuple(dict.fromkeys((leaf, plural)))


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
    vocabulary: _MovementPatternVocabulary,
) -> tuple[GraphDecision, ...]:
    decisions: list[GraphDecision] = []
    injuries = session.run(
        "MATCH (:Member {id: $member_id})-[:has]->(injury:MemberInjury) "
        "RETURN injury AS member_injury, injury.id AS member_injury_id, "
        "injury.notes AS notes, "
        "injury.status AS injury_status, injury.severity AS injury_severity "
        "ORDER BY member_injury_id",
        member_id=member_id,
    )
    for injury in injuries:
        for base_status, mention, resolution in _directive_resolutions(
            cast(str, injury["notes"]), vocabulary
        ):
            paths = session.run(
                "MATCH path=(pattern:MovementPattern)<-[:performs]-"
                "(exercise:Exercise) "
                "WHERE pattern.id = $pattern_id AND exercise.id IN $exercise_ids "
                "RETURN exercise.id AS exercise_id, path "
                "ORDER BY exercise_id",
                pattern_id=resolution.concept_id,
                exercise_ids=list(exercise_ids),
            )
            injury_status = cast(str, injury["injury_status"])
            injury_severity = cast(str, injury["injury_severity"])
            decisions.extend(
                GraphDecision(
                    exercise_id=cast(str, record["exercise_id"]),
                    status=_modulated_status(
                        base_status, injury_status, injury_severity
                    ),
                    layer="clinical directive",
                    member_injury_id=cast(str, injury["member_injury_id"]),
                    injury_status=injury_status,
                    injury_severity=injury_severity,
                    reason=f"Clinical directive: {base_status} {mention}",
                    walked_path=_directive_walked_path(injury, record),
                )
                for record in paths
            )
    return tuple(decisions)


def _directive_resolutions(
    notes: str, vocabulary: _MovementPatternVocabulary
) -> tuple[tuple[VerdictStatus, str, Resolution], ...]:
    resolutions: list[tuple[VerdictStatus, str, Resolution]] = []
    for match in _CLINICAL_DIRECTIVE.finditer(notes):
        status = _directive_status(match.group(1).lower())
        for value in _DIRECTIVE_SEPARATOR.split(match.group(2)):
            mention = value.strip()
            resolution = resolve(mention, vocabulary)
            if resolution.concept_id is not None:
                resolutions.append((status, mention, resolution))
    return tuple(resolutions)


def _directive_status(marker: str) -> VerdictStatus:
    if marker in {"cleared for", "clear for", "allowed", "allow"}:
        return "clear"
    if marker in {"caution", "modify", "limit"}:
        return "caution"
    return "exclude"


def _walked_path(record: Record) -> WalkedPath:
    path = cast(Path, record["path"])
    return WalkedPath(
        nodes=tuple(_walked_node(node) for node in path.nodes),
        edges=tuple(_walked_edge(edge) for edge in path.relationships),
    )


def _directive_walked_path(injury: Record, record: Record) -> WalkedPath:
    path = _walked_path(record)
    member_injury = cast(Node, injury["member_injury"])
    return WalkedPath(
        nodes=(_walked_node(member_injury), *path.nodes),
        edges=path.edges,
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
