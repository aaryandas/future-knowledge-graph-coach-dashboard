from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from neo4j import ManagedTransaction, Record

from app.graph.member_context import MorningBrief, _read_morning_brief
from app.graph.store import neo4j_session

COACH_ACTION_SOURCE = "coach-action"

type CoachTaskStatus = Literal["open", "completed", "dismissed"]
type CoachActionWriteStatus = Literal["confirmed", "target-not-found"]
type SessionPlanSection = Literal["warm-up", "main", "cool-down"]


@dataclass(frozen=True)
class SessionPlanRow:
    row_id: str
    exercise_id: str
    section: SessionPlanSection | None
    sets: int | None
    reps: int | None
    hold_minutes: float | None
    rest_minutes: float | None
    per_side: bool | None
    supports_weight: bool | None
    minutes: float | None

    def __post_init__(self) -> None:
        _require_text(self.row_id, "session plan row id")
        _require_text(self.exercise_id, "Exercise id")
        _require_positive_int(self.sets, "session plan sets")
        _require_positive_int(self.reps, "session plan reps")
        _require_non_negative_number(self.hold_minutes, "session plan hold minutes")
        _require_non_negative_number(self.rest_minutes, "session plan rest minutes")
        _require_non_negative_number(self.minutes, "session plan minutes")


@dataclass(frozen=True)
class SessionPlan:
    session_id: str
    rows: tuple[SessionPlanRow, ...]
    source: str
    actor: str | None
    timestamp: str | None


@dataclass(frozen=True)
class SendMemberMessageWrite:
    message: str
    coach_task_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.message, "member message")
        if self.coach_task_id is not None:
            _require_text(self.coach_task_id, "CoachTask id")


@dataclass(frozen=True)
class UpdateBriefTaskWrite:
    coach_task_id: str
    status: CoachTaskStatus
    text: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.coach_task_id, "CoachTask id")
        if self.text is not None:
            _require_text(self.text, "CoachTask text")


@dataclass(frozen=True)
class WriteSessionPlanWrite:
    session_id: str
    rows: tuple[SessionPlanRow, ...]

    def __post_init__(self) -> None:
        _require_text(self.session_id, "WorkoutSession id")
        row_ids = tuple(row.row_id for row in self.rows)
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("A session plan cannot contain duplicate row ids.")


type CoachActionWrite = (
    SendMemberMessageWrite | UpdateBriefTaskWrite | WriteSessionPlanWrite
)


@dataclass(frozen=True)
class CoachActionWriteResult:
    status: CoachActionWriteStatus
    source: Literal["coach-action"]
    actor: str | None
    timestamp: str
    morning_brief: MorningBrief | None


def get_session_plan(member_id: str, session_id: str) -> SessionPlan | None:
    """Read one stored WorkoutSession and its ordered included rows."""
    _require_text(member_id, "Member id")
    _require_text(session_id, "WorkoutSession id")
    with neo4j_session() as session:
        records = tuple(
            session.run(
                """
                MATCH (:Member {id: $member_id})-[:performed]->
                      (workout:WorkoutSession {id: $session_id})
                OPTIONAL MATCH (workout)-[edge:included]->(exercise:Exercise)
                RETURN properties(workout) AS workout_properties,
                       edge.id AS row_id,
                       exercise.id AS exercise_id,
                       properties(edge) AS row_properties
                ORDER BY coalesce(edge.position, 2147483647), edge.id
                """,
                member_id=member_id,
                session_id=session_id,
            )
        )
    if not records:
        return None
    workout_properties = _property_map(records[0], "workout_properties")
    return SessionPlan(
        session_id=session_id,
        rows=tuple(
            _session_plan_row(record)
            for record in records
            if isinstance(record["row_id"], str)
            and isinstance(record["exercise_id"], str)
        ),
        source=_string_property(workout_properties, "source"),
        actor=_optional_string_property(workout_properties, "actor"),
        timestamp=_optional_string_property(workout_properties, "timestamp"),
    )


