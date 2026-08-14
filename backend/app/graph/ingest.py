import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, LiteralString, cast

from neo4j import ManagedTransaction, Session

from app.graph.coach_actions import COACH_ACTION_SOURCE
from app.graph.conditions import CONDITIONS_SOURCE, AuthoredConditions, load_conditions
from app.graph.schema import (
    EXERCISE_TAXONOMIES,
    KG1_EDGE_TYPES,
    KG1_NODE_LABELS,
    KG2_EDGE_TYPES,
    KG2_NODE_LABELS,
    NODE_LABELS,
    EdgeType,
    NodeLabel,
)
from app.graph.store import neo4j_session
from app.resolver import (
    ArtifactVocabulary,
    Resolution,
    Vocabulary,
    VocabularyConcept,
    resolve,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIRECTORY = REPOSITORY_ROOT / "data"
CATALOG_SOURCE = "data/exercises.json"
MEMBER_CONTEXT_PATTERN = "member-context*.json"
_CLINICAL_DIRECTIVE = re.compile(
    r"\b(cleared for|clear for|allowed|allow|avoid|exclude|caution|modify|limit)"
    r"\b([^.;]*)",
    re.IGNORECASE,
)
_DIRECTIVE_SEPARATOR = re.compile(r"\s+and\s+|,")

KG1_EDGE_SOURCE_LABELS: dict[EdgeType, tuple[NodeLabel, ...]] = {
    "targets": ("Exercise",),
    "loads": ("Exercise",),
    "performs": ("Exercise",),
    "requires": ("Exercise",),
    "findingSite": ("ClinicalFinding",),
    "isA": ("AnatomicalStructure",),
    "exactMatch": ("Joint", "Injury"),
    "contraindicates": ("Injury",),
}
KG2_EDGE_SOURCE_LABELS: dict[EdgeType, NodeLabel] = {
    "pursues": "Member",
    "has": "Member",
    "owns": "Member",
    "performed": "Member",
    "observed": "Member",
    "said": "Member",
    "received": "Member",
    "dislikes": "Member",
    "included": "WorkoutSession",
    "exactMatch": "MemberInjury",
    "clinicalDirective": "MemberInjury",
    "evidencedBy": "Barrier",
    "addresses": "CoachTask",
}

type JsonObject = dict[str, Any]
type DirectiveStatus = Literal["clear", "caution", "exclude"]


@dataclass(frozen=True)
class Node:
    id: str
    properties: JsonObject


@dataclass(frozen=True)
class Edge:
    id: str
    source_id: str
    target_id: str
    properties: JsonObject


@dataclass(frozen=True)
class NodeBatch:
    label: NodeLabel
    rows: list[Node]


@dataclass(frozen=True)
class EdgeBatch:
    source_label: NodeLabel
    edge_type: EdgeType
    target_label: NodeLabel
    rows: list[Edge]


@dataclass(frozen=True)
class _ClinicalDirective:
    status: DirectiveStatus
    raw_text: str


@dataclass(frozen=True)
class _MovementPatternVocabulary:
    values: tuple[VocabularyConcept, ...]

    def concepts(self) -> Iterable[VocabularyConcept]:
        return self.values

    def token_aliases(self) -> Iterable[tuple[tuple[str, ...], tuple[str, ...]]]:
        return ()

    def embeddings(self) -> None:
        return None


@dataclass(frozen=True)
class KG1Payload:
    nodes: list[NodeBatch]
    edges: list[EdgeBatch]
    seed_sources: tuple[str, ...]


@dataclass(frozen=True)
class KG1Counts:
    nodes: dict[NodeLabel, int]
    edges: dict[EdgeType, int]


@dataclass(frozen=True)
class KG2Payload:
    nodes: list[NodeBatch]
    edges: list[EdgeBatch]


@dataclass(frozen=True)
class KG2Counts:
    nodes: dict[NodeLabel, int]
    edges: dict[EdgeType, int]


def ingest_kg1(data_directory: Path = DEFAULT_DATA_DIRECTORY) -> KG1Counts:
    payload = _load_kg1(data_directory)
    ingested_at = datetime.now(UTC).isoformat()

    with neo4j_session() as session:
        _ensure_constraints(session)
        session.execute_write(_merge_and_reconcile_kg1_payload, payload, ingested_at)
        return _read_kg1_counts(session)


def ingest_kg2(data_directory: Path = DEFAULT_DATA_DIRECTORY) -> KG2Counts:
    payload = _load_kg2(data_directory)
    ingested_at = datetime.now(UTC).isoformat()

    with neo4j_session() as session:
        _ensure_constraints(session)
        session.execute_write(_merge_and_reconcile_kg2_payload, payload, ingested_at)
        return _read_kg2_counts(session)


def _load_kg1(data_directory: Path) -> KG1Payload:
    catalog_path = data_directory / "exercises.json"
    catalog_bytes = catalog_path.read_bytes()
    exercises = cast(list[JsonObject], json.loads(catalog_bytes))
    catalog_version = sha256(catalog_bytes).hexdigest()

    ontology_directory = data_directory / "ontology"
    snomed = _read_object(ontology_directory / "snomed-ct.json")
    mappings = _read_object(ontology_directory / "skos-mappings.json")
    conditions = load_conditions(data_directory / "contraindications.json")

    node_batches, exercise_edge_batches = _catalog_batches(exercises, catalog_version)
    snomed_node_batches, snomed_edge_batches, concept_labels = _snomed_batches(snomed)
    condition_node_batches, condition_edge_batches, injury_findings = (
        _condition_batches(conditions, node_batches, concept_labels)
    )
    mapping_edge_batches = _mapping_batches(mappings, concept_labels, injury_findings)

    return KG1Payload(
        nodes=[*node_batches, *snomed_node_batches, *condition_node_batches],
        edges=[
            *exercise_edge_batches,
            *snomed_edge_batches,
            *mapping_edge_batches,
            *condition_edge_batches,
        ],
        seed_sources=tuple(
            sorted(
                {
                    CATALOG_SOURCE,
                    CONDITIONS_SOURCE,
                    _artifact_stamp(snomed)[0],
                    _artifact_stamp(mappings)[0],
                }
            )
        ),
    )


def _load_kg2(data_directory: Path) -> KG2Payload:
    member_paths = sorted(data_directory.glob(MEMBER_CONTEXT_PATTERN))
    if not member_paths:
        raise FileNotFoundError(
            f"No member seed documents match {MEMBER_CONTEXT_PATTERN!r}"
        )

    synonyms_path = data_directory / "synonyms.json"
    exercise_path = data_directory / "exercises.json"
    snomed_path = data_directory / "ontology" / "snomed-ct.json"
    equipment_vocab = ArtifactVocabulary.from_file(
        exercise_path,
        kind="Equipment",
        synonyms_path=synonyms_path,
    )
    exercise_vocab = ArtifactVocabulary.from_file(
        exercise_path,
        kind="Exercise",
        synonyms_path=synonyms_path,
    )
    finding_vocab = ArtifactVocabulary.from_file(
        snomed_path,
        kind="ClinicalFinding",
        synonyms_path=synonyms_path,
    )
    movement_pattern_vocab = _movement_pattern_vocabulary(exercise_path, synonyms_path)
    joint_vocab = ArtifactVocabulary.from_file(
        exercise_path,
        kind="Joint",
        synonyms_path=synonyms_path,
    )

    node_rows: dict[NodeLabel, list[Node]] = defaultdict(list)
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]] = defaultdict(
        list
    )
    for member_path in member_paths:
        member_bytes = member_path.read_bytes()
        member = _object(json.loads(member_bytes), str(member_path))
        source = f"data/{member_path.name}"
        version = sha256(member_bytes).hexdigest()
        _append_member(
            member,
            source,
            version,
            equipment_vocab,
            exercise_vocab,
            finding_vocab,
            movement_pattern_vocab,
            joint_vocab,
            node_rows,
            edge_rows,
        )

    for label, rows in node_rows.items():
        _require_unique_ids(rows, label)

    return KG2Payload(
        nodes=[NodeBatch(label, node_rows.get(label, [])) for label in KG2_NODE_LABELS],
        edges=[
            EdgeBatch(source_label, edge_type, target_label, rows)
            for (source_label, edge_type, target_label), rows in edge_rows.items()
        ],
    )


