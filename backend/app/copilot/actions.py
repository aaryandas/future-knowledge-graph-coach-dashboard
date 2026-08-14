from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from langchain_core.tools import BaseTool, tool

from app.graph import (
    CoachActionWriteResult,
    SendMemberMessageWrite,
    UpdateBriefTaskWrite,
    confirm_coach_action,
)

type CoachActionKind = Literal["send-member-message", "update-brief-task"]
type CoachActionStatus = Literal["pending", "confirmed", "discarded", "failed"]
type CoachTaskStatus = Literal["open", "completed", "dismissed"]
type CoachActionDecisionKind = Literal["confirm", "discard"]


@dataclass(frozen=True)
class SendMemberMessage:
    action_id: str
    kind: Literal["send-member-message"]
    message: str
    coach_task_id: str | None = None


@dataclass(frozen=True)
class UpdateBriefTask:
    action_id: str
    kind: Literal["update-brief-task"]
    coach_task_id: str
    status: CoachTaskStatus
    text: str | None = None


type CoachAction = SendMemberMessage | UpdateBriefTask


@dataclass(frozen=True)
class CoachActionDecision:
    decision: CoachActionDecisionKind
    action: CoachAction


class CoachActionWriter(Protocol):
    def __call__(
        self,
        member_id: str,
        action: CoachAction,
    ) -> CoachActionWriteResult: ...


@tool
def send_member_message(message: str, coach_task_id: str | None = None) -> str:
    """Propose a coach message to the member; the coach must confirm before it is sent."""
    return message


@tool
def update_brief_task(
    coach_task_id: str,
    status: CoachTaskStatus,
    text: str | None = None,
) -> str:
    """Propose an exact CoachTask update; the coach must confirm before it is written."""
    return f"{coach_task_id}: {status}: {text or ''}"


COACH_ACTION_TOOLS: tuple[BaseTool, ...] = (
    send_member_message,
    update_brief_task,
)
COACH_ACTION_TOOL_NAMES = frozenset(tool.name for tool in COACH_ACTION_TOOLS)


def coach_action_from_tool_call(
    action_id: str,
    name: str,
    arguments: object,
) -> CoachAction | None:
    if not action_id or not isinstance(arguments, dict):
        return None
    if name == send_member_message.name:
        message = _required_text(arguments.get("message"))
        coach_task_id = _optional_text(arguments.get("coach_task_id"))
        if message is None or coach_task_id is _INVALID:
            return None
        return SendMemberMessage(
            action_id=action_id,
            kind="send-member-message",
            message=message,
            coach_task_id=cast("str | None", coach_task_id),
        )
    if name == update_brief_task.name:
        coach_task_id = _required_text(arguments.get("coach_task_id"))
        status = arguments.get("status")
        text = _optional_text(arguments.get("text"))
        if (
            coach_task_id is None
            or status not in ("open", "completed", "dismissed")
            or text is _INVALID
        ):
            return None
        return UpdateBriefTask(
            action_id=action_id,
            kind="update-brief-task",
            coach_task_id=coach_task_id,
            status=status,
            text=cast("str | None", text),
        )
    return None


def coach_action_decision(
    pending_action: CoachAction,
    value: object,
) -> CoachActionDecision | None:
    if (
        not isinstance(value, dict)
        or value.get("action_id") != pending_action.action_id
    ):
        return None
    decision = value.get("decision")
    if decision == "discard":
        return CoachActionDecision(decision="discard", action=pending_action)
    if decision != "confirm":
        return None
    raw_action = value.get("action")
    if raw_action is None:
        return CoachActionDecision(decision="confirm", action=pending_action)
    edited_action = _edited_action(pending_action, raw_action)
    if edited_action is None:
        return None
    return CoachActionDecision(decision="confirm", action=edited_action)


def coach_action_from_payload(value: object) -> CoachAction | None:
    if not isinstance(value, dict):
        return None
    action_id = value.get("action_id")
    raw_action = value.get("action")
    if not isinstance(action_id, str) or not isinstance(raw_action, dict):
        return None
    return coach_action_from_tool_call(
        action_id,
        _tool_name(raw_action.get("kind")),
        raw_action,
    )


def coach_action_payload(
    action: CoachAction,
    status: CoachActionStatus,
) -> dict[str, Any]:
    if isinstance(action, SendMemberMessage):
        exact_action: dict[str, Any] = {
            "kind": action.kind,
            "message": action.message,
            "coach_task_id": action.coach_task_id,
        }
    else:
        exact_action = {
            "kind": action.kind,
            "coach_task_id": action.coach_task_id,
            "status": action.status,
            "text": action.text,
        }
    return {
        "action_id": action.action_id,
        "status": status,
        "action": exact_action,
    }


def write_coach_action(
    member_id: str,
    action: CoachAction,
) -> CoachActionWriteResult:
    graph_action = (
        SendMemberMessageWrite(
            message=action.message,
            coach_task_id=action.coach_task_id,
        )
        if isinstance(action, SendMemberMessage)
        else UpdateBriefTaskWrite(
            coach_task_id=action.coach_task_id,
            status=action.status,
            text=action.text,
        )
    )
    return confirm_coach_action(member_id, action.action_id, graph_action)


def _edited_action(
    pending_action: CoachAction,
    raw_action: object,
) -> CoachAction | None:
    if not isinstance(raw_action, dict):
        return None
    edited_action = coach_action_from_tool_call(
        pending_action.action_id,
        _tool_name(raw_action.get("kind")),
        raw_action,
    )
    if (
        isinstance(pending_action, SendMemberMessage)
        and isinstance(edited_action, SendMemberMessage)
        and edited_action.coach_task_id == pending_action.coach_task_id
    ):
        return edited_action
    if (
        isinstance(pending_action, UpdateBriefTask)
        and isinstance(edited_action, UpdateBriefTask)
        and edited_action.coach_task_id == pending_action.coach_task_id
    ):
        return edited_action
    return None


def _tool_name(kind: object) -> str:
    if kind == "send-member-message":
        return send_member_message.name
    if kind == "update-brief-task":
        return update_brief_task.name
    return ""


class _Invalid:
    pass


_INVALID = _Invalid()


def _required_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _optional_text(value: object) -> str | None | _Invalid:
    if value is None:
        return None
    return _required_text(value) or _INVALID
