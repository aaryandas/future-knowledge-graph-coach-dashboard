from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from neo4j import Record, Session

from app.graph.store import neo4j_session

type ObservationScalar = str | int | float | bool


@dataclass(frozen=True)
class MemberProfile:
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
class GoalView:
    node_id: str
    external_id: str
    text: str
    priority: int
    target_date: str | None


@dataclass(frozen=True)
class MemberInjuryView:
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
class WorkoutSessionView:
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
class ObservationValue:
    name: str
    value: ObservationScalar


@dataclass(frozen=True)
class ObservationView:
    node_id: str
    kind: str
    observed_at: str
    value: int | float | None
    unit: str | None
    measurements: tuple[ObservationValue, ...]


@dataclass(frozen=True)
class ChatMessageView:
    node_id: str
    timestamp: str
    sender: str
    text: str
    attachments_json: str | None


@dataclass(frozen=True)
class BarrierView:
    node_id: str
    kind: str
    copper_id: str
    reason: str
    risk_level: str
    evidence_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class CoachTaskView:
    node_id: str
    generated_for: str
    type: str
    text: str
    status: str
    addressed_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MorningBrief:
    generated_for: str
    churn_risk_level: str
    churn_risk_reasons: tuple[str, ...]
    barriers: tuple[BarrierView, ...]
    coach_tasks: tuple[CoachTaskView, ...]


@dataclass(frozen=True)
class MemberContext:
    profile: MemberProfile
    goals: tuple[GoalView, ...]
    injuries: tuple[MemberInjuryView, ...]
    workout_sessions: tuple[WorkoutSessionView, ...]
    observations: tuple[ObservationView, ...]
    chat_messages: tuple[ChatMessageView, ...]
    morning_brief: MorningBrief


def get_member_context(member_id: str) -> MemberContext | None:
    with neo4j_session() as session:
        profile = _read_member_profile(session, member_id)
        if profile is None:
            return None
        morning_brief = _read_morning_brief(session, member_id)
        if morning_brief is None:
            raise RuntimeError(f"Member {member_id} has no morning brief")
        return MemberContext(
            profile=profile,
            goals=_read_member_goals(session, member_id),
            injuries=_read_member_injuries(session, member_id),
            workout_sessions=_read_workout_sessions(session, member_id),
            observations=_read_observations(session, member_id),
            chat_messages=_read_chat_messages(session, member_id),
            morning_brief=morning_brief,
        )


def get_member_profile(member_id: str) -> MemberProfile | None:
    with neo4j_session() as session:
        return _read_member_profile(session, member_id)


def get_member_goals(member_id: str) -> tuple[GoalView, ...]:
    with neo4j_session() as session:
        return _read_member_goals(session, member_id)


def get_member_injuries(member_id: str) -> tuple[MemberInjuryView, ...]:
    with neo4j_session() as session:
        return _read_member_injuries(session, member_id)


def get_workout_sessions(member_id: str) -> tuple[WorkoutSessionView, ...]:
    with neo4j_session() as session:
        return _read_workout_sessions(session, member_id)


def get_observations(member_id: str) -> tuple[ObservationView, ...]:
    with neo4j_session() as session:
        return _read_observations(session, member_id)


def get_chat_messages(member_id: str) -> tuple[ChatMessageView, ...]:
    with neo4j_session() as session:
        return _read_chat_messages(session, member_id)


def get_morning_brief(member_id: str) -> MorningBrief | None:
    with neo4j_session() as session:
        return _read_morning_brief(session, member_id)


def _read_member_profile(session: Session, member_id: str) -> MemberProfile | None:
    record = session.run(
        "MATCH (member:Member {id: $member_id}) "
        "RETURN member.id AS node_id, properties(member) AS properties",
        member_id=member_id,
    ).single()
    if record is None:
        return None
    properties = _properties(record)
    return MemberProfile(
        node_id=cast(str, record["node_id"]),
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


def _read_member_goals(session: Session, member_id: str) -> tuple[GoalView, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:pursues]->(goal:Goal) "
        "RETURN goal.id AS node_id, properties(goal) AS properties "
        "ORDER BY goal.priority, goal.id",
        member_id=member_id,
    )
    return tuple(_goal(record) for record in records)


