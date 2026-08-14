from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel, ConfigDict, Field

from app.api.generation_parts import (
    generation_data_parts,
)
from app.generation import (
    GenerationTurn,
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


type TurnRunner = Callable[
    [str, str, int, str, str],
    GenerationTurn,
]


def create_generate_router(
    *,
    turn_runner: TurnRunner | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/members/{member_id}/generate")
    run_turn = turn_runner or run_generation_session

    @router.post("")
    def generate_stream(
        member_id: str,
        request: GenerateStreamRequest,
    ) -> StreamingResponse:
        user_message = _latest_user_message(request.messages)
        try:
            turn = run_turn(
                member_id,
                _message_text(user_message.parts),
                request.window,
                request.id,
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
    for part in generation_data_parts(turn):
        yield _sse(part.model_dump(mode="json", by_alias=True))
    yield _sse({"type": "text-start", "id": text_part_id})
    yield _sse({"type": "text-delta", "id": text_part_id, "delta": turn.text})
    yield _sse({"type": "text-end", "id": text_part_id})
    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish", "finishReason": "stop"})
    yield "data: [DONE]\n\n"


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


router = create_generate_router()
