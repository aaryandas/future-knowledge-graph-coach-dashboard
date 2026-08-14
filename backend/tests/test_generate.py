import json

from app.api.generate import TurnRunner, create_generate_router
from app.generation import GenerationTurn
from app.generation.testing import (
    ConstraintSet,
    Plan,
    PlanEntry,
    PlanSection,
    Resolution,
    ResolvedIntent,
    ResolvedMention,
)
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
            plan=_plan(),
            trace=(),
            resolved_intent=_resolved_intent(),
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
    events = _events(response.text)
    assert [event["type"] for event in events] == [
        "start",
        "start-step",
        "data-plan",
        "data-trace",
        "data-constraints",
        "text-start",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
    ]
    data_parts = [event for event in events if str(event["type"]).startswith("data-")]
    assert [(part["type"], part["id"]) for part in data_parts] == [
        ("data-plan", "generation-plan"),
        ("data-trace", "generation-trace"),
        ("data-constraints", "generation-constraints"),
    ]
    constraints_part = next(
        part for part in data_parts if part["type"] == "data-constraints"
    )
    constraints_data = constraints_part["data"]
    assert isinstance(constraints_data, dict)
    suggestions = constraints_data["session_injury_persistence_suggestions"]
    assert isinstance(suggestions, list)
    suggestion = suggestions[0]
    assert isinstance(suggestion, dict)
    assert suggestion["requires_confirmation"] is True


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


def _resolved_intent() -> ResolvedIntent:
    knee = ResolvedMention(
        purpose="session injury",
        vocabulary="Joint",
        resolution=Resolution(
            concept_id="fkg:joint/knee",
            confidence=1.0,
            pass_="exact",
            candidates=(),
            raw_text="knee",
            modifiers=(),
        ),
        enforced=True,
    )
    return ResolvedIntent(
        targets=(),
        constraints=ConstraintSet(
            exclusions=(),
            session_injuries=(knee,),
            equipment_override=None,
        ),
    )