def _read_member_injuries(
    session: Session, member_id: str
) -> tuple[MemberInjuryView, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:has]->(injury:MemberInjury) "
        "OPTIONAL MATCH (injury)-[:exactMatch]->(finding:ClinicalFinding) "
        "RETURN injury.id AS node_id, properties(injury) AS properties, "
        "[node IN collect(finding) WHERE node IS NOT NULL | node.id] "
        "AS clinical_finding_ids, injury.since AS sort_since "
        "ORDER BY sort_since DESC, node_id",
        member_id=member_id,
    )
    return tuple(_injury(record) for record in records)


def _read_workout_sessions(
    session: Session, member_id: str
) -> tuple[WorkoutSessionView, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:performed]->(workout:WorkoutSession) "
        "OPTIONAL MATCH (workout)-[edge]->(exercise:Exercise) "
        "WHERE type(edge) = 'included' "
        "RETURN workout.id AS node_id, properties(workout) AS properties, "
        "[node IN collect(exercise) WHERE node IS NOT NULL | node.id] "
        "AS exercise_ids, workout.date AS sort_date "
        "ORDER BY sort_date DESC, node_id",
        member_id=member_id,
    )
    return tuple(_workout_session(record) for record in records)


def _read_observations(session: Session, member_id: str) -> tuple[ObservationView, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:observed]->(observation:Observation) "
        "RETURN observation.id AS node_id, properties(observation) AS properties "
        "ORDER BY observation.observed_at DESC, observation.kind, observation.id",
        member_id=member_id,
    )
    return tuple(_observation(record) for record in records)


def _read_chat_messages(
    session: Session, member_id: str
) -> tuple[ChatMessageView, ...]:
    records = session.run(
        "MATCH (:Member {id: $member_id})-[:said|received]->(message:ChatMessage) "
        "RETURN message.id AS node_id, properties(message) AS properties "
        "ORDER BY message.timestamp DESC, message.id",
        member_id=member_id,
    )
    return tuple(_chat_message(record) for record in records)


def _read_morning_brief(session: Session, member_id: str) -> MorningBrief | None:
    member = session.run(
        "MATCH (member:Member {id: $member_id}) "
        "RETURN properties(member) AS properties",
        member_id=member_id,
    ).single()
    if member is None:
        return None
    properties = _properties(member)
    barrier_records = session.run(
        "MATCH (barrier:Barrier {member_id: $member_id}) "
        "OPTIONAL MATCH (barrier)-[:evidencedBy]->(evidence) "
        "RETURN barrier.id AS node_id, properties(barrier) AS properties, "
        "[node IN collect(evidence) WHERE node IS NOT NULL | node.id] "
        "AS evidence_node_ids "
        "ORDER BY node_id",
        member_id=member_id,
    )
    task_records = session.run(
        "MATCH (task:CoachTask {member_id: $member_id}) "
        "OPTIONAL MATCH (task)-[:addresses]->(addressed) "
        "RETURN task.id AS node_id, properties(task) AS properties, "
        "[node IN collect(addressed) WHERE node IS NOT NULL | node.id] "
        "AS addressed_node_ids, task.generated_for AS sort_generated_for "
        "ORDER BY sort_generated_for DESC, node_id",
        member_id=member_id,
    )
    return MorningBrief(
        generated_for=_string(properties, "brief_generated_for"),
        churn_risk_level=_string(properties, "churn_risk_level"),
        churn_risk_reasons=_strings(properties, "churn_risk_reasons"),
        barriers=tuple(_barrier(record) for record in barrier_records),
        coach_tasks=tuple(_coach_task(record) for record in task_records),
    )


def _goal(record: Record) -> GoalView:
    properties = _properties(record)
    return GoalView(
        node_id=cast(str, record["node_id"]),
        external_id=_string(properties, "external_id"),
        text=_string(properties, "text"),
        priority=_int(properties, "priority"),
        target_date=_optional_string(properties, "target_date"),
    )


