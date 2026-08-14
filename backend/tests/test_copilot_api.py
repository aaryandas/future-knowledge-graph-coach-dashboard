import json
from contextlib import nullcontext
from typing import Any

from app.api.copilot import (
    DataSourcesPart,
    HistoryReader,
    TurnRunner,
    create_copilot_router,
)
from app.copilot import (
    CopilotHistoryMessage,
    CopilotLLM,
    CopilotSource,
    CopilotTurn,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "mbr_01HX9JORDAN"


def test_copilot_stream_emits_data_sources_before_text_for_use_chat() -> None:
    source = CopilotSource(tool="get_member_goals", node_ids=(MEMBER_ID, "goal:1"))

    def run_turn(
        member_id: str,
        message: str,
        checkpointer: BaseCheckpointSaver[Any],
        llm: CopilotLLM | None,
        message_id: str,
    ) -> CopilotTurn:
        assert member_id == MEMBER_ID
        assert message == "What is the priority goal?"
        assert message_id == "user-1"
        return CopilotTurn(
            message_id="assistant-1", text="Build strength.", sources=(source,)
        )

    response = _client(turn_runner=run_turn).post(
        f"/api/members/{MEMBER_ID}/copilot",
        json={
            "id": MEMBER_ID,
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "parts": [{"type": "text", "text": "What is the priority goal?"}],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    events = _events(response.text)
    assert [event["type"] for event in events] == [
        "start",
        "start-step",
        "data-sources",
        "text-start",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
    ]
    assert events[2] == {
        "type": "data-sources",
        "data": {
            "sources": [
                {
                    "tool": "get_member_goals",
                    "node_ids": [MEMBER_ID, "goal:1"],
                }
            ]
        },
    }


def test_copilot_history_returns_replayable_data_parts() -> None:
    source = CopilotSource(tool="get_member_goals", node_ids=(MEMBER_ID, "goal:1"))

    def read_history(
        member_id: str,
        checkpointer: BaseCheckpointSaver[Any],
    ) -> tuple[CopilotHistoryMessage, ...]:
        assert member_id == MEMBER_ID
        return (
            CopilotHistoryMessage(
                id="user-1",
                role="user",
                text="What is the priority goal?",
                sources=(),
            ),
            CopilotHistoryMessage(
                id="assistant-1",
                role="assistant",
                text="Build strength.",
                sources=(source,),
            ),
        )

    response = _client(history_reader=read_history).get(
        f"/api/members/{MEMBER_ID}/copilot/history"
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": MEMBER_ID,
        "messages": [
            {
                "id": "user-1",
                "role": "user",
                "parts": [{"type": "text", "text": "What is the priority goal?"}],
            },
            {
                "id": "assistant-1",
                "role": "assistant",
                "parts": [
                    {
                        "type": "data-sources",
                        "data": {
                            "sources": [
                                {
                                    "tool": "get_member_goals",
                                    "node_ids": [MEMBER_ID, "goal:1"],
                                }
                            ]
                        },
                    },
                    {"type": "text", "text": "Build strength."},
                ],
            },
        ],
    }


def test_data_sources_part_is_a_frozen_pydantic_contract() -> None:
    assert DataSourcesPart.model_config["frozen"] is True
    schema = DataSourcesPart.model_json_schema()
    assert schema["properties"]["type"]["const"] == "data-sources"


def _client(
    *,
    turn_runner: TurnRunner | None = None,
    history_reader: HistoryReader | None = None,
) -> TestClient:
    checkpointer = InMemorySaver()
    test_app = FastAPI()
    test_app.include_router(
        create_copilot_router(
            llm_factory=lambda: None,
            checkpointer_factory=lambda: nullcontext(checkpointer),
            turn_runner=turn_runner,
            history_reader=history_reader,
        )
    )
    return TestClient(test_app)


def _events(stream: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: {")
    ]