def confirm_coach_action(
    member_id: str,
    action_id: str,
    action: CoachActionWrite,
    *,
    timestamp: datetime | None = None,
) -> CoachActionWriteResult:
    """Apply one coach-confirmed KG2 mutation in one transaction."""
    _require_text(member_id, "Member id")
    _require_text(action_id, "coach action id")
    action_timestamp = timestamp or datetime.now(UTC)
    if action_timestamp.utcoffset() is None:
        raise ValueError("A coach action timestamp must include a UTC offset.")
    acted_at = action_timestamp.isoformat()
    with neo4j_session() as session:
        actor = session.execute_write(
            _write_coach_action,
            member_id,
            action_id,
            action,
            acted_at,
        )
        morning_brief = (
            _read_morning_brief(session, member_id)
            if actor is not None and isinstance(action, UpdateBriefTaskWrite)
            else None
        )
    return CoachActionWriteResult(
        status="confirmed" if actor is not None else "target-not-found",
        source=COACH_ACTION_SOURCE,
        actor=actor,
        timestamp=acted_at,
        morning_brief=morning_brief,
    )


def _write_coach_action(
    transaction: ManagedTransaction,
    member_id: str,
    action_id: str,
    action: CoachActionWrite,
    timestamp: str,
) -> str | None:
    if isinstance(action, SendMemberMessageWrite):
        return _send_member_message(
            transaction,
            member_id,
            action_id,
            action,
            timestamp,
        )
    if isinstance(action, UpdateBriefTaskWrite):
        return _update_brief_task(
            transaction,
            member_id,
            action_id,
            action,
            timestamp,
        )
    return _write_session_plan(
        transaction,
        member_id,
        action_id,
        action,
        timestamp,
    )


def _send_member_message(
    transaction: ManagedTransaction,
    member_id: str,
    action_id: str,
    action: SendMemberMessageWrite,
    timestamp: str,
) -> str | None:
    message_id = f"{member_id}:chat:coach-action:{action_id}"
    edge_id = f"{member_id}:received:{message_id}"
    record = transaction.run(
        """
        MATCH (member:Member {id: $member_id})
        OPTIONAL MATCH (task:CoachTask {id: $coach_task_id, member_id: $member_id})
        WITH member, task
        WHERE $coach_task_id IS NULL OR task IS NOT NULL
        MERGE (message:ChatMessage {id: $message_id})
        SET message.member_id = $member_id,
            message.timestamp = $timestamp,
            message.sender = 'coach',
            message.text = $message,
            message.coach_task_id = $coach_task_id,
            message.action_id = $action_id,
            message.source = $source,
            message.actor = member.coach_id
        MERGE (member)-[edge:received {id: $edge_id}]->(message)
        SET edge.source = $source,
            edge.actor = member.coach_id,
            edge.timestamp = $timestamp,
            edge.action_id = $action_id
        RETURN member.coach_id AS actor
        """,
        member_id=member_id,
        coach_task_id=action.coach_task_id,
        message_id=message_id,
        edge_id=edge_id,
        message=action.message,
        action_id=action_id,
        source=COACH_ACTION_SOURCE,
        timestamp=timestamp,
    ).single()
    return None if record is None else cast(str, record["actor"])


def _update_brief_task(
    transaction: ManagedTransaction,
    member_id: str,
    action_id: str,
    action: UpdateBriefTaskWrite,
    timestamp: str,
) -> str | None:
    record = transaction.run(
        """
        MATCH (member:Member {id: $member_id})
        MATCH (task:CoachTask {id: $coach_task_id, member_id: $member_id})
        SET task.status = $status,
            task.text = coalesce($text, task.text),
            task.action_id = $action_id,
            task.source = $source,
            task.actor = member.coach_id,
            task.timestamp = $timestamp
        RETURN member.coach_id AS actor
        """,
        member_id=member_id,
        coach_task_id=action.coach_task_id,
        status=action.status,
        text=action.text,
        action_id=action_id,
        source=COACH_ACTION_SOURCE,
        timestamp=timestamp,
    ).single()
    return None if record is None else cast(str, record["actor"])


