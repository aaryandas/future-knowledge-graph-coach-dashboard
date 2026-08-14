from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any, Literal

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.base import BaseCheckpointSaver
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel, ConfigDict, Field

from app.api.generation_parts import (
    data_constraints_part,
    data_plan_part,
    data_trace_part,
)
from app.generation import (
    GenerationTurn,
    IntentLLM,
    build_intent_llm,
    open_postgres_checkpointer,
    run_generation_session,
)


class GenerateRequestMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str
    role: Literal["user", "assistant", "system"]
    parts: list[dict[str, object]]


class GenerateStreamRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(min_length=1)
    messages: list[GenerateRequestMessage]
    window: int = Field(ge=20)


type LLMFactory = Callable[[], IntentLLM | None]
type CheckpointerFactory = Callable[
    [], AbstractContextManager[BaseCheckpointSaver[Any]]
]
type TurnRunner = Callable[
    [str, str, int, str, BaseCheckpointSaver[Any], IntentLLM | None, str],
    GenerationTurn,
]


def create_generate_router(
    *,
    llm_factory: LLMFactory = build_intent_llm,
    checkpointer_factory: CheckpointerFactory = open_postgres_checkpointer,
    turn_runner: TurnRunner | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/members/{member_id}/generate")
    run_turn = turn_runner or _run_turn

    @router.post("")
    def generate_stream(
        member_id: str,
        request: GenerateStreamRequest,
    ) -> StreamingResponse:
        user_message = _latest_user_message(request.messages)
        try:
            with checkpointer_factory() as checkpointer:
                turn = run_turn(
                    member_id,
                    _message_text(user_message.parts),
                    request.window,
                    request.id,
                    checkpointer,
                    llm_factory(),
                    user_message.id,
                )
        except psycopg.Error as error:
            raise HTTPException(
                status_code=503,
                detail="Generation thread storage is unavailable.",
            ) from error
        except Neo4jError as error:
            raise HTTPException(
                status_code=503,
                detail="Generation graph storage is unavailable.",
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

    return router


def _run_turn(
    member_id: str,
    message: str,
    window: int,
    thread_id: str,
    checkpointer: BaseCheckpointSaver[Any],
    llm: IntentLLM | None,
    message_id: str,
) -> GenerationTurn:
    return run_generation_session(
        member_id,
        message,
        window,
        thread_id,
        checkpointer=checkpointer,
        llm=llm,
        message_id=message_id,
    )


def _latest_user_message(
    messages: list[GenerateRequestMessage],
) -> GenerateRequestMessage:
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


def _ui_message_stream(turn: GenerationTurn) -> Iterator[str]:
    text_part_id = f"{turn.message_id}-text"
    yield _sse({"type": "start", "messageId": turn.message_id})
    yield _sse({"type": "start-step"})
    if turn.plan is not None:
        yield _sse(data_plan_part(turn.plan).model_dump(mode="json", by_alias=True))
    yield _sse(data_trace_part(turn.trace).model_dump(mode="json", by_alias=True))
    yield _sse(
        data_constraints_part(
            turn.resolved_intent,
            turn.failure,
        ).model_dump(mode="json", by_alias=True)
    )
    yield _sse({"type": "text-start", "id": text_part_id})
    yield _sse({"type": "text-delta", "id": text_part_id, "delta": turn.text})
    yield _sse({"type": "text-end", "id": text_part_id})
    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish", "finishReason": "stop"})
    yield "data: [DONE]\n\n"


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


router = create_generate_router()
