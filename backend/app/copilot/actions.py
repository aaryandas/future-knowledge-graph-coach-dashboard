from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol, cast

from langchain_core.tools import BaseTool, tool

from app.graph import (
    CoachActionWriteResult,
    GraphEdgeKind,
    GraphNodeKind,
    SendMemberMessageWrite,
    SessionPlan,
    SessionPlanRow,
    UpdateBriefTaskWrite,
    WriteSessionPlanWrite,
    confirm_coach_action,
    get_session_plan,
)
from app.safety import (
    Verdict,
    VerdictTraceEvent,
    WalkedEdge,
    WalkedNode,
    WalkedPath,
    evaluate_safety,
)

type CoachActionKind = Literal[
    "send-member-message",
    "update-brief-task",
    "write-session-plan",
]
type CoachActionStatus = Literal[
    "pending",
    "confirmed",
    "discarded",
    "failed",
    "blocked",
]
type CoachTaskStatus = Literal["open", "completed", "dismissed"]
type CoachActionDecisionKind = Literal["confirm", "discard"]
type SessionPlanEditKind = Literal["add", "edit", "reorder", "remove"]
type SessionPlanEditFailureReason = Literal[
    "session-not-found",
    "row-not-found",
    "duplicate-row-id",
    "position-out-of-range",
]


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


@dataclass(frozen=True)
class AddSessionPlanRow:
    kind: Literal["add"]
    row: SessionPlanRow
    position: int


@dataclass(frozen=True)
class EditSessionPlanRow:
    kind: Literal["edit"]
    row: SessionPlanRow


@dataclass(frozen=True)
class ReorderSessionPlanRow:
    kind: Literal["reorder"]
    row_id: str
    position: int


@dataclass(frozen=True)
class RemoveSessionPlanRow:
    kind: Literal["remove"]
    row_id: str


type SessionPlanEdit = (
    AddSessionPlanRow
    | EditSessionPlanRow
    | ReorderSessionPlanRow
    | RemoveSessionPlanRow
)


@dataclass(frozen=True)
class SessionPlanWriteRequest:
    action_id: str
    kind: Literal["write-session-plan"]
    session_id: str
    edits: tuple[SessionPlanEdit, ...]


@dataclass(frozen=True)
class SessionPlanVerdict:
    exercise_id: str
    status: Literal["exclude", "caution", "clear"]
    trace: tuple[VerdictTraceEvent, ...]


@dataclass(frozen=True)
class SessionPlanEditFailure:
    reason: SessionPlanEditFailureReason
    edit_index: int | None
    row_id: str | None


@dataclass(frozen=True)
class WriteSessionPlan:
    action_id: str
    kind: Literal["write-session-plan"]
    session_id: str
    edits: tuple[SessionPlanEdit, ...]
    old_rows: tuple[SessionPlanRow, ...]
    new_rows: tuple[SessionPlanRow, ...]
    verdicts: tuple[SessionPlanVerdict, ...]
    failure: SessionPlanEditFailure | None = None


type CoachAction = SendMemberMessage | UpdateBriefTask | WriteSessionPlan
type CoachActionRequest = CoachAction | SessionPlanWriteRequest


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


class SessionPlanReader(Protocol):
    def __call__(self, member_id: str, session_id: str) -> SessionPlan | None: ...


class SessionPlanVerdictEvaluator(Protocol):
    def __call__(
        self,
        member_id: str,
        exercise_ids: tuple[str, ...],
    ) -> tuple[Verdict, ...]: ...


@dataclass(frozen=True)
class CoachActionProposal:
    action: CoachAction
    status: Literal["pending", "blocked", "failed"]


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


@tool
def write_session_plan(
    session_id: str,
    edits: list[SessionPlanEdit],
) -> str:
    """Propose typed row edits to a WorkoutSession; confirm before writing them."""
    return f"{session_id}: {len(edits)} edits"


