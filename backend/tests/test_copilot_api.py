import json

from app.api.copilot import (
    DataChartPart,
    DataPart,
    DataSourcesPart,
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


def test_copilot_stream_emits_data_parts_in_prescribed_order_before_text() -> None:
    sources_part = _sources_part()
    chart_part = _chart_part()
    brief_part = CopilotDataPart(type="data-brief", data={"priority": "strength"})
    action_part = CopilotDataPart(type="data-action", data={"kind": "send-message"})

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
            data_parts=(action_part, sources_part, brief_part, chart_part),
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
        "data-chart",
        "data-sources",
        "data-brief",
        "data-action",
        "text-start",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
    ]
    assert events[3] == {
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
    chart_part = _chart_part()

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
                        "type": "data-chart",
                        "data": _chart_part().data,
                    },
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


def test_data_sources_part_is_a_frozen_typed_pydantic_contract() -> None:
    assert DataSourcesPart.model_config["frozen"] is True
    schema = DataSourcesPart.model_json_schema()
    assert schema["properties"]["type"]["const"] == "data-sources"
    assert schema["properties"]["data"] == {"$ref": "#/$defs/DataSources"}
    assert schema["$defs"]["DataSources"]["properties"]["sources"]["items"] == {
        "$ref": "#/$defs/Source"
    }


def test_data_chart_part_is_a_frozen_discriminated_pydantic_contract() -> None:
    assert DataChartPart.model_config["frozen"] is True
    schema = DataChartPart.model_json_schema()
    assert schema["properties"]["type"]["const"] == "data-chart"
    assert schema["properties"]["data"] == {"$ref": "#/$defs/DataChart"}
    assert set(schema["$defs"]["DataChart"]["discriminator"]["mapping"]) == {
        "adherence_trend",
        "sleep_week",
        "message_pattern",
        "four_week_comparison",
    }

    chart = DataChartPart.model_validate({"data": _chart_part().data})
    assert chart.data.kind == "sleep_week"
    assert chart.model_dump()["data"]["series"][0]["hours"] == 7.5


def test_data_part_keeps_future_data_kinds_generic() -> None:
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


def _chart_part() -> CopilotDataPart:
    return CopilotDataPart(
        type="data-chart",
        data={
            "kind": "sleep_week",
            "window": "7-days",
            "axes": {
                "x": {"label": "Night", "values": ["2026-06-03"]},
                "y": {
                    "label": "Sleep",
                    "unit": "hours",
                    "minimum": 0,
                    "maximum": 9,
                    "ticks": [0, 3, 6, 9],
                },
            },
            "series": [
                {
                    "observed_at": "2026-06-03",
                    "hours": 7.5,
                    "observation_node_id": "observation:sleep:2026-06-03",
                }
            ],
            "observation_node_ids": ["observation:sleep:2026-06-03"],
        },
    )


def _events(stream: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: {")
    ]