def _injury(record: Record) -> MemberInjuryView:
    properties = _properties(record)
    return MemberInjuryView(
        node_id=cast(str, record["node_id"]),
        external_id=_string(properties, "external_id"),
        region=_string(properties, "region"),
        joint=_string(properties, "joint"),
        status=_string(properties, "status"),
        severity=_string(properties, "severity"),
        since=_string(properties, "since"),
        notes=_string(properties, "notes"),
        snomedct_hint=_optional_string(properties, "snomedct_hint"),
        clinical_finding_mentions=_strings(properties, "clinical_finding_mentions"),
        clinical_finding_ids=tuple(cast(list[str], record["clinical_finding_ids"])),
    )


def _workout_session(record: Record) -> WorkoutSessionView:
    properties = _properties(record)
    return WorkoutSessionView(
        node_id=cast(str, record["node_id"]),
        date=_string(properties, "date"),
        title=_string(properties, "title"),
        planned=_bool(properties, "planned"),
        completed=_bool(properties, "completed"),
        duration_min=_int(properties, "duration_min"),
        rpe=_optional_number(properties, "rpe"),
        exercise_mentions=_strings(properties, "exercise_mentions"),
        exercise_ids=tuple(cast(list[str], record["exercise_ids"])),
    )


def _observation(record: Record) -> ObservationView:
    properties = _properties(record)
    value = _optional_number(properties, "value")
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
        ObservationValue(name=key, value=cast(ObservationScalar, item))
        for key, item in sorted(properties.items())
        if key not in excluded
    )
    return ObservationView(
        node_id=cast(str, record["node_id"]),
        kind=_string(properties, "kind"),
        observed_at=_string(properties, "observed_at"),
        value=value,
        unit=_optional_string(properties, "unit"),
        measurements=measurements,
    )


def _chat_message(record: Record) -> ChatMessageView:
    properties = _properties(record)
    return ChatMessageView(
        node_id=cast(str, record["node_id"]),
        timestamp=_string(properties, "timestamp"),
        sender=_string(properties, "sender"),
        text=_string(properties, "text"),
        attachments_json=_optional_string(properties, "attachments_json"),
    )


def _barrier(record: Record) -> BarrierView:
    properties = _properties(record)
    return BarrierView(
        node_id=cast(str, record["node_id"]),
        kind=_string(properties, "kind"),
        copper_id=_string(properties, "copper_id"),
        reason=_string(properties, "reason"),
        risk_level=_string(properties, "risk_level"),
        evidence_node_ids=tuple(cast(list[str], record["evidence_node_ids"])),
    )


def _coach_task(record: Record) -> CoachTaskView:
    properties = _properties(record)
    return CoachTaskView(
        node_id=cast(str, record["node_id"]),
        generated_for=_string(properties, "generated_for"),
        type=_string(properties, "type"),
        text=_string(properties, "text"),
        status=_string(properties, "status"),
        addressed_node_ids=tuple(cast(list[str], record["addressed_node_ids"])),
    )


def _properties(record: Record) -> dict[str, Any]:
    return cast(dict[str, Any], record["properties"])


def _string(properties: dict[str, Any], key: str) -> str:
    value = properties.get(key)
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be a string")
    return value


def _optional_string(properties: dict[str, Any], key: str) -> str | None:
    value = properties.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError(f"Expected {key} to be a string or null")
    return value


def _strings(properties: dict[str, Any], key: str) -> tuple[str, ...]:
    value = properties.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"Expected {key} to be a list of strings")
    return tuple(value)


def _bool(properties: dict[str, Any], key: str) -> bool:
    value = properties.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Expected {key} to be a boolean")
    return value


def _int(properties: dict[str, Any], key: str) -> int:
    value = properties.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected {key} to be an integer")
    return value


def _number(properties: dict[str, Any], key: str) -> int | float:
    value = properties.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"Expected {key} to be a number")
    return value


def _optional_number(properties: dict[str, Any], key: str) -> int | float | None:
    value = properties.get(key)
    if value is not None and (
        not isinstance(value, int | float) or isinstance(value, bool)
    ):
        raise TypeError(f"Expected {key} to be a number or null")
    return value
