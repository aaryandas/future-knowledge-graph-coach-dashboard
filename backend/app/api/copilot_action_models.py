from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.generation_parts import VerdictTraceEvent

type NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class SendMemberMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["send-member-message"]
    message: NonEmptyText
    coach_task_id: NonEmptyText | None = None


class UpdateBriefTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["update-brief-task"]
    coach_task_id: NonEmptyText
    status: Literal["open", "completed", "dismissed"]
    text: NonEmptyText | None = None


class SessionPlanRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_id: NonEmptyText
    exercise_id: NonEmptyText
    section: Literal["warm-up", "main", "cool-down"] | None
    sets: Annotated[int, Field(gt=0)] | None
    reps: Annotated[int, Field(gt=0)] | None
    hold_minutes: Annotated[float, Field(ge=0)] | None
    rest_minutes: Annotated[float, Field(ge=0)] | None
    per_side: bool | None
    supports_weight: bool | None
    minutes: Annotated[float, Field(ge=0)] | None


class AddSessionPlanRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["add"]
    row: SessionPlanRow
    position: Annotated[int, Field(ge=0)]


class EditSessionPlanRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["edit"]
    row: SessionPlanRow


class ReorderSessionPlanRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["reorder"]
    row_id: NonEmptyText
    position: Annotated[int, Field(ge=0)]


class RemoveSessionPlanRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["remove"]
    row_id: NonEmptyText


type SessionPlanEdit = Annotated[
    AddSessionPlanRow
    | EditSessionPlanRow
    | ReorderSessionPlanRow
    | RemoveSessionPlanRow,
    Field(discriminator="kind"),
]


class SessionPlanVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    exercise_id: NonEmptyText
    status: Literal["exclude", "caution", "clear"]
    trace: list[VerdictTraceEvent]


class SessionPlanEditFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: Literal[
        "session-not-found",
        "row-not-found",
        "duplicate-row-id",
        "position-out-of-range",
    ]
    edit_index: Annotated[int, Field(ge=0)] | None
    row_id: NonEmptyText | None


class WriteSessionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["write-session-plan"]
    session_id: NonEmptyText
    edits: Annotated[list[SessionPlanEdit], Field(min_length=1)]
    old_rows: list[SessionPlanRow]
    new_rows: list[SessionPlanRow]
    verdicts: list[SessionPlanVerdict]
    failure: SessionPlanEditFailure | None


type CoachAction = Annotated[
    SendMemberMessage | UpdateBriefTask | WriteSessionPlan,
    Field(discriminator="kind"),
]


class DataAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    status: Literal["pending", "confirmed", "discarded", "failed", "blocked"]
    action: CoachAction
    actor: NonEmptyText | None = None
    timestamp: NonEmptyText | None = None


class DataActionPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-action"] = "data-action"
    data: DataAction
