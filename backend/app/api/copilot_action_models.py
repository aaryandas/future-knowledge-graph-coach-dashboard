from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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


type CoachAction = Annotated[
    SendMemberMessage | UpdateBriefTask,
    Field(discriminator="kind"),
]


class DataAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    status: Literal["pending", "confirmed", "discarded", "failed"]
    action: CoachAction


class DataActionPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-action"] = "data-action"
    data: DataAction
