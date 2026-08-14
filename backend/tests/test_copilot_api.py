import json

from app.api.copilot import (
    DataPart,
    HistoryReader,
    TurnRunner,
    create_copilot_router,
)
from app.copilot import (
    CopilotDataPart,
    CopilotHistoryMessage,
    CopilotTurn,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

MEMBER_ID = "mbr_01HX9JORDAN"


def test_copilot_stream_emits_data_sources_before_text_for_use_chat() -> None:
    sources_part = _sources_part()

    def run_turn(
        member_id: str,
        message: str,
        message_id: str,
    ) -> CopilotTurn:
        assert member_id == MEMBER_ID
        assert message == "What is the priority goal?"
        assert message_id == "user-1"
        return CopilotTurn(
            message_id="assistant-1",
            text="Build strength.",
            data_parts=(sources_part,),
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
    sources_part = _sources_part()
    chart_part = CopilotDataPart(
        type="data-chart",
        data={"kind": "sleep-week", "series": [{"day": "Mon", "hours": 7.5}]},
    )

    def read_history(
        member_id: str,
    ) -> tuple[CopilotHistoryMessage, ...]:
        assert member_id == MEMBER_ID
        return (
            CopilotHistoryMessage(
                id="user-1",
                role="user",
                text="What is the priority goal?",
                data_parts=(),
            ),
            CopilotHistoryMessage(
                id="assistant-1",
                role="assistant",
                text="Build strength.",
                data_parts=(sources_part, chart_part),
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
                    {
                        "type": "data-chart",
                        "data": {
                            "kind": "sleep-week",
                            "series": [{"day": "Mon", "hours": 7.5}],
                        },
                    },
                    {"type": "text", "text": "Build strength."},
                ],
            },
        ],
    }


def test_data_part_is_a_frozen_generic_pydantic_contract() -> None:
    assert DataPart.model_config["frozen"] is True
    schema = DataPart.model_json_schema()
    assert schema["properties"]["type"]["type"] == "string"


def _client(
    *,
    turn_runner: TurnRunner | None = None,
    history_reader: HistoryReader | None = None,
) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(
        create_copilot_router(
            turn_runner=turn_runner,
            history_reader=history_reader,
        )
    )
    return TestClient(test_app)


def _sources_part() -> CopilotDataPart:
    return CopilotDataPart(
        type="data-sources",
        data={
            "sources": [
                {
                    "tool": "get_member_goals",
                    "node_ids": [MEMBER_ID, "goal:1"],
                }
            ]
        },
    )


def _events(stream: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: {")
    ]
