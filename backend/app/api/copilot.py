from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, JsonValue

from app.api.copilot_action_models import DataAction, DataActionPart
from app.api.copilot_brief_models import DataBrief, DataBriefPart
from app.api.data_chart import DataChartPart
from app.copilot import (
    CopilotConflict,
    CopilotDataPart,
    CopilotHistoryMessage,
    CopilotTurn,
    CopilotTurnResult,
    replay_copilot_history,
    run_copilot_turn,
)


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool: str
    node_ids: list[str]


class DataSources(BaseModel):
    model_config = ConfigDict(frozen=True)

    sources: list[Source]


class DataSourcesPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-sources"] = "data-sources"
    data: DataSources


class DataPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    data: JsonValue


class TextPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["text"] = "text"
    text: str


class CopilotRequestMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str
    role: Literal["user", "assistant", "system"]
    parts: list[dict[str, object]]


class CopilotStreamRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str
    messages: list[CopilotRequestMessage]


class CopilotReplayMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    role: Literal["user", "assistant"]
    parts: list[
        TextPart
        | DataChartPart
        | DataSourcesPart
        | DataBriefPart
        | DataActionPart
        | DataPart
    ]


class CopilotHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    messages: list[CopilotReplayMessage]


type TurnRunner = Callable[[str, str, str], CopilotTurnResult]
type HistoryReader = Callable[[str], tuple[CopilotHistoryMessage, ...]]

_DATA_PART_ORDER = {
    "data-chart": 0,
    "data-sources": 1,
    "data-brief": 2,
    "data-action": 3,
}


def create_copilot_router(
    *,
    turn_runner: TurnRunner | None = None,
    history_reader: HistoryReader | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/members/{member_id}/copilot")
    run_turn = turn_runner or _run_turn
    read_history = history_reader or _read_history

    @router.post("")
    def copilot_stream(
        member_id: str,
        request: CopilotStreamRequest,
    ) -> StreamingResponse:
        if request.id != member_id:
            raise HTTPException(
                status_code=409,
                detail="The useChat thread id must match the member id.",
            )
        user_message = _latest_user_message(request.messages)
        try:
            result = run_turn(
                member_id,
                _message_text(user_message.parts),
                user_message.id,
            )
        except psycopg.Error as error:
            raise HTTPException(
                status_code=503,
                detail="Copilot thread storage is unavailable.",
            ) from error
        if isinstance(result, CopilotConflict):
            raise HTTPException(status_code=409, detail=result.detail)
        return StreamingResponse(
            copilot_turn_stream(result),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "x-vercel-ai-ui-message-stream": "v1",
            },
        )

    @router.get("/history", response_model=CopilotHistory)
    def copilot_history(member_id: str) -> CopilotHistory:
        try:
            messages = read_history(member_id)
        except psycopg.Error as error:
            raise HTTPException(
                status_code=503,
                detail="Copilot thread storage is unavailable.",
            ) from error
        return CopilotHistory(
            id=member_id,
            messages=[_replay_message(message) for message in messages],
        )

    return router


def _run_turn(
    member_id: str,
    message: str,
    message_id: str,
) -> CopilotTurnResult:
    return run_copilot_turn(
        member_id,
        message,
        message_id=message_id,
    )


def _read_history(
    member_id: str,
) -> tuple[CopilotHistoryMessage, ...]:
    return replay_copilot_history(member_id)


def _latest_user_message(
    messages: list[CopilotRequestMessage],
) -> CopilotRequestMessage:
    for message in reversed(messages):
        if message.role != "user":
            continue
        if _message_text(message.parts):
            return message
    raise HTTPException(status_code=422, detail="A user text part is required.")


def _message_text(parts: list[dict[str, object]]) -> str:
    return "\n".join(
        text.strip()
        for part in parts
        if part.get("type") == "text"
        and isinstance((text := part.get("text")), str)
        and text.strip()
    )


def _data_part(
    part: CopilotDataPart,
) -> DataChartPart | DataSourcesPart | DataBriefPart | DataActionPart | DataPart:
    if part.type == "data-chart":
        return DataChartPart.model_validate({"data": part.data})
    if part.type == "data-sources":
        return DataSourcesPart(data=DataSources.model_validate(part.data))
    if part.type == "data-brief":
        return DataBriefPart(data=DataBrief.model_validate(part.data))
    if part.type == "data-action":
        return DataActionPart(data=DataAction.model_validate(part.data))
    return DataPart(type=part.type, data=part.data)


def _replay_message(message: CopilotHistoryMessage) -> CopilotReplayMessage:
    parts: list[
        TextPart
        | DataChartPart
        | DataSourcesPart
        | DataBriefPart
        | DataActionPart
        | DataPart
    ] = [
        *(_data_part(part) for part in _ordered_data_parts(message.data_parts)),
        TextPart(text=message.text),
    ]
    return CopilotReplayMessage(id=message.id, role=message.role, parts=parts)


def copilot_turn_stream(turn: CopilotTurn) -> Iterator[str]:
    text_part_id = f"{turn.message_id}-text"
    yield _sse({"type": "start", "messageId": turn.message_id})
    yield _sse({"type": "start-step"})
    for part in _ordered_data_parts(turn.data_parts):
        yield _sse(_data_part(part).model_dump(mode="json"))
    yield _sse({"type": "text-start", "id": text_part_id})
    yield _sse({"type": "text-delta", "id": text_part_id, "delta": turn.text})
    yield _sse({"type": "text-end", "id": text_part_id})
    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish", "finishReason": "stop"})
    yield "data: [DONE]\n\n"


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


def _ordered_data_parts(
    parts: tuple[CopilotDataPart, ...],
) -> tuple[CopilotDataPart, ...]:
    return tuple(sorted(parts, key=lambda part: _DATA_PART_ORDER.get(part.type, 4)))


router = create_copilot_router()
