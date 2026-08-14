import json

from app.api.generate import TurnRunner, create_generate_router
from app.generation import GenerationTurn
from fastapi import FastAPI
from fastapi.testclient import TestClient

MEMBER_ID = "mbr_01HX9JORDAN"


def test_generate_stream_calls_the_generation_session_seam() -> None:
    def run_turn(
        member_id: str,
        message: str,
        window: int,
        thread_id: str,
        message_id: str,
    ) -> GenerationTurn:
        assert member_id == MEMBER_ID
        assert message == "Build a 30 minute lower-body workout."
        assert window == 30
        assert thread_id == "generation-thread-1"
        assert message_id == "user-1"
        return GenerationTurn(
            message_id="user-1-assistant",
            plan=None,
            trace=(),
            resolved_intent=None,
            failure=None,
            text="Session ready.",
        )

    response = _client(turn_runner=run_turn).post(
        f"/api/members/{MEMBER_ID}/generate",
        json={
            "id": "generation-thread-1",
            "window": 30,
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "parts": [
                        {
                            "type": "text",
                            "text": "Build a 30 minute lower-body workout.",
                        }
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert [event["type"] for event in _events(response.text)] == [
        "start",
        "start-step",
        "data-trace",
        "data-constraints",
        "text-start",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
    ]


def _client(*, turn_runner: TurnRunner) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(create_generate_router(turn_runner=turn_runner))
    return TestClient(test_app)


def _events(stream: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: {")
    ]
