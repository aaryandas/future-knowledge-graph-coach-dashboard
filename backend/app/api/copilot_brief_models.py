from typing import Literal

from pydantic import BaseModel, ConfigDict


class Barrier(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    kind: str
    copper_id: str
    reason: str
    risk_level: str
    evidence_node_ids: list[str]


class CoachTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    generated_for: str
    type: str
    text: str
    status: str
    addressed_node_ids: list[str]


class DataBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_for: str
    churn_risk_level: str
    churn_risk_reasons: list[str]
    barriers: list[Barrier]
    coach_tasks: list[CoachTask]


class DataBriefPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-brief"] = "data-brief"
    data: DataBrief
