from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from neo4j import ManagedTransaction

from app.graph.member_context import MorningBrief, _read_morning_brief
from app.graph.store import neo4j_session

COACH_ACTION_SOURCE = "coach-action"

type CoachTaskStatus = Literal["open", "completed", "dismissed"]
type CoachActionWriteStatus = Literal["confirmed", "target-not-found"]


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


type CoachActionWrite = SendMemberMessageWrite | UpdateBriefTaskWrite


@dataclass(frozen=True)
class CoachActionWriteResult:
    status: CoachActionWriteStatus
    source: Literal["coach-action"]
    actor: str | None
    timestamp: str
    morning_brief: MorningBrief | None


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
    return _update_brief_task(
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


def _require_text(value: str, description: str) -> None:
    if not value.strip():
        raise ValueError(f"A {description} cannot be empty.")
