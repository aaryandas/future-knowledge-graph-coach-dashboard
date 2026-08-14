import json
from collections.abc import Iterable, Mapping
from time import perf_counter
from typing import Any

import pytest
from app.api.generate import TurnRunner, create_generate_router
from app.generation import GenerationTurn
from app.generation.testing import FakeLLM, run_checkpointed_session
from app.graph import get_member_injuries, ingest_kg1, ingest_kg2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "mbr_01HX9JORDAN"
BARBELL_EXERCISE_IDS = frozenset(
    {
        "0b3178cf-bf89-45a3-bfb0-27310ef6ef38",
        "00b26731-066f-4b69-96e8-3472fc6fbc09",
        "00c7ac93-153e-4b96-be56-b4ca6b465369",
    }
)


@pytest.fixture(scope="module")
def seeded_generation_graph() -> None:
    ingest_kg1()
    ingest_kg2()


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


def test_generate_stream_enforces_a_session_injury_without_persisting_it(
    seeded_generation_graph: None,
) -> None:
    before = get_member_injuries(MEMBER_ID)
    client = _generation_client(
        [
            {
                "focus": "full-body",
                "targets": [],
                "exclusions": [],
                "injuries": ["her left knee is bothering her"],
                "equipment": [],
            }
        ]
    )

    started_at = perf_counter()
    response = _generate(
        client,
        thread_id="knee-session",
        message_id="knee-message",
        text="Build a full-body plan; her left knee is bothering her.",
    )
    elapsed = perf_counter() - started_at

    assert response.status_code == 200
    parts = _data_parts(response.text)
    plan = parts["data-plan"]["data"]
    constraints = parts["data-constraints"]["data"]
    trace = parts["data-trace"]["data"]
    knee_resolution = next(
        event
        for event in trace
        if event["kind"] == "resolution" and event["purpose"] == "session injury"
    )
    assert knee_resolution["concept_id"] == "fkg:joint/knee"
    assert knee_resolution["enforced"] is True
    assert any(
        event["kind"] == "verdict"
        and event["status"] == "exclude"
        and event["walked_path"]["nodes"][0]["node_id"] == "fkg:joint/knee"
        and event["walked_path"]["edges"][0]["kind"] == "loads"
        for event in trace
    )
    assert constraints["session_injury_persistence_suggestions"] == [
        {
            "raw_text": "her left knee is bothering her",
            "concept_id": "fkg:joint/knee",
            "vocabulary": "Joint",
            "action": "persist session injury",
            "requires_confirmation": True,
            "message": (
                "The session injury is enforced for this session. "
                "Coach confirmation is required to add it to the member record."
            ),
        }
    ]
    assert get_member_injuries(MEMBER_ID) == before
    assert plan["requested_minutes"] == 30
    assert plan["packed_minutes"] <= plan["requested_minutes"]
    assert all(entry["verdict"] != "exclude" for entry in _plan_entries(plan))
    assert elapsed < 2.5


def test_generate_stream_drops_unavailable_equipment_and_is_byte_deterministic(
    seeded_generation_graph: None,
) -> None:
    intent = {
        "focus": "full-body",
        "targets": [],
        "exclusions": [],
        "injuries": [],
        "equipment": ["Dumbbell", "Kettlebell"],
    }
    client = _generation_client([intent, intent])

    first = _generate(
        client,
        thread_id="equipment-session-1",
        message_id="equipment-message-1",
        text="She has no barbell, only dumbbells and a kettlebell.",
    )
    second = _generate(
        client,
        thread_id="equipment-session-2",
        message_id="equipment-message-2",
        text="She has no barbell, only dumbbells and a kettlebell.",
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert _data_line(first.text, "data-plan") == _data_line(
        second.text,
        "data-plan",
    )
    parts = _data_parts(first.text)
    plan = parts["data-plan"]["data"]
    trace = parts["data-trace"]["data"]
    plan_entries = _plan_entries(plan)
    filtered_ids = {
        event["exercise_id"]
        for event in trace
        if event["kind"] == "packing"
        and event["action"] == "filtered"
        and event["reason"] == "Required equipment is unavailable."
    }

    assert filtered_ids
    assert BARBELL_EXERCISE_IDS.issubset(filtered_ids)
    assert filtered_ids.isdisjoint(entry["exercise_id"] for entry in plan_entries)
    assert any(
        "Dumbbell" in entry["name"] or "Kettlebell" in entry["name"]
        for entry in plan_entries
    )
    assert all(
        event["used"]
        and event["wasGeneratedBy"]
        and event["wasAttributedTo"] == "graph"
        for event in trace
    )


def _client(*, turn_runner: TurnRunner) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(create_generate_router(turn_runner=turn_runner))
    return TestClient(test_app)


def _generation_client(responses: Iterable[Mapping[str, object]]) -> TestClient:
    checkpointer = InMemorySaver()
    llm = FakeLLM(responses)

    def run_turn(
        member_id: str,
        message: str,
        window: int,
        thread_id: str,
        message_id: str,
    ) -> GenerationTurn:
        return run_checkpointed_session(
            member_id,
            message,
            window,
            thread_id,
            checkpointer=checkpointer,
            llm=llm,
            message_id=message_id,
        )

    return _client(turn_runner=run_turn)


def _generate(
    client: TestClient,
    *,
    thread_id: str,
    message_id: str,
    text: str,
) -> Response:
    return client.post(
        f"/api/members/{MEMBER_ID}/generate",
        json={
            "id": thread_id,
            "window": 30,
            "messages": [
                {
                    "id": message_id,
                    "role": "user",
                    "parts": [{"type": "text", "text": text}],
                }
            ],
        },
    )


def _data_parts(stream: str) -> dict[str, dict[str, Any]]:
    return {
        event["type"]: event
        for event in _events(stream)
        if event["type"].startswith("data-")
    }


def _data_line(stream: str, part_type: str) -> str:
    return next(
        line
        for line in stream.splitlines()
        if line.startswith("data: {")
        and json.loads(line.removeprefix("data: "))["type"] == part_type
    )


def _plan_entries(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for section in ("warm_up", "main", "cool_down")
        for entry in plan[section]["entries"]
    ]


def _events(stream: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: {")
    ]
