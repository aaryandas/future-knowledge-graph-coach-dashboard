import json

from app.api.generate import TurnRunner, create_generate_router
from app.generation import GenerationTurn
from app.generation.testing import Plan, PlanEntry, PlanSection
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


def test_coaching_note_text_parts_stream_after_plan_and_trace() -> None:
    def run_turn(
        member_id: str,
        message: str,
        window: int,
        thread_id: str,
        message_id: str,
    ) -> GenerationTurn:
        return GenerationTurn(
            message_id="user-1-assistant",
            plan=_plan(),
            trace=(),
            resolved_intent=None,
            failure=None,
            text="Session ready.",
            coaching_note_parts=(
                "Keep the load light.",
                " Stop if knee pain increases.",
            ),
        )

    response = _client(turn_runner=run_turn).post(
        f"/api/members/{MEMBER_ID}/generate",
        json={
            "id": "generation-thread-1",
            "window": 20,
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "parts": [{"type": "text", "text": "Build a workout."}],
                }
            ],
        },
    )

    events = _events(response.text)
    event_types = [event["type"] for event in events]
    annotation_indexes = [
        index
        for index, event in enumerate(events)
        if event.get("id") == "user-1-assistant-annotation"
    ]
    assert response.status_code == 200
    assert event_types.index("data-plan") < min(annotation_indexes)
    assert event_types.index("data-trace") < min(annotation_indexes)
    assert [
        event["delta"]
        for event in events
        if event.get("id") == "user-1-assistant-annotation"
        and event["type"] == "text-delta"
    ] == ["Keep the load light.", " Stop if knee pain increases."]


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


def _plan() -> Plan:
    entry = PlanEntry(
        exercise_id="ex-1",
        name="March",
        sets=2,
        reps=8,
        hold_minutes=None,
        rest_minutes=0.5,
        per_side=False,
        supports_weight=False,
        verdict="clear",
        caution_note=None,
        minutes=3.0,
    )
    return Plan(
        warm_up=PlanSection(section="warm-up", entries=(entry,), minutes=3.0),
        main=PlanSection(section="main", entries=(entry,), minutes=14.0),
        cool_down=PlanSection(section="cool-down", entries=(entry,), minutes=3.0),
        requested_minutes=20,
        packed_minutes=20.0,
    )