def _write_session_plan(
    transaction: ManagedTransaction,
    member_id: str,
    action_id: str,
    action: WriteSessionPlanWrite,
    timestamp: str,
) -> str | None:
    rows = [
        {**row.__dict__, "position": position}
        for position, row in enumerate(action.rows)
    ]
    record = transaction.run(
        """
        MATCH (member:Member {id: $member_id})-[:performed]->
              (workout:WorkoutSession {id: $session_id})
        CALL {
            WITH $rows AS rows
            UNWIND rows AS row
            MATCH (exercise:Exercise {id: row.exercise_id})
            RETURN collect({row: row, exercise: exercise}) AS entries
        }
        WITH member, workout, entries
        WHERE size(entries) = size($rows)
        OPTIONAL MATCH (workout)-[existing:included]->(:Exercise)
        WITH member, workout, entries, collect(existing) AS existing_edges
        FOREACH (edge IN existing_edges | DELETE edge)
        SET workout.exercise_mentions = [entry IN entries | entry.exercise.name],
            workout.action_id = $action_id,
            workout.source = $source,
            workout.actor = member.coach_id,
            workout.timestamp = $timestamp
        WITH member, workout, entries
        CALL {
            WITH workout, entries, member
            UNWIND entries AS entry
            WITH workout, member, entry.row AS row, entry.exercise AS exercise
            CREATE (workout)-[edge:included {id: row.row_id}]->(exercise)
            SET edge.position = row.position,
                edge.section = row.section,
                edge.sets = row.sets,
                edge.reps = row.reps,
                edge.hold_minutes = row.hold_minutes,
                edge.rest_minutes = row.rest_minutes,
                edge.per_side = row.per_side,
                edge.supports_weight = row.supports_weight,
                edge.minutes = row.minutes,
                edge.action_id = $action_id,
                edge.source = $source,
                edge.actor = member.coach_id,
                edge.timestamp = $timestamp
            RETURN count(*) AS written_rows
        }
        RETURN member.coach_id AS actor
        """,
        member_id=member_id,
        session_id=action.session_id,
        rows=rows,
        action_id=action_id,
        source=COACH_ACTION_SOURCE,
        timestamp=timestamp,
    ).single()
    return None if record is None else cast(str, record["actor"])


def _session_plan_row(record: Record) -> SessionPlanRow:
    properties = _property_map(record, "row_properties")
    return SessionPlanRow(
        row_id=cast(str, record["row_id"]),
        exercise_id=cast(str, record["exercise_id"]),
        section=_optional_section(properties.get("section")),
        sets=_optional_int(properties.get("sets")),
        reps=_optional_int(properties.get("reps")),
        hold_minutes=_optional_number(properties.get("hold_minutes")),
        rest_minutes=_optional_number(properties.get("rest_minutes")),
        per_side=_optional_bool(properties.get("per_side")),
        supports_weight=_optional_bool(properties.get("supports_weight")),
        minutes=_optional_number(properties.get("minutes")),
    )


def _property_map(record: Record, key: str) -> dict[str, Any]:
    value = record[key]
    if not isinstance(value, dict):
        raise TypeError(f"Graph property map {key} must be a dictionary.")
    return cast("dict[str, Any]", value)


def _string_property(properties: dict[str, Any], key: str) -> str:
    value = properties.get(key)
    if not isinstance(value, str):
        raise TypeError(f"Graph property {key} must be a string.")
    return value


def _optional_string_property(properties: dict[str, Any], key: str) -> str | None:
    value = properties.get(key)
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"Graph property {key} must be a string or null.")


def _optional_section(value: object) -> SessionPlanSection | None:
    if value is None:
        return None
    if value not in ("warm-up", "main", "cool-down"):
        raise TypeError("Graph property section must be a session plan section.")
    return cast("SessionPlanSection", value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("A stored session plan integer must be an integer or null.")
    return value


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError("A stored session plan number must be numeric or null.")
    return float(value)


def _optional_bool(value: object) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise TypeError("A stored session plan boolean must be a boolean or null.")


def _require_text(value: str, description: str) -> None:
    if not value.strip():
        raise ValueError(f"A {description} cannot be empty.")


def _require_positive_int(value: int | None, description: str) -> None:
    if value is not None and (isinstance(value, bool) or value <= 0):
        raise ValueError(f"{description.capitalize()} must be a positive integer.")


def _require_non_negative_number(
    value: float | None,
    description: str,
) -> None:
    if value is not None and (isinstance(value, bool) or value < 0):
        raise ValueError(f"{description.capitalize()} cannot be negative.")