def _append_member(
    member: JsonObject,
    source: str,
    version: str,
    equipment_vocab: ArtifactVocabulary,
    exercise_vocab: ArtifactVocabulary,
    finding_vocab: ArtifactVocabulary,
    movement_pattern_vocab: _MovementPatternVocabulary,
    joint_vocab: ArtifactVocabulary,
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> None:
    stamp = {"source": source, "version": version}
    profile = _object(member.get("profile"), "member profile")
    member_id = _required_string(profile, "id")
    preferences = _object(member.get("preferences"), f"Member {member_id} preferences")
    equipment_mentions = _string_list(
        member.get("equipment_available"), f"Member {member_id} equipment_available"
    )
    dislike_mentions = _string_list(
        preferences.get("dislikes"), f"Member {member_id} preferences.dislikes"
    )
    coach_brief = _object(member.get("coach_brief"), f"Member {member_id} coach_brief")
    churn_risk = _object(
        coach_brief.get("churn_risk"), f"Member {member_id} churn_risk"
    )

    member_properties = {key: value for key, value in profile.items() if key != "id"}
    member_properties.update(
        {
            "preferred_session_minutes": preferences.get("preferred_session_minutes"),
            "training_days_per_week": preferences.get("training_days_per_week"),
            "preferred_days": _string_list(
                preferences.get("preferred_days"),
                f"Member {member_id} preferences.preferred_days",
            ),
            "preference_notes": preferences.get("notes"),
            "equipment_available": equipment_mentions,
            "dislikes": dislike_mentions,
            "brief_generated_for": _required_string(coach_brief, "generated_for"),
            "churn_risk_level": _required_string(churn_risk, "level"),
            "churn_risk_reasons": _string_list(
                churn_risk.get("reasons"), f"Member {member_id} churn_risk.reasons"
            ),
            **stamp,
        }
    )
    node_rows["Member"].append(
        Node(id=member_id, properties=_neo4j_properties(member_properties, member_id))
    )

    _append_bridge_edges(
        member_id,
        "Member",
        "owns",
        "Equipment",
        equipment_mentions,
        equipment_vocab,
        stamp,
        edge_rows,
    )
    _append_bridge_edges(
        member_id,
        "Member",
        "dislikes",
        "Exercise",
        dislike_mentions,
        exercise_vocab,
        stamp,
        edge_rows,
    )

    _append_goals(member, member_id, stamp, node_rows, edge_rows)
    _append_injuries(
        member,
        member_id,
        finding_vocab,
        movement_pattern_vocab,
        joint_vocab,
        stamp,
        node_rows,
        edge_rows,
    )
    sessions = _append_workout_sessions(
        member,
        member_id,
        exercise_vocab,
        stamp,
        node_rows,
        edge_rows,
    )
    messages = _append_chat_messages(member, member_id, stamp, node_rows, edge_rows)
    observations = _append_observations(
        member,
        member_id,
        _required_string(coach_brief, "generated_for"),
        messages,
        stamp,
        node_rows,
        edge_rows,
    )
    barrier_ids = _append_barriers(
        churn_risk,
        member_id,
        stamp,
        observations,
        sessions,
        messages,
        node_rows,
        edge_rows,
    )
    _append_coach_tasks(
        coach_brief,
        member_id,
        stamp,
        sessions,
        barrier_ids,
        node_rows,
        edge_rows,
    )


def _append_goals(
    member: JsonObject,
    member_id: str,
    stamp: JsonObject,
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> None:
    for value in _object_list(member.get("goals"), f"Member {member_id} goals"):
        external_id = _required_string(value, "id")
        goal_id = f"{member_id}:goal:{external_id}"
        properties = {key: item for key, item in value.items() if key != "id"}
        properties.update(external_id=external_id, member_id=member_id, **stamp)
        node_rows["Goal"].append(Node(goal_id, _neo4j_properties(properties, goal_id)))
        _append_edge(
            member_id,
            "Member",
            "pursues",
            goal_id,
            "Goal",
            stamp,
            edge_rows,
        )


def _append_injuries(
    member: JsonObject,
    member_id: str,
    finding_vocab: ArtifactVocabulary,
    movement_pattern_vocab: _MovementPatternVocabulary,
    joint_vocab: ArtifactVocabulary,
    stamp: JsonObject,
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> None:
    for value in _object_list(member.get("injuries"), f"Member {member_id} injuries"):
        external_id = _required_string(value, "id")
        injury_id = f"{member_id}:injury:{external_id}"
        finding_mentions = _clinical_finding_mentions(value)
        directives = _clinical_directives(value)
        properties = {key: item for key, item in value.items() if key != "id"}
        properties.update(
            external_id=external_id,
            member_id=member_id,
            clinical_finding_mentions=finding_mentions,
            clinical_directive_mentions=[
                directive.raw_text for directive in directives
            ],
            **stamp,
        )
        node_rows["MemberInjury"].append(
            Node(injury_id, _neo4j_properties(properties, injury_id))
        )
        _append_edge(
            member_id,
            "Member",
            "has",
            injury_id,
            "MemberInjury",
            stamp,
            edge_rows,
        )
        for mention in finding_mentions:
            resolution = _exact_resolution(mention, finding_vocab)
            if resolution is None:
                continue
            _append_edge(
                injury_id,
                "MemberInjury",
                "exactMatch",
                cast(str, resolution.concept_id),
                "ClinicalFinding",
                _bridge_properties(stamp, resolution),
                edge_rows,
            )
        for directive in directives:
            target_label: NodeLabel = "MovementPattern"
            resolution = _exact_resolution(directive.raw_text, movement_pattern_vocab)
            if resolution is None:
                target_label = "Joint"
                resolution = _exact_resolution(directive.raw_text, joint_vocab)
            if resolution is None:
                continue
            _append_edge(
                injury_id,
                "MemberInjury",
                "clinicalDirective",
                cast(str, resolution.concept_id),
                target_label,
                {
                    **_bridge_properties(stamp, resolution),
                    "status": directive.status,
                },
                edge_rows,
            )


def _append_workout_sessions(
    member: JsonObject,
    member_id: str,
    exercise_vocab: ArtifactVocabulary,
    stamp: JsonObject,
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> list[tuple[str, JsonObject]]:
    sessions: list[tuple[str, JsonObject]] = []
    workouts = _object_list(
        member.get("workout_history"), f"Member {member_id} workout_history"
    )
    for workout in workouts:
        workout_date = _required_string(workout, "date")
        session_id = f"{member_id}:workout:{workout_date}"
        exercise_mentions = _string_list(
            workout.get("exercises"), f"WorkoutSession {session_id} exercises"
        )
        properties = {key: item for key, item in workout.items() if key != "exercises"}
        properties.update(
            member_id=member_id, exercise_mentions=exercise_mentions, **stamp
        )
        node_rows["WorkoutSession"].append(
            Node(session_id, _neo4j_properties(properties, session_id))
        )
        sessions.append((session_id, properties))
        _append_edge(
            member_id,
            "Member",
            "performed",
            session_id,
            "WorkoutSession",
            stamp,
            edge_rows,
        )
        _append_bridge_edges(
            session_id,
            "WorkoutSession",
            "included",
            "Exercise",
            exercise_mentions,
            exercise_vocab,
            stamp,
            edge_rows,
        )
    return sessions


def _append_observations(
    member: JsonObject,
    member_id: str,
    generated_for: str,
    messages: list[tuple[str, JsonObject]],
    stamp: JsonObject,
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> dict[str, list[str]]:
    observations: dict[str, list[str]] = defaultdict(list)
    adherence = _object(member.get("adherence"), f"Member {member_id} adherence")
    for weekly in _object_list(
        adherence.get("weekly_completion_pct"),
        f"Member {member_id} adherence.weekly_completion_pct",
    ):
        observed_at = _required_string(weekly, "week_of")
        _append_observation(
            member_id,
            "adherence-week",
            observed_at,
            {"value": weekly.get("pct"), "unit": "percent"},
            stamp,
            observations,
            node_rows,
            edge_rows,
        )

    biomarkers = _object(member.get("biomarkers"), f"Member {member_id} biomarkers")
    _append_observation(
        member_id,
        "resting-hr",
        generated_for,
        {"value": biomarkers.get("resting_hr_bpm"), "unit": "bpm"},
        stamp,
        observations,
        node_rows,
        edge_rows,
    )
    _append_observation(
        member_id,
        "hrv",
        generated_for,
        {"value": biomarkers.get("hrv_ms"), "unit": "ms"},
        stamp,
        observations,
        node_rows,
        edge_rows,
    )

    sleep_values = _number_list(
        biomarkers.get("sleep_hours_last_7_days"),
        f"Member {member_id} biomarkers.sleep_hours_last_7_days",
    )
    sleep_start = date.fromisoformat(generated_for) - timedelta(days=len(sleep_values))
    for offset, value in enumerate(sleep_values):
        observed_at = (sleep_start + timedelta(days=offset)).isoformat()
        _append_observation(
            member_id,
            "sleep-night",
            observed_at,
            {"value": value, "unit": "hours"},
            stamp,
            observations,
            node_rows,
            edge_rows,
        )

    daily_message_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"member": 0, "coach": 0}
    )
    for _, properties in messages:
        observed_at = (
            datetime.fromisoformat(cast(str, properties["timestamp"]))
            .date()
            .isoformat()
        )
        sender = cast(str, properties["sender"])
        daily_message_counts[observed_at][sender] += 1
    for observed_at, counts in sorted(daily_message_counts.items()):
        _append_observation(
            member_id,
            "message-pattern-day",
            observed_at,
            {
                "value": counts["member"] + counts["coach"],
                "unit": "messages",
                "member_count": counts["member"],
                "coach_count": counts["coach"],
            },
            stamp,
            observations,
            node_rows,
            edge_rows,
        )

    for weight in _object_list(
        biomarkers.get("weight_trend_kg"),
        f"Member {member_id} biomarkers.weight_trend_kg",
    ):
        observed_at = _required_string(weight, "date")
        _append_observation(
            member_id,
            "weight",
            observed_at,
            {"value": weight.get("kg"), "unit": "kg"},
            stamp,
            observations,
            node_rows,
            edge_rows,
        )

    labs = _object(member.get("labs"), f"Member {member_id} labs")
    for field, kind in (("blood_panel", "blood-panel"), ("dexa_scan", "dexa")):
        lab = _object(labs.get(field), f"Member {member_id} labs.{field}")
        observed_at = _required_string(lab, "date")
        values = {key: item for key, item in lab.items() if key != "date"}
        _append_observation(
            member_id,
            kind,
            observed_at,
            values,
            stamp,
            observations,
            node_rows,
            edge_rows,
        )
    return observations


def _append_observation(
    member_id: str,
    kind: str,
    observed_at: str,
    values: JsonObject,
    stamp: JsonObject,
    observations: dict[str, list[str]],
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> None:
    observation_id = f"{member_id}:observation:{kind}:{observed_at}"
    properties = {
        "member_id": member_id,
        "kind": kind,
        "observed_at": observed_at,
        **values,
        **stamp,
    }
    node_rows["Observation"].append(
        Node(observation_id, _neo4j_properties(properties, observation_id))
    )
    observations[kind].append(observation_id)
    _append_edge(
        member_id,
        "Member",
        "observed",
        observation_id,
        "Observation",
        stamp,
        edge_rows,
    )


def _append_chat_messages(
    member: JsonObject,
    member_id: str,
    stamp: JsonObject,
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> list[tuple[str, JsonObject]]:
    messages: list[tuple[str, JsonObject]] = []
    chat_history = _object_list(
        member.get("chat_history"), f"Member {member_id} chat_history"
    )
    for message in chat_history:
        timestamp = _required_string(message, "ts")
        sender = _required_string(message, "from")
        text = _required_string(message, "text")
        digest = sha256(f"{sender}\0{text}".encode()).hexdigest()[:12]
        message_id = f"{member_id}:chat:{timestamp}:{digest}"
        properties: JsonObject = {
            "member_id": member_id,
            "timestamp": timestamp,
            "sender": sender,
            "text": text,
            **stamp,
        }
        if "attachments" in message:
            properties["attachments_json"] = json.dumps(
                message["attachments"], sort_keys=True, separators=(",", ":")
            )
        node_rows["ChatMessage"].append(
            Node(message_id, _neo4j_properties(properties, message_id))
        )
        messages.append((message_id, properties))
        if sender not in ("member", "coach"):
            raise ValueError(
                f"ChatMessage {message_id} has unsupported sender {sender}"
            )
        _append_edge(
            member_id,
            "Member",
            "said" if sender == "member" else "received",
            message_id,
            "ChatMessage",
            stamp,
            edge_rows,
        )
    return messages


def _append_barriers(
    churn_risk: JsonObject,
    member_id: str,
    stamp: JsonObject,
    observations: dict[str, list[str]],
    sessions: list[tuple[str, JsonObject]],
    messages: list[tuple[str, JsonObject]],
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> list[str]:
    reasons = _string_list(churn_risk.get("reasons"), f"Member {member_id} barriers")
    risk_level = _required_string(churn_risk, "level")
    barriers: list[str] = []

    adherence_reason = next(
        (reason for reason in reasons if "adherence" in reason.casefold()), None
    )
    adherence_evidence = observations.get("adherence-week", [])
    if adherence_reason is not None and len(adherence_evidence) >= 2:
        barrier_id = _append_barrier(
            member_id,
            "adherence-decline",
            "https://github.com/EBehaviourChange-COPPER/ontology/blob/main/COPPER_3048",
            adherence_reason,
            risk_level,
            [(node_id, "Observation") for node_id in adherence_evidence],
            stamp,
            node_rows,
            edge_rows,
        )
        barriers.append(barrier_id)

    fatigue_reason = next(
        (
            reason
            for reason in reasons
            if any(term in reason.casefold() for term in ("skipped", "fatigue", "work"))
        ),
        None,
    )
    missed_sessions: list[tuple[str, NodeLabel]] = [
        (session_id, "WorkoutSession")
        for session_id, properties in sessions
        if properties.get("completed") is False
    ]
    fatigue_messages: list[tuple[str, NodeLabel]] = [
        (message_id, "ChatMessage")
        for message_id, properties in messages
        if any(
            term in cast(str, properties["text"]).casefold()
            for term in ("skipped", "wiped", "work")
        )
    ]
    fatigue_evidence = [*missed_sessions, *fatigue_messages]
    if fatigue_reason is not None and fatigue_evidence:
        barrier_id = _append_barrier(
            member_id,
            "work-fatigue",
            "http://purl.obolibrary.org/obo/MFOEM_000080",
            fatigue_reason,
            risk_level,
            fatigue_evidence,
            stamp,
            node_rows,
            edge_rows,
        )
        barriers.append(barrier_id)
    return barriers


def _append_barrier(
    member_id: str,
    kind: str,
    copper_id: str,
    reason: str,
    risk_level: str,
    evidence: list[tuple[str, NodeLabel]],
    stamp: JsonObject,
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> str:
    barrier_id = f"{member_id}:barrier:{kind}"
    properties = {
        "member_id": member_id,
        "kind": kind,
        "copper_id": copper_id,
        "reason": reason,
        "risk_level": risk_level,
        **stamp,
    }
    node_rows["Barrier"].append(Node(barrier_id, properties))
    for evidence_id, evidence_label in evidence:
        _append_edge(
            barrier_id,
            "Barrier",
            "evidencedBy",
            evidence_id,
            evidence_label,
            stamp,
            edge_rows,
        )
    return barrier_id


def _append_coach_tasks(
    coach_brief: JsonObject,
    member_id: str,
    stamp: JsonObject,
    sessions: list[tuple[str, JsonObject]],
    barrier_ids: list[str],
    node_rows: dict[NodeLabel, list[Node]],
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> None:
    generated_for = _required_string(coach_brief, "generated_for")
    tasks = _object_list(
        coach_brief.get("morning_tasks"), f"Member {member_id} morning_tasks"
    )
    completed_sessions = [
        (session_id, properties)
        for session_id, properties in sessions
        if properties.get("completed") is True
    ]
    latest_completed_id = (
        max(
            completed_sessions,
            key=lambda item: cast(str, item[1]["date"]),
        )[0]
        if completed_sessions
        else None
    )
    for task in tasks:
        task_type = _required_string(task, "type")
        task_text = _required_string(task, "text")
        digest = sha256(f"{task_type}\0{task_text}".encode()).hexdigest()[:12]
        task_id = f"{member_id}:coach-task:{generated_for}:{digest}"
        properties = {
            "member_id": member_id,
            "generated_for": generated_for,
            "type": task_type,
            "text": task_text,
            "status": "open",
            **stamp,
        }
        node_rows["CoachTask"].append(Node(task_id, properties))
        if task_type == "celebrate" and latest_completed_id is not None:
            _append_edge(
                task_id,
                "CoachTask",
                "addresses",
                latest_completed_id,
                "WorkoutSession",
                stamp,
                edge_rows,
            )
        elif task_type == "review_risk":
            for barrier_id in barrier_ids:
                _append_edge(
                    task_id,
                    "CoachTask",
                    "addresses",
                    barrier_id,
                    "Barrier",
                    stamp,
                    edge_rows,
                )


def _append_bridge_edges(
    source_id: str,
    source_label: NodeLabel,
    edge_type: EdgeType,
    target_label: NodeLabel,
    mentions: list[str],
    vocab: Vocabulary,
    stamp: JsonObject,
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> None:
    for mention in mentions:
        resolution = _exact_resolution(mention, vocab)
        if resolution is None:
            continue
        _append_edge(
            source_id,
            source_label,
            edge_type,
            cast(str, resolution.concept_id),
            target_label,
            _bridge_properties(stamp, resolution),
            edge_rows,
        )


def _append_edge(
    source_id: str,
    source_label: NodeLabel,
    edge_type: EdgeType,
    target_id: str,
    target_label: NodeLabel,
    properties: JsonObject,
    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]],
) -> None:
    edge_id = f"{source_id}:{edge_type}:{target_id}"
    edge_rows[(source_label, edge_type, target_label)].append(
        Edge(edge_id, source_id, target_id, properties)
    )


def _exact_resolution(mention: str, vocab: Vocabulary) -> Resolution | None:
    resolution = resolve(mention, vocab)
    if resolution.pass_ != "exact" or resolution.concept_id is None:
        return None
    return resolution


def _bridge_properties(stamp: JsonObject, resolution: Resolution) -> JsonObject:
    return {
        "raw_text": resolution.raw_text,
        "modifiers": list(resolution.modifiers),
        "confidence": resolution.confidence,
        **stamp,
    }


def _clinical_finding_mentions(injury: JsonObject) -> list[str]:
    mentions = [
        value
        for field in ("condition", "diagnosis", "finding")
        if isinstance((value := injury.get(field)), str) and value
    ]
    hint = injury.get("snomedct_hint")
    if isinstance(hint, str) and hint:
        query = hint.removeprefix("Look up ").split("/", maxsplit=1)[0].strip()
        if query:
            mentions.append(query)
    return list(dict.fromkeys(mentions))


def _clinical_directives(injury: JsonObject) -> list[_ClinicalDirective]:
    notes = injury.get("notes")
    if not isinstance(notes, str):
        return []
    directives: list[_ClinicalDirective] = []
    for match in _CLINICAL_DIRECTIVE.finditer(notes):
        status = _directive_status(match.group(1).lower())
        directives.extend(
            _ClinicalDirective(status, raw_text)
            for value in _DIRECTIVE_SEPARATOR.split(match.group(2))
            if (raw_text := value.strip())
        )
    return directives


def _directive_status(marker: str) -> DirectiveStatus:
    if marker in {"cleared for", "clear for", "allowed", "allow"}:
        return "clear"
    if marker in {"caution", "modify", "limit"}:
        return "caution"
    return "exclude"


def _movement_pattern_vocabulary(
    exercise_path: Path, synonyms_path: Path
) -> _MovementPatternVocabulary:
    vocabulary = ArtifactVocabulary.from_file(
        exercise_path,
        kind="MovementPattern",
        synonyms_path=synonyms_path,
    )
    return _MovementPatternVocabulary(
        tuple(
            VocabularyConcept(
                concept_id=concept.concept_id,
                preferred_term=concept.preferred_term,
                aliases=tuple(
                    dict.fromkeys(
                        (*concept.aliases, *_movement_aliases(concept.preferred_term))
                    )
                ),
            )
            for concept in vocabulary.concepts()
        )
    )


def _movement_aliases(preferred_term: str) -> tuple[str, ...]:
    leaf = preferred_term.rsplit(" - ", maxsplit=1)[-1]
    return tuple(dict.fromkeys((leaf, f"{leaf}s")))


def _neo4j_properties(properties: JsonObject, node_id: str) -> JsonObject:
    valid_scalars = (str, int, float, bool)
    for key, value in properties.items():
        if value is None or isinstance(value, valid_scalars):
            continue
        if isinstance(value, list) and all(
            isinstance(item, valid_scalars) for item in value
        ):
            continue
        raise TypeError(f"Node {node_id} property {key!r} cannot be stored in Neo4j")
    return properties


def _object_list(value: Any, description: str) -> list[JsonObject]:
    if not isinstance(value, list):
        raise TypeError(f"{description} must be a list")
    return [_object(item, description) for item in value]


def _string_list(value: Any, description: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{description} must be a list of strings")
    return value


def _number_list(value: Any, description: str) -> list[int | float]:
    if not isinstance(value, list) or not all(
        isinstance(item, int | float) and not isinstance(item, bool) for item in value
    ):
        raise TypeError(f"{description} must be a list of numbers")
    return value


def _read_object(path: Path) -> JsonObject:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _catalog_batches(
    exercises: list[JsonObject], version: str
) -> tuple[list[NodeBatch], list[EdgeBatch]]:
    exercise_rows: list[Node] = []
    taxonomy_rows: dict[NodeLabel, dict[str, Node]] = defaultdict(dict)
    edge_rows: dict[tuple[NodeLabel, EdgeType], list[Edge]] = defaultdict(list)
    taxonomy_fields = {field for field, _, _, _ in EXERCISE_TAXONOMIES}

    for exercise in exercises:
        exercise_id = _required_string(exercise, "id")
        properties = {
            key: value
            for key, value in exercise.items()
            if key != "id" and key not in taxonomy_fields
        }
        properties.update(source=CATALOG_SOURCE, version=version)
        exercise_rows.append(Node(id=exercise_id, properties=properties))

        for field, label, edge_type, id_prefix in EXERCISE_TAXONOMIES:
            terms = exercise.get(field)
            if not isinstance(terms, list) or not all(
                isinstance(term, str) for term in terms
            ):
                raise ValueError(f"Exercise {exercise_id} has invalid {field}")

            for term in terms:
                target_id = f"fkg:{id_prefix}/{_slug(term)}"
                taxonomy_rows[label][target_id] = Node(
                    id=target_id,
                    properties={
                        "name": term,
                        "source": CATALOG_SOURCE,
                        "version": version,
                    },
                )
                edge_id = f"{exercise_id}:{edge_type}:{target_id}"
                edge_rows[(label, edge_type)].append(
                    Edge(
                        id=edge_id,
                        source_id=exercise_id,
                        target_id=target_id,
                        properties={
                            "source": CATALOG_SOURCE,
                            "version": version,
                        },
                    )
                )

    _require_unique_ids(exercise_rows, CATALOG_SOURCE)
    nodes = [NodeBatch("Exercise", exercise_rows)]
    nodes.extend(
        NodeBatch(label, list(rows.values())) for label, rows in taxonomy_rows.items()
    )
    edges = [
        EdgeBatch("Exercise", edge_type, target_label, rows)
        for (target_label, edge_type), rows in edge_rows.items()
    ]
    return nodes, edges


def _snomed_batches(
    artifact: JsonObject,
) -> tuple[list[NodeBatch], list[EdgeBatch], dict[str, NodeLabel]]:
    source, version = _artifact_stamp(artifact)
    concepts = artifact.get("concepts")
    edges = artifact.get("edges")
    if not isinstance(concepts, list) or not isinstance(edges, list):
        raise TypeError("SNOMED artifact must contain concepts and edges")

    node_rows: dict[NodeLabel, list[Node]] = defaultdict(list)
    concept_labels: dict[str, NodeLabel] = {}
    for value in concepts:
        concept = _object(value, "SNOMED concept")
        concept_id = _required_string(concept, "id")
        label = _node_label(_required_string(concept, "kind"))
        if label not in ("AnatomicalStructure", "ClinicalFinding"):
            raise ValueError(f"Unsupported SNOMED concept kind: {label}")
        if concept_id in concept_labels:
            raise ValueError(f"Duplicate SNOMED concept id: {concept_id}")
        concept_labels[concept_id] = label
        properties = {
            key: item for key, item in concept.items() if key not in {"id", "kind"}
        }
        properties.update(source=source, version=version)
        node_rows[label].append(Node(id=concept_id, properties=properties))

    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]] = defaultdict(
        list
    )
    for value in edges:
        edge = _object(value, "SNOMED edge")
        source_id = _required_string(edge, "source_id")
        target_id = _required_string(edge, "target_id")
        edge_type = _edge_type(_required_string(edge, "type"))
        key = (
            _concept_label(concept_labels, source_id),
            edge_type,
            _concept_label(concept_labels, target_id),
        )
        properties = {
            item_key: item
            for item_key, item in edge.items()
            if item_key not in {"id", "source_id", "target_id", "type"}
        }
        properties.update(source=source, version=version)
        edge_rows[key].append(
            Edge(
                id=_required_string(edge, "id"),
                source_id=source_id,
                target_id=target_id,
                properties=properties,
            )
        )

    nodes = [NodeBatch(label, rows) for label, rows in node_rows.items()]
    grouped_edges = [
        EdgeBatch(source_label, edge_type, target_label, rows)
        for (source_label, edge_type, target_label), rows in edge_rows.items()
    ]
    return nodes, grouped_edges, concept_labels


def _mapping_batches(
    artifact: JsonObject,
    concept_labels: dict[str, NodeLabel],
    injury_findings: dict[str, str],
) -> list[EdgeBatch]:
    source, version = _artifact_stamp(artifact)
    mappings = artifact.get("mappings")
    if not isinstance(mappings, list):
        raise TypeError("SKOS artifact must contain mappings")

    rows_by_labels: dict[tuple[NodeLabel, NodeLabel], list[Edge]] = defaultdict(list)
    mapped_injuries: set[str] = set()
    for value in mappings:
        mapping = _object(value, "SKOS mapping")
        source_id = _required_string(mapping, "source_id")
        if source_id.startswith("fkg:injury/"):
            source_label: NodeLabel = "Injury"
            expected_target_id = injury_findings.get(source_id)
            if expected_target_id is None:
                raise ValueError(f"Unknown authored Injury mapping source: {source_id}")
            mapped_injuries.add(source_id)
        elif source_id.startswith("fkg:joint/"):
            source_label = "Joint"
            expected_target_id = None
        else:
            raise ValueError(f"Unsupported exactMatch source: {source_id}")
        predicate = _required_string(mapping, "predicate")
        if predicate != "skos:exactMatch":
            raise ValueError(f"Unsupported SKOS predicate: {predicate}")
        target_id = _required_string(mapping, "target_id")
        if expected_target_id is not None and target_id != expected_target_id:
            raise ValueError(
                f"Authored Injury {source_id} must exactMatch {expected_target_id}"
            )
        target_label = _concept_label(concept_labels, target_id)
        properties = {
            key: item
            for key, item in mapping.items()
            if key not in {"id", "source_id", "target_id"}
        }
        properties.update(source=source, version=version)
        rows_by_labels[(source_label, target_label)].append(
            Edge(
                id=_required_string(mapping, "id"),
                source_id=source_id,
                target_id=target_id,
                properties=properties,
            )
        )

    missing_mappings = injury_findings.keys() - mapped_injuries
    if missing_mappings:
        missing = ", ".join(sorted(missing_mappings))
        raise ValueError(f"Authored Injuries lack exactMatch mappings: {missing}")

    return [
        EdgeBatch(source_label, "exactMatch", target_label, rows)
        for (source_label, target_label), rows in rows_by_labels.items()
    ]


def _condition_batches(
    artifact: AuthoredConditions,
    catalog_node_batches: list[NodeBatch],
    concept_labels: dict[str, NodeLabel],
) -> tuple[list[NodeBatch], list[EdgeBatch], dict[str, str]]:
    catalog_ids = {
        batch.label: {node.id for node in batch.rows} for batch in catalog_node_batches
    }
    injury_nodes: dict[str, Node] = {}
    injury_findings: dict[str, str] = {}
    edge_rows: dict[NodeLabel, list[Edge]] = defaultdict(list)

    for row in artifact.rows:
        if concept_labels.get(row.clinical_finding_id) != "ClinicalFinding":
            raise ValueError(
                f"Authored Injury {row.injury_id} references unknown ClinicalFinding: "
                f"{row.clinical_finding_id}"
            )
        if row.target_id not in catalog_ids.get(row.target_kind, set()):
            raise ValueError(
                f"Authored Injury {row.injury_id} references unknown "
                f"{row.target_kind}: {row.target_id}"
            )

        existing_finding = injury_findings.get(row.injury_id)
        if existing_finding is not None and existing_finding != row.clinical_finding_id:
            raise ValueError(
                f"Authored Injury {row.injury_id} has conflicting ClinicalFindings"
            )
        existing_node = injury_nodes.get(row.injury_id)
        if existing_node is not None and existing_node.properties["name"] != row.name:
            raise ValueError(f"Authored Injury {row.injury_id} has conflicting names")

        injury_findings[row.injury_id] = row.clinical_finding_id
        injury_nodes[row.injury_id] = Node(
            id=row.injury_id,
            properties={
                "name": row.name,
                "clinical_finding_id": row.clinical_finding_id,
                "source": CONDITIONS_SOURCE,
                "version": artifact.version,
            },
        )
        edge_rows[row.target_kind].append(
            Edge(
                id=f"{row.injury_id}:contraindicates:{row.target_id}",
                source_id=row.injury_id,
                target_id=row.target_id,
                properties={
                    "level": row.level,
                    "note": row.note,
                    "citation": row.citation,
                    "citation_url": row.citation_url,
                    "source": CONDITIONS_SOURCE,
                    "version": artifact.version,
                },
            )
        )

    nodes = [NodeBatch("Injury", list(injury_nodes.values()))]
    edges = [
        EdgeBatch("Injury", "contraindicates", target_label, rows)
        for target_label, rows in edge_rows.items()
    ]
    return nodes, edges, injury_findings


def _artifact_stamp(artifact: JsonObject) -> tuple[str, str]:
    return (
        _required_string(artifact, "artifact_id"),
        _required_string(artifact, "version"),
    )


def _required_string(value: JsonObject, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Expected non-empty string at {key}")
    return item


def _object(value: Any, description: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(f"{description} must be a JSON object")
    return value


def _node_label(value: str) -> NodeLabel:
    if value not in NODE_LABELS:
        raise ValueError(f"Unsupported node label: {value}")
    return value


def _edge_type(value: str) -> EdgeType:
    if value not in KG1_EDGE_TYPES:
        raise ValueError(f"Unsupported edge type: {value}")
    return value


def _concept_label(labels: dict[str, NodeLabel], concept_id: str) -> NodeLabel:
    try:
        return labels[concept_id]
    except KeyError as error:
        raise ValueError(f"Unknown SNOMED concept id: {concept_id}") from error


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError(f"Cannot create stable id from {value!r}")
    return slug


def _require_unique_ids(nodes: list[Node], source: str) -> None:
    ids = [node.id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{source} contains duplicate ids")


def _ensure_constraints(session: Session) -> None:
    for label in NODE_LABELS:
        graph_name = "kg1" if label in KG1_NODE_LABELS else "kg2"
        constraint_name = f"{graph_name}_{_slug(label)}_id"
        session.run(
            _cypher(
                f"""
            CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
            FOR (node:`{label}`) REQUIRE node.id IS UNIQUE
            """
            )
        ).consume()


def _merge_payload(
    transaction: ManagedTransaction,
    payload: KG1Payload | KG2Payload,
    ingested_at: str,
) -> None:
    for batch in payload.nodes:
        transaction.run(
            _cypher(
                f"""
            UNWIND $rows AS row
            MERGE (node:`{batch.label}` {{id: row.id}})
            SET node += CASE
                WHEN node.source = $coach_action_source THEN {{}}
                ELSE row.properties
            END
            SET node.ingested_at = coalesce(node.ingested_at, datetime($ingested_at))
            """
            ),
            rows=[asdict(node) for node in batch.rows],
            ingested_at=ingested_at,
            coach_action_source=COACH_ACTION_SOURCE,
        ).consume()

    for batch in payload.edges:
        legacy_property_cleanup = (
            "REMOVE edge.verdict" if batch.edge_type == "contraindicates" else ""
        )
        transaction.run(
            _cypher(
                f"""
            UNWIND $rows AS row
            MATCH (source:`{batch.source_label}` {{id: row.source_id}})
            MATCH (target:`{batch.target_label}` {{id: row.target_id}})
            MERGE (source)-[edge:`{batch.edge_type}` {{id: row.id}}]->(target)
            SET edge += row.properties
            SET edge.ingested_at = coalesce(edge.ingested_at, datetime($ingested_at))
            {legacy_property_cleanup}
            """
            ),
            rows=[asdict(edge) for edge in batch.rows],
            ingested_at=ingested_at,
        ).consume()


def _merge_and_reconcile_kg2_payload(
    transaction: ManagedTransaction,
    payload: KG2Payload,
    ingested_at: str,
) -> None:
    _merge_payload(transaction, payload, ingested_at)
    seed_sources = sorted(
        {
            cast(str, node.properties["source"])
            for batch in payload.nodes
            for node in batch.rows
        }
    )
    for batch in payload.nodes:
        transaction.run(
            _cypher(
                f"""
            MATCH (node:`{batch.label}`)
            WHERE node.source IN $seed_sources
              AND NOT node.id IN $current_ids
            DETACH DELETE node
            """
            ),
            seed_sources=seed_sources,
            current_ids=[node.id for node in batch.rows],
        ).consume()


def _merge_and_reconcile_kg1_payload(
    transaction: ManagedTransaction,
    payload: KG1Payload,
    ingested_at: str,
) -> None:
    _merge_payload(transaction, payload, ingested_at)
    current_ids = {
        label: [
            node.id
            for batch in payload.nodes
            if batch.label == label
            for node in batch.rows
        ]
        for label in KG1_NODE_LABELS
    }
    for label in KG1_NODE_LABELS:
        transaction.run(
            _cypher(
                f"""
            MATCH (node:`{label}`)
            WHERE node.source IN $seed_sources
              AND NOT node.id IN $current_ids
            DETACH DELETE node
            """
            ),
            seed_sources=list(payload.seed_sources),
            current_ids=current_ids[label],
        ).consume()


def _read_kg1_counts(session: Session) -> KG1Counts:
    node_counts = {
        label: _count(
            session, _cypher(f"MATCH (node:`{label}`) RETURN count(node) AS count")
        )
        for label in KG1_NODE_LABELS
    }
    edge_counts = {
        edge_type: _count(
            session,
            _cypher(
                "MATCH (source)-[edge]->() WHERE "
                f"({_source_label_predicate(KG1_EDGE_SOURCE_LABELS[edge_type])}) "
                f"AND type(edge) = '{edge_type}' "
                "RETURN count(edge) AS count"
            ),
        )
        for edge_type in KG1_EDGE_TYPES
    }
    return KG1Counts(nodes=node_counts, edges=edge_counts)


def _source_label_predicate(labels: tuple[NodeLabel, ...]) -> str:
    return " OR ".join(f"source:`{label}`" for label in labels)


def _read_kg2_counts(session: Session) -> KG2Counts:
    node_counts = {
        label: _count(
            session, _cypher(f"MATCH (node:`{label}`) RETURN count(node) AS count")
        )
        for label in KG2_NODE_LABELS
    }
    edge_counts = {
        edge_type: _count(
            session,
            _cypher(
                f"MATCH (source:`{KG2_EDGE_SOURCE_LABELS[edge_type]}`)"
                f"-[edge]->() WHERE type(edge) = '{edge_type}' "
                "RETURN count(edge) AS count"
            ),
        )
        for edge_type in KG2_EDGE_TYPES
    }
    return KG2Counts(nodes=node_counts, edges=edge_counts)


def _cypher(query: str) -> LiteralString:
    # Interpolated fragments come only from the closed schema constants.
    return cast(LiteralString, query)


def _count(session: Session, query: LiteralString) -> int:
    record = session.run(query).single(strict=True)
    return cast(int, record["count"])
