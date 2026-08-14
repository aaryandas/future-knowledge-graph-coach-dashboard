from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from langchain_core.tools import BaseTool, tool
from neo4j import Record

from app.graph.constants import ObservationKind
from app.graph.relevance import (
    as_observation_kind,
    current_date,
    observation_freshness,
    scope_observations,
)
from app.graph.store import neo4j_session

type ObservationScalar = str | int | float | bool
type ChatSender = Literal["member", "coach"]


@dataclass(frozen=True)
class _JsonToolResult:
    def __str__(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass(frozen=True)
class ObservationMeasurement:
    name: str
    value: ObservationScalar


@dataclass(frozen=True)
class ObservationData:
    node_id: str
    kind: ObservationKind
    observed_at: str
    age_days: int
    stale: bool
    value: int | float | None
    unit: str | None
    measurements: tuple[ObservationMeasurement, ...]


@dataclass(frozen=True)
class ObservationsResult(_JsonToolResult):
    observations: tuple[ObservationData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkoutSessionData:
    node_id: str
    date: str
    title: str
    planned: bool
    completed: bool
    duration_min: int
    rpe: int | float | None
    exercise_mentions: tuple[str, ...]
    exercise_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkoutSessionsResult(_JsonToolResult):
    workout_sessions: tuple[WorkoutSessionData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChatMessageData:
    node_id: str
    timestamp: str
    sender: ChatSender
    text: str
    attachments_json: str | None


@dataclass(frozen=True)
class ChatMessagesResult(_JsonToolResult):
    chat_messages: tuple[ChatMessageData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class GoalData:
    node_id: str
    external_id: str
    text: str
    priority: int
    target_date: str | None


@dataclass(frozen=True)
class MemberGoalsResult(_JsonToolResult):
    goals: tuple[GoalData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemberInjuryData:
    node_id: str
    external_id: str
    region: str
    joint: str
    status: str
    severity: str
    since: str
    notes: str
    snomedct_hint: str | None
    clinical_finding_mentions: tuple[str, ...]
    clinical_finding_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemberInjuriesResult(_JsonToolResult):
    injuries: tuple[MemberInjuryData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class BarrierData:
    node_id: str
    kind: str
    copper_id: str
    reason: str
    risk_level: str
    evidence_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class CoachTaskData:
    node_id: str
    generated_for: str
    type: str
    text: str
    status: str
    addressed_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MorningBriefData:
    generated_for: str
    churn_risk_level: str
    churn_risk_reasons: tuple[str, ...]
    barriers: tuple[BarrierData, ...]
    coach_tasks: tuple[CoachTaskData, ...]


@dataclass(frozen=True)
class MorningBriefResult(_JsonToolResult):
    morning_brief: MorningBriefData | None
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemberProfileData:
    node_id: str
    name: str
    age: int
    sex: str
    height_cm: int | float
    weight_kg: int | float
    timezone: str
    member_since: str
    coach_id: str
    tier: str
    preferred_session_minutes: int
    training_days_per_week: int
    preferred_days: tuple[str, ...]
    preference_notes: str
    equipment_available: tuple[str, ...]
    dislikes: tuple[str, ...]


@dataclass(frozen=True)
class MemberProfileResult(_JsonToolResult):
    profile: MemberProfileData | None
    node_ids: tuple[str, ...]


@tool
def get_observations(member_id: str, as_of: date | None = None) -> ObservationsResult:
    """Read current `Member -[:observed]-> Observation` values and latest labs, newest first."""
    read_date = as_of or current_date()
    with neo4j_session() as session:
        records = session.run(
            "MATCH (member:Member {id: $member_id}) "
            "OPTIONAL MATCH (member)-[:observed]->(observation:Observation) "
            "RETURN member.id AS member_node_id, observation.id AS node_id, "
            "properties(observation) AS properties "
            "ORDER BY observation.observed_at DESC, observation.kind, observation.id",
            member_id=member_id,
        )
        member_node_id: str | None = None
        observations: list[ObservationData] = []
        observation_node_ids: list[str] = []
        for record in records:
            member_node_id = _optional_record_string(record, "member_node_id")
            node_id = _optional_record_string(record, "node_id")
            if node_id is None:
                continue
            properties = _record_properties(record)
            observations.append(_observation_data(node_id, properties, as_of=read_date))
        scoped_observations = scope_observations(observations)
        observation_node_ids.extend(
            observation.node_id for observation in scoped_observations
        )
    return ObservationsResult(
        observations=scoped_observations,
        node_ids=_node_ids(member_node_id, observation_node_ids),
    )


@tool
def get_workout_sessions(member_id: str) -> WorkoutSessionsResult:
    """Read `Member -[:performed]-> WorkoutSession -[:included]-> Exercise`, newest first."""
    with neo4j_session() as session:
        records = session.run(
            "MATCH (member:Member {id: $member_id}) "
            "OPTIONAL MATCH (member)-[:performed]->(workout:WorkoutSession) "
            "OPTIONAL MATCH (workout)-[:included]->(exercise:Exercise) "
            "RETURN member.id AS member_node_id, workout.id AS node_id, "
            "properties(workout) AS properties, "
            "[node IN collect(DISTINCT exercise) WHERE node IS NOT NULL | node.id] "
            "AS exercise_ids, workout.date AS sort_date "
            "ORDER BY sort_date DESC, node_id",
            member_id=member_id,
        )
        member_node_id: str | None = None
        workout_sessions: list[WorkoutSessionData] = []
        workout_node_ids: list[str] = []
        exercise_node_ids: list[str] = []
        for record in records:
            member_node_id = _optional_record_string(record, "member_node_id")
            node_id = _optional_record_string(record, "node_id")
            if node_id is None:
                continue
            properties = _record_properties(record)
            exercise_ids = tuple(sorted(_record_strings(record, "exercise_ids")))
            workout_sessions.append(
                _workout_session_data(node_id, properties, exercise_ids)
            )
            workout_node_ids.append(node_id)
            exercise_node_ids.extend(exercise_ids)
    return WorkoutSessionsResult(
        workout_sessions=tuple(workout_sessions),
        node_ids=_node_ids(
            member_node_id,
            workout_node_ids,
            exercise_node_ids,
        ),
    )


@tool
def get_chat_messages(member_id: str) -> ChatMessagesResult:
    """Read `Member -[:said|received]-> ChatMessage`, newest first."""
    with neo4j_session() as session:
        records = session.run(
            "MATCH (member:Member {id: $member_id}) "
            "OPTIONAL MATCH (member)-[:said|received]->(message:ChatMessage) "
            "RETURN member.id AS member_node_id, message.id AS node_id, "
            "properties(message) AS properties "
            "ORDER BY message.timestamp DESC, message.id",
            member_id=member_id,
        )
        member_node_id: str | None = None
        chat_messages: list[ChatMessageData] = []
        message_node_ids: list[str] = []
        for record in records:
            member_node_id = _optional_record_string(record, "member_node_id")
            node_id = _optional_record_string(record, "node_id")
            if node_id is None:
                continue
            chat_messages.append(
                _chat_message_data(node_id, _record_properties(record))
            )
            message_node_ids.append(node_id)
    return ChatMessagesResult(
        chat_messages=tuple(chat_messages),
        node_ids=_node_ids(member_node_id, message_node_ids),
    )


@tool
def get_member_goals(member_id: str) -> MemberGoalsResult:
    """Read `Member -[:pursues]-> Goal`, highest priority first."""
    with neo4j_session() as session:
        records = session.run(
            "MATCH (member:Member {id: $member_id}) "
            "OPTIONAL MATCH (member)-[:pursues]->(goal:Goal) "
            "RETURN member.id AS member_node_id, goal.id AS node_id, "
            "properties(goal) AS properties "
            "ORDER BY goal.priority, goal.id",
            member_id=member_id,
        )
        member_node_id: str | None = None
        goals: list[GoalData] = []
        goal_node_ids: list[str] = []
        for record in records:
            member_node_id = _optional_record_string(record, "member_node_id")
            node_id = _optional_record_string(record, "node_id")
            if node_id is None:
                continue
            goals.append(_goal_data(node_id, _record_properties(record)))
            goal_node_ids.append(node_id)
    return MemberGoalsResult(
        goals=tuple(goals),
        node_ids=_node_ids(member_node_id, goal_node_ids),
    )


@tool
def get_member_injuries(member_id: str) -> MemberInjuriesResult:
    """Read `Member -[:has]-> MemberInjury -[:exactMatch]-> ClinicalFinding`, newest first."""
    with neo4j_session() as session:
        records = session.run(
            "MATCH (member:Member {id: $member_id}) "
            "OPTIONAL MATCH (member)-[:has]->(injury:MemberInjury) "
            "OPTIONAL MATCH (injury)-[:exactMatch]->(finding:ClinicalFinding) "
            "RETURN member.id AS member_node_id, injury.id AS node_id, "
            "properties(injury) AS properties, "
            "[node IN collect(DISTINCT finding) WHERE node IS NOT NULL | node.id] "
            "AS clinical_finding_ids, injury.since AS sort_since "
            "ORDER BY sort_since DESC, node_id",
            member_id=member_id,
        )
        member_node_id: str | None = None
        injuries: list[MemberInjuryData] = []
        injury_node_ids: list[str] = []
        finding_node_ids: list[str] = []
        for record in records:
            member_node_id = _optional_record_string(record, "member_node_id")
            node_id = _optional_record_string(record, "node_id")
            if node_id is None:
                continue
            clinical_finding_ids = tuple(
                sorted(_record_strings(record, "clinical_finding_ids"))
            )
            injuries.append(
                _member_injury_data(
                    node_id,
                    _record_properties(record),
                    clinical_finding_ids,
                )
            )
            injury_node_ids.append(node_id)
            finding_node_ids.extend(clinical_finding_ids)
    return MemberInjuriesResult(
        injuries=tuple(injuries),
        node_ids=_node_ids(
            member_node_id,
            injury_node_ids,
            finding_node_ids,
        ),
    )


@tool
def get_morning_brief(member_id: str) -> MorningBriefResult:
    """Read the morning brief through `CoachTask -[:addresses]->` and `Barrier -[:evidencedBy]->`."""
    with neo4j_session() as session:
        record = session.run(
            "MATCH (member:Member {id: $member_id}) "
            "OPTIONAL MATCH (task:CoachTask {member_id: $member_id}) "
            "OPTIONAL MATCH (task)-[:addresses]->(addressed) "
            "WITH member, collect(DISTINCT {node_id: task.id, "
            "properties: properties(task), addressed_node_id: addressed.id}) "
            "AS task_rows "
            "OPTIONAL MATCH (barrier:Barrier {member_id: $member_id}) "
            "OPTIONAL MATCH (barrier)-[:evidencedBy]->(evidence) "
            "RETURN member.id AS member_node_id, properties(member) AS properties, "
            "task_rows, collect(DISTINCT {node_id: barrier.id, "
            "properties: properties(barrier), evidence_node_id: evidence.id}) "
            "AS barrier_rows",
            member_id=member_id,
        ).single()
    if record is None:
        return MorningBriefResult(morning_brief=None, node_ids=())

    member_node_id = _record_string(record, "member_node_id")
    properties = _record_properties(record)
    coach_tasks = _coach_tasks(_record_mappings(record, "task_rows"))
    barriers = _barriers(_record_mappings(record, "barrier_rows"))
    return MorningBriefResult(
        morning_brief=MorningBriefData(
            generated_for=_string(properties, "brief_generated_for"),
            churn_risk_level=_string(properties, "churn_risk_level"),
            churn_risk_reasons=_strings(properties, "churn_risk_reasons"),
            barriers=barriers,
            coach_tasks=coach_tasks,
        ),
        node_ids=_node_ids(
            member_node_id,
            (task.node_id for task in coach_tasks),
            (
                addressed_node_id
                for task in coach_tasks
                for addressed_node_id in task.addressed_node_ids
            ),
            (barrier.node_id for barrier in barriers),
            (
                evidence_node_id
                for barrier in barriers
                for evidence_node_id in barrier.evidence_node_ids
            ),
        ),
    )


@tool
def get_member_profile(member_id: str) -> MemberProfileResult:
    """Read `Member -[:owns]-> Equipment` and `Member -[:dislikes]-> Exercise` with the Member profile."""
    with neo4j_session() as session:
        record = session.run(
            "MATCH (member:Member {id: $member_id}) "
            "OPTIONAL MATCH (member)-[:owns]->(equipment:Equipment) "
            "WITH member, collect(DISTINCT equipment.id) AS equipment_node_ids "
            "OPTIONAL MATCH (member)-[:dislikes]->(exercise:Exercise) "
            "RETURN member.id AS member_node_id, properties(member) AS properties, "
            "equipment_node_ids, collect(DISTINCT exercise.id) AS exercise_node_ids",
            member_id=member_id,
        ).single()
    if record is None:
        return MemberProfileResult(profile=None, node_ids=())

    member_node_id = _record_string(record, "member_node_id")
    properties = _record_properties(record)
    equipment_node_ids = sorted(_record_strings(record, "equipment_node_ids"))
    exercise_node_ids = sorted(_record_strings(record, "exercise_node_ids"))
    return MemberProfileResult(
        profile=_member_profile_data(member_node_id, properties),
        node_ids=_node_ids(
            member_node_id,
            equipment_node_ids,
            exercise_node_ids,
        ),
    )


RETRIEVAL_TOOLS: tuple[BaseTool, ...] = (
    get_observations,
    get_workout_sessions,
    get_chat_messages,
    get_member_goals,
    get_member_injuries,
    get_morning_brief,
    get_member_profile,
)


def _observation_data(
    node_id: str, properties: dict[str, Any], *, as_of: date
) -> ObservationData:
    kind = as_observation_kind(_string(properties, "kind"))
    observed_at = _string(properties, "observed_at")
    freshness = observation_freshness(kind, observed_at, as_of=as_of)
    excluded = {
        "id",
        "member_id",
        "kind",
        "observed_at",
        "value",
        "unit",
        "source",
        "version",
        "ingested_at",
    }
    measurements = tuple(
        ObservationMeasurement(name=key, value=_observation_scalar(item, key))
        for key, item in sorted(properties.items())
        if key not in excluded
    )
    return ObservationData(
        node_id=node_id,
        kind=kind,
        observed_at=observed_at,
        age_days=freshness.age_days,
        stale=freshness.stale,
        value=_optional_number(properties, "value"),
        unit=_optional_string(properties, "unit"),
        measurements=measurements,
    )


def _workout_session_data(
    node_id: str,
    properties: dict[str, Any],
    exercise_ids: tuple[str, ...],
) -> WorkoutSessionData:
    return WorkoutSessionData(
        node_id=node_id,
        date=_string(properties, "date"),
        title=_string(properties, "title"),
        planned=_bool(properties, "planned"),
        completed=_bool(properties, "completed"),
        duration_min=_int(properties, "duration_min"),
        rpe=_optional_number(properties, "rpe"),
        exercise_mentions=_strings(properties, "exercise_mentions"),
        exercise_ids=exercise_ids,
    )


def _chat_message_data(node_id: str, properties: dict[str, Any]) -> ChatMessageData:
    sender = _string(properties, "sender")
    if sender not in ("member", "coach"):
        raise ValueError(f"ChatMessage {node_id} has unsupported sender {sender}")
    return ChatMessageData(
        node_id=node_id,
        timestamp=_string(properties, "timestamp"),
        sender=sender,
        text=_string(properties, "text"),
        attachments_json=_optional_string(properties, "attachments_json"),
    )


def _goal_data(node_id: str, properties: dict[str, Any]) -> GoalData:
    return GoalData(
        node_id=node_id,
        external_id=_string(properties, "external_id"),
        text=_string(properties, "text"),
        priority=_int(properties, "priority"),
        target_date=_optional_string(properties, "target_date"),
    )


def _member_injury_data(
    node_id: str,
    properties: dict[str, Any],
    clinical_finding_ids: tuple[str, ...],
) -> MemberInjuryData:
    return MemberInjuryData(
        node_id=node_id,
        external_id=_string(properties, "external_id"),
        region=_string(properties, "region"),
        joint=_string(properties, "joint"),
        status=_string(properties, "status"),
        severity=_string(properties, "severity"),
        since=_string(properties, "since"),
        notes=_string(properties, "notes"),
        snomedct_hint=_optional_string(properties, "snomedct_hint"),
        clinical_finding_mentions=_strings(properties, "clinical_finding_mentions"),
        clinical_finding_ids=clinical_finding_ids,
    )


def _member_profile_data(node_id: str, properties: dict[str, Any]) -> MemberProfileData:
    return MemberProfileData(
        node_id=node_id,
        name=_string(properties, "name"),
        age=_int(properties, "age"),
        sex=_string(properties, "sex"),
        height_cm=_number(properties, "height_cm"),
        weight_kg=_number(properties, "weight_kg"),
        timezone=_string(properties, "timezone"),
        member_since=_string(properties, "member_since"),
        coach_id=_string(properties, "coach_id"),
        tier=_string(properties, "tier"),
        preferred_session_minutes=_int(properties, "preferred_session_minutes"),
        training_days_per_week=_int(properties, "training_days_per_week"),
        preferred_days=_strings(properties, "preferred_days"),
        preference_notes=_string(properties, "preference_notes"),
        equipment_available=_strings(properties, "equipment_available"),
        dislikes=_strings(properties, "dislikes"),
    )


def _coach_tasks(rows: list[Mapping[str, Any]]) -> tuple[CoachTaskData, ...]:
    task_rows: dict[str, tuple[dict[str, Any], set[str]]] = {}
    for row in rows:
        node_id = _optional_mapping_string(row, "node_id")
        if node_id is None:
            continue
        properties = _mapping_properties(row)
        addressed_node_id = _optional_mapping_string(row, "addressed_node_id")
        if node_id not in task_rows:
            task_rows[node_id] = (properties, set())
        if addressed_node_id is not None:
            task_rows[node_id][1].add(addressed_node_id)
    return tuple(
        CoachTaskData(
            node_id=node_id,
            generated_for=_string(properties, "generated_for"),
            type=_string(properties, "type"),
            text=_string(properties, "text"),
            status=_string(properties, "status"),
            addressed_node_ids=tuple(sorted(addressed_node_ids)),
        )
        for node_id, (properties, addressed_node_ids) in sorted(
            sorted(task_rows.items()),
            key=lambda item: _string(item[1][0], "generated_for"),
            reverse=True,
        )
    )


def _barriers(rows: list[Mapping[str, Any]]) -> tuple[BarrierData, ...]:
    barrier_rows: dict[str, tuple[dict[str, Any], set[str]]] = {}
    for row in rows:
        node_id = _optional_mapping_string(row, "node_id")
        if node_id is None:
            continue
        properties = _mapping_properties(row)
        evidence_node_id = _optional_mapping_string(row, "evidence_node_id")
        if node_id not in barrier_rows:
            barrier_rows[node_id] = (properties, set())
        if evidence_node_id is not None:
            barrier_rows[node_id][1].add(evidence_node_id)
    return tuple(
        BarrierData(
            node_id=node_id,
            kind=_string(properties, "kind"),
            copper_id=_string(properties, "copper_id"),
            reason=_string(properties, "reason"),
            risk_level=_string(properties, "risk_level"),
            evidence_node_ids=tuple(sorted(evidence_node_ids)),
        )
        for node_id, (properties, evidence_node_ids) in sorted(barrier_rows.items())
    )


def _node_ids(
    member_node_id: str | None,
    *node_id_groups: Iterable[str],
) -> tuple[str, ...]:
    node_ids: list[str] = []
    seen: set[str] = set()
    for node_id in () if member_node_id is None else (member_node_id,):
        seen.add(node_id)
        node_ids.append(node_id)
    for group in node_id_groups:
        for node_id in group:
            if node_id in seen:
                continue
            seen.add(node_id)
            node_ids.append(node_id)
    return tuple(node_ids)


def _record_properties(record: Record) -> dict[str, Any]:
    properties = record["properties"]
    if not isinstance(properties, Mapping):
        raise TypeError("Expected properties to be a mapping")
    return dict(properties)


def _record_string(record: Record, key: str) -> str:
    value = record[key]
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be a string")
    return value


def _optional_record_string(record: Record, key: str) -> str | None:
    value = record[key]
    if value is not None and not isinstance(value, str):
        raise TypeError(f"Expected {key} to be a string or null")
    return value


def _record_strings(record: Record, key: str) -> tuple[str, ...]:
    value = record[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"Expected {key} to be a list of strings")
    return tuple(value)


def _record_mappings(record: Record, key: str) -> list[Mapping[str, Any]]:
    value = record[key]
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise TypeError(f"Expected {key} to be a list of mappings")
    return value


def _mapping_properties(value: Mapping[str, Any]) -> dict[str, Any]:
    properties = value.get("properties")
    if not isinstance(properties, Mapping):
        raise TypeError("Expected properties to be a mapping")
    return dict(properties)


def _optional_mapping_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise TypeError(f"Expected {key} to be a string or null")
    return item


def _string(properties: Mapping[str, Any], key: str) -> str:
    value = properties.get(key)
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be a string")
    return value


def _optional_string(properties: Mapping[str, Any], key: str) -> str | None:
    value = properties.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError(f"Expected {key} to be a string or null")
    return value


def _strings(properties: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = properties.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"Expected {key} to be a list of strings")
    return tuple(value)


def _bool(properties: Mapping[str, Any], key: str) -> bool:
    value = properties.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Expected {key} to be a boolean")
    return value


def _int(properties: Mapping[str, Any], key: str) -> int:
    value = properties.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected {key} to be an integer")
    return value


def _number(properties: Mapping[str, Any], key: str) -> int | float:
    value = properties.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"Expected {key} to be a number")
    return value


def _optional_number(properties: Mapping[str, Any], key: str) -> int | float | None:
    value = properties.get(key)
    if value is not None and (
        not isinstance(value, int | float) or isinstance(value, bool)
    ):
        raise TypeError(f"Expected {key} to be a number or null")
    return value


def _observation_scalar(value: Any, name: str) -> ObservationScalar:
    if not isinstance(value, str | int | float | bool):
        raise TypeError(f"Expected Observation measurement {name} to be a scalar")
    return value
