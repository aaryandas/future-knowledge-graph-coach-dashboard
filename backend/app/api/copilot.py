from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any, Literal

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict

from app.copilot import (
    CopilotHistoryMessage,
    CopilotLLM,
    CopilotSource,
    CopilotTurn,
    build_copilot_llm,
    open_postgres_checkpointer,
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
    parts: list[TextPart | DataSourcesPart]


class CopilotHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    messages: list[CopilotReplayMessage]


type LLMFactory = Callable[[], CopilotLLM | None]
type CheckpointerFactory = Callable[
    [], AbstractContextManager[BaseCheckpointSaver[Any]]
]
type TurnRunner = Callable[
    [str, str, BaseCheckpointSaver[Any], CopilotLLM | None, str], CopilotTurn
]
type HistoryReader = Callable[
    [str, BaseCheckpointSaver[Any]], tuple[CopilotHistoryMessage, ...]
]


def create_copilot_router(
    *,
    llm_factory: LLMFactory = build_copilot_llm,
    checkpointer_factory: CheckpointerFactory = open_postgres_checkpointer,
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
            with checkpointer_factory() as checkpointer:
                turn = run_turn(
                    member_id,
                    _message_text(user_message.parts),
                    checkpointer,
                    llm_factory(),
                    user_message.id,
                )
        except psycopg.Error as error:
            raise HTTPException(
                status_code=503,
                detail="Copilot thread storage is unavailable.",
            ) from error
        return StreamingResponse(
            _ui_message_stream(turn),
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
            with checkpointer_factory() as checkpointer:
                messages = read_history(member_id, checkpointer)
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
    checkpointer: BaseCheckpointSaver[Any],
    llm: CopilotLLM | None,
    message_id: str,
) -> CopilotTurn:
    return run_copilot_turn(
        member_id,
        message,
        checkpointer=checkpointer,
        llm=llm,
        message_id=message_id,
    )


def _read_history(
    member_id: str,
    checkpointer: BaseCheckpointSaver[Any],
) -> tuple[CopilotHistoryMessage, ...]:
    return replay_copilot_history(member_id, checkpointer=checkpointer)


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


def _source(source: CopilotSource) -> Source:
    return Source(tool=source.tool, node_ids=list(source.node_ids))


def _data_sources_part(sources: tuple[CopilotSource, ...]) -> DataSourcesPart:
    return DataSourcesPart(
        data=DataSources(sources=[_source(source) for source in sources])
    )


def _replay_message(message: CopilotHistoryMessage) -> CopilotReplayMessage:
    parts: list[TextPart | DataSourcesPart]
    if message.role == "assistant":
        parts = [
            _data_sources_part(message.sources),
            TextPart(text=message.text),
        ]
    else:
        parts = [TextPart(text=message.text)]
    return CopilotReplayMessage(id=message.id, role=message.role, parts=parts)


def _ui_message_stream(turn: CopilotTurn) -> Iterator[str]:
    text_part_id = f"{turn.message_id}-text"
    yield _sse({"type": "start", "messageId": turn.message_id})
    yield _sse({"type": "start-step"})
    yield _sse(_data_sources_part(turn.sources).model_dump(mode="json"))
    yield _sse({"type": "text-start", "id": text_part_id})
    yield _sse({"type": "text-delta", "id": text_part_id, "delta": turn.text})
    yield _sse({"type": "text-end", "id": text_part_id})
    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish", "finishReason": "stop"})
    yield "data: [DONE]\n\n"


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


router = create_copilot_router()