COACH_ACTION_TOOLS: tuple[BaseTool, ...] = (
    send_member_message,
    update_brief_task,
    write_session_plan,
)
COACH_ACTION_TOOL_NAMES = frozenset(tool.name for tool in COACH_ACTION_TOOLS)


def coach_action_from_tool_call(
    action_id: str,
    name: str,
    arguments: object,
) -> CoachActionRequest | None:
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
    if name == write_session_plan.name:
        session_id = _required_text(arguments.get("session_id"))
        raw_edits = arguments.get("edits")
        if session_id is None or not isinstance(raw_edits, list) or not raw_edits:
            return None
        edits = tuple(_session_plan_edit(value) for value in raw_edits)
        if any(edit is None for edit in edits):
            return None
        return SessionPlanWriteRequest(
            action_id=action_id,
            kind="write-session-plan",
            session_id=session_id,
            edits=cast("tuple[SessionPlanEdit, ...]", edits),
        )
    return None


def prepare_coach_action(
    member_id: str,
    request: CoachActionRequest,
    *,
    session_plan_reader: SessionPlanReader = get_session_plan,
    verdict_evaluator: SessionPlanVerdictEvaluator = evaluate_safety,
) -> CoachActionProposal:
    if not isinstance(request, SessionPlanWriteRequest):
        return CoachActionProposal(action=request, status="pending")
    session_plan = session_plan_reader(member_id, request.session_id)
    if session_plan is None:
        return CoachActionProposal(
            action=WriteSessionPlan(
                action_id=request.action_id,
                kind=request.kind,
                session_id=request.session_id,
                edits=request.edits,
                old_rows=(),
                new_rows=(),
                verdicts=(),
                failure=SessionPlanEditFailure(
                    reason="session-not-found",
                    edit_index=None,
                    row_id=None,
                ),
            ),
            status="failed",
        )
    edited = _apply_session_plan_edits(session_plan.rows, request.edits)
    if isinstance(edited, SessionPlanEditFailure):
        return CoachActionProposal(
            action=WriteSessionPlan(
                action_id=request.action_id,
                kind=request.kind,
                session_id=request.session_id,
                edits=request.edits,
                old_rows=session_plan.rows,
                new_rows=session_plan.rows,
                verdicts=(),
                failure=edited,
            ),
            status="failed",
        )
    verdicts = verdict_evaluator(
        member_id,
        tuple(row.exercise_id for row in edited),
    )
    if len(verdicts) != len(edited) or any(
        verdict.exercise_id != row.exercise_id
        for verdict, row in zip(verdicts, edited, strict=True)
    ):
        raise RuntimeError("Safety verdicts must match the edited session plan rows.")
    action = WriteSessionPlan(
        action_id=request.action_id,
        kind=request.kind,
        session_id=request.session_id,
        edits=request.edits,
        old_rows=session_plan.rows,
        new_rows=edited,
        verdicts=tuple(
            SessionPlanVerdict(
                exercise_id=verdict.exercise_id,
                status=verdict.status,
                trace=verdict.trace,
            )
            for verdict in verdicts
        ),
    )
    return CoachActionProposal(
        action=action,
        status=(
            "blocked"
            if any(verdict.status == "exclude" for verdict in verdicts)
            else "pending"
        ),
    )


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
    if raw_action.get("kind") == "write-session-plan":
        return _session_plan_action_from_payload(action_id, raw_action)
    action = coach_action_from_tool_call(
        action_id,
        _tool_name(raw_action.get("kind")),
        raw_action,
    )
    return action if isinstance(action, SendMemberMessage | UpdateBriefTask) else None


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
    elif isinstance(action, UpdateBriefTask):
        exact_action = {
            "kind": action.kind,
            "coach_task_id": action.coach_task_id,
            "status": action.status,
            "text": action.text,
        }
    else:
        exact_action = {
            "kind": action.kind,
            "session_id": action.session_id,
            "edits": [asdict(edit) for edit in action.edits],
            "old_rows": [asdict(row) for row in action.old_rows],
            "new_rows": [asdict(row) for row in action.new_rows],
            "verdicts": [asdict(verdict) for verdict in action.verdicts],
            "failure": asdict(action.failure) if action.failure is not None else None,
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
    if isinstance(action, SendMemberMessage):
        graph_action = SendMemberMessageWrite(
            message=action.message,
            coach_task_id=action.coach_task_id,
        )
    elif isinstance(action, UpdateBriefTask):
        graph_action = UpdateBriefTaskWrite(
            coach_task_id=action.coach_task_id,
            status=action.status,
            text=action.text,
        )
    else:
        graph_action = WriteSessionPlanWrite(
            session_id=action.session_id,
            rows=action.new_rows,
        )
    return confirm_coach_action(member_id, action.action_id, graph_action)


def _edited_action(
    pending_action: CoachAction,
    raw_action: object,
) -> CoachAction | None:
    if not isinstance(raw_action, dict):
        return None
    edited_action = (
        _session_plan_action_from_payload(pending_action.action_id, raw_action)
        if isinstance(pending_action, WriteSessionPlan)
        else coach_action_from_tool_call(
            pending_action.action_id,
            _tool_name(raw_action.get("kind")),
            raw_action,
        )
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
    if (
        isinstance(pending_action, WriteSessionPlan)
        and isinstance(edited_action, WriteSessionPlan)
        and edited_action == pending_action
    ):
        return edited_action
    return None


def _apply_session_plan_edits(
    current_rows: tuple[SessionPlanRow, ...],
    edits: tuple[SessionPlanEdit, ...],
) -> tuple[SessionPlanRow, ...] | SessionPlanEditFailure:
    rows = list(current_rows)
    for edit_index, edit in enumerate(edits):
        if isinstance(edit, AddSessionPlanRow):
            if any(row.row_id == edit.row.row_id for row in rows):
                return SessionPlanEditFailure(
                    reason="duplicate-row-id",
                    edit_index=edit_index,
                    row_id=edit.row.row_id,
                )
            if edit.position < 0 or edit.position > len(rows):
                return SessionPlanEditFailure(
                    reason="position-out-of-range",
                    edit_index=edit_index,
                    row_id=edit.row.row_id,
                )
            rows.insert(edit.position, edit.row)
            continue
        row_id = (
            edit.row.row_id if isinstance(edit, EditSessionPlanRow) else edit.row_id
        )
        position = next(
            (index for index, row in enumerate(rows) if row.row_id == row_id),
            None,
        )
        if position is None:
            return SessionPlanEditFailure(
                reason="row-not-found",
                edit_index=edit_index,
                row_id=row_id,
            )
        if isinstance(edit, EditSessionPlanRow):
            rows[position] = edit.row
        elif isinstance(edit, RemoveSessionPlanRow):
            rows.pop(position)
        else:
            row = rows.pop(position)
            if edit.position < 0 or edit.position > len(rows):
                return SessionPlanEditFailure(
                    reason="position-out-of-range",
                    edit_index=edit_index,
                    row_id=edit.row_id,
                )
            rows.insert(edit.position, row)
    return tuple(rows)


def _session_plan_action_from_payload(
    action_id: str,
    value: dict[object, object],
) -> WriteSessionPlan | None:
    request = coach_action_from_tool_call(
        action_id,
        write_session_plan.name,
        value,
    )
    if not isinstance(request, SessionPlanWriteRequest):
        return None
    raw_old_rows = value.get("old_rows")
    raw_new_rows = value.get("new_rows")
    raw_verdicts = value.get("verdicts")
    if (
        not isinstance(raw_old_rows, list)
        or not isinstance(raw_new_rows, list)
        or not isinstance(raw_verdicts, list)
    ):
        return None
    old_rows = tuple(_session_plan_row(item) for item in raw_old_rows)
    new_rows = tuple(_session_plan_row(item) for item in raw_new_rows)
    verdicts = tuple(_session_plan_verdict(item) for item in raw_verdicts)
    if (
        any(row is None for row in old_rows)
        or any(row is None for row in new_rows)
        or any(verdict is None for verdict in verdicts)
    ):
        return None
    raw_failure = value.get("failure")
    failure = None if raw_failure is None else _session_plan_edit_failure(raw_failure)
    if raw_failure is not None and failure is None:
        return None
    return WriteSessionPlan(
        action_id=action_id,
        kind="write-session-plan",
        session_id=request.session_id,
        edits=request.edits,
        old_rows=cast("tuple[SessionPlanRow, ...]", old_rows),
        new_rows=cast("tuple[SessionPlanRow, ...]", new_rows),
        verdicts=cast("tuple[SessionPlanVerdict, ...]", verdicts),
        failure=failure,
    )


def _session_plan_edit(value: object) -> SessionPlanEdit | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind in ("add", "edit"):
        row = _session_plan_row(value.get("row"))
        if row is None:
            return None
        if kind == "edit":
            return EditSessionPlanRow(kind="edit", row=row)
        position = _non_negative_int(value.get("position"))
        if position is None:
            return None
        return AddSessionPlanRow(kind="add", row=row, position=position)
    if kind in ("reorder", "remove"):
        row_id = _required_text(value.get("row_id"))
        if row_id is None:
            return None
        if kind == "remove":
            return RemoveSessionPlanRow(kind="remove", row_id=row_id)
        position = _non_negative_int(value.get("position"))
        if position is None:
            return None
        return ReorderSessionPlanRow(
            kind="reorder",
            row_id=row_id,
            position=position,
        )
    return None


def _session_plan_row(value: object) -> SessionPlanRow | None:
    if not isinstance(value, dict):
        return None
    row_id = _required_text(value.get("row_id"))
    exercise_id = _required_text(value.get("exercise_id"))
    section = value.get("section")
    if section not in (None, "warm-up", "main", "cool-down"):
        return None
    sets = _optional_positive_int(value.get("sets"))
    reps = _optional_positive_int(value.get("reps"))
    hold_minutes = _optional_non_negative_number(value.get("hold_minutes"))
    rest_minutes = _optional_non_negative_number(value.get("rest_minutes"))
    minutes = _optional_non_negative_number(value.get("minutes"))
    per_side = _optional_bool(value.get("per_side"))
    supports_weight = _optional_bool(value.get("supports_weight"))
    if (
        row_id is None
        or exercise_id is None
        or _INVALID
        in (
            sets,
            reps,
            hold_minutes,
            rest_minutes,
            minutes,
            per_side,
            supports_weight,
        )
    ):
        return None
    return SessionPlanRow(
        row_id=row_id,
        exercise_id=exercise_id,
        section=cast("Literal['warm-up', 'main', 'cool-down'] | None", section),
        sets=cast("int | None", sets),
        reps=cast("int | None", reps),
        hold_minutes=cast("float | None", hold_minutes),
        rest_minutes=cast("float | None", rest_minutes),
        per_side=cast("bool | None", per_side),
        supports_weight=cast("bool | None", supports_weight),
        minutes=cast("float | None", minutes),
    )


def _session_plan_verdict(value: object) -> SessionPlanVerdict | None:
    if not isinstance(value, dict):
        return None
    exercise_id = _required_text(value.get("exercise_id"))
    status = value.get("status")
    raw_trace = value.get("trace")
    if (
        exercise_id is None
        or status not in ("exclude", "caution", "clear")
        or not isinstance(raw_trace, list)
    ):
        return None
    trace = tuple(_verdict_trace_event(item) for item in raw_trace)
    if any(event is None for event in trace):
        return None
    return SessionPlanVerdict(
        exercise_id=exercise_id,
        status=status,
        trace=cast("tuple[VerdictTraceEvent, ...]", trace),
    )


def _verdict_trace_event(value: object) -> VerdictTraceEvent | None:
    if not isinstance(value, dict):
        return None
    exercise_id = _required_text(value.get("exercise_id"))
    status = value.get("status")
    layer = value.get("layer")
    reason = _required_text(value.get("reason"))
    walked_path = _walked_path(value.get("walked_path"))
    raw_used = value.get("used")
    attribution = value.get("was_attributed_to")
    if (
        exercise_id is None
        or status not in ("exclude", "caution", "clear")
        or layer
        not in (
            None,
            "clinical directive",
            "contraindication",
            "SNOMED anatomical fallback",
        )
        or reason is None
        or walked_path is None
        or not isinstance(raw_used, list)
        or not all(isinstance(item, str) for item in raw_used)
        or value.get("kind") != "verdict"
        or value.get("was_generated_by") != "evaluate_safety"
        or attribution not in ("graph", "agent")
    ):
        return None
    return VerdictTraceEvent(
        exercise_id=exercise_id,
        status=status,
        layer=layer,
        reason=reason,
        walked_path=walked_path,
        used=tuple(cast("list[str]", raw_used)),
        was_attributed_to=attribution,
    )


def _walked_path(value: object) -> WalkedPath | None:
    if not isinstance(value, dict):
        return None
    raw_nodes = value.get("nodes")
    raw_edges = value.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return None
    nodes = tuple(_walked_node(item) for item in raw_nodes)
    edges = tuple(_walked_edge(item) for item in raw_edges)
    if any(node is None for node in nodes) or any(edge is None for edge in edges):
        return None
    return WalkedPath(
        nodes=cast("tuple[WalkedNode, ...]", nodes),
        edges=cast("tuple[WalkedEdge, ...]", edges),
    )


def _walked_node(value: object) -> WalkedNode | None:
    if not isinstance(value, dict):
        return None
    node_id = _required_text(value.get("node_id"))
    kind = _required_text(value.get("kind"))
    name = _optional_text(value.get("name"))
    if node_id is None or kind is None or name is _INVALID:
        return None
    return WalkedNode(
        node_id=node_id,
        kind=cast("GraphNodeKind", kind),
        name=cast("str | None", name),
    )


def _walked_edge(value: object) -> WalkedEdge | None:
    if not isinstance(value, dict):
        return None
    edge_id = _required_text(value.get("edge_id"))
    kind = _required_text(value.get("kind"))
    source_id = _required_text(value.get("source_id"))
    target_id = _required_text(value.get("target_id"))
    if None in (edge_id, kind, source_id, target_id):
        return None
    return WalkedEdge(
        edge_id=cast(str, edge_id),
        kind=cast("GraphEdgeKind", kind),
        source_id=cast(str, source_id),
        target_id=cast(str, target_id),
    )


def _session_plan_edit_failure(value: object) -> SessionPlanEditFailure | None:
    if not isinstance(value, dict):
        return None
    reason = value.get("reason")
    edit_index = value.get("edit_index")
    row_id = _optional_text(value.get("row_id"))
    if (
        reason
        not in (
            "session-not-found",
            "row-not-found",
            "duplicate-row-id",
            "position-out-of-range",
        )
        or (edit_index is not None and _non_negative_int(edit_index) is None)
        or row_id is _INVALID
    ):
        return None
    return SessionPlanEditFailure(
        reason=reason,
        edit_index=cast("int | None", edit_index),
        row_id=cast("str | None", row_id),
    )


def _tool_name(kind: object) -> str:
    if kind == "send-member-message":
        return send_member_message.name
    if kind == "update-brief-task":
        return update_brief_task.name
    if kind == "write-session-plan":
        return write_session_plan.name
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


def _non_negative_int(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _optional_positive_int(value: object) -> int | None | _Invalid:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return _INVALID
    return value


def _optional_non_negative_number(value: object) -> float | None | _Invalid:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        return _INVALID
    return float(value)


def _optional_bool(value: object) -> bool | None | _Invalid:
    if value is None or isinstance(value, bool):
        return value
    return _INVALID
