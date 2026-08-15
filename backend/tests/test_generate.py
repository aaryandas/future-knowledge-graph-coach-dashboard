import json
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from time import perf_counter
from typing import Any

import pytest
from app.api.generate import TurnRunner, create_generate_router
from app.generation import GenerationTurn, run_generation_session
from app.generation.persistence import open_postgres_checkpointer
from app.generation.testing import (
    AgentTraceEvent,
    CatalogExercise,
    ConstraintSet,
    FakeAnnotationLLM,
    FakeLLM,
    GenerationMemberContext,
    Plan,
    PlanEntry,
    PlanSection,
    Resolution,
    ResolvedIntent,
    ResolvedMention,
    Verdict,
    WalkedPath,
    generation_test_adapters,
)
from app.graph import get_member_injuries, ingest_kg1, ingest_kg2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response

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


def test_coaching_note_text_parts_stream_after_plan_and_trace() -> None:
    data_parts_built: list[bool] = []

    class ObservedTrace(tuple[AgentTraceEvent, ...]):
        def __iter__(self):
            data_parts_built.append(True)
            return super().__iter__()

    trace = ObservedTrace()

    def coaching_note_parts():
        assert data_parts_built
        yield "Keep the load light."
        yield " Stop if knee pain increases."

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
            trace=trace,
            resolved_intent=None,
            failure=None,
            text="Session ready.",
            coaching_note_parts=coaching_note_parts(),
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
    assert response.status_code == 200
    assert [event["type"] for event in events] == [
        "start",
        "start-step",
        "data-plan",
        "data-trace",
        "data-constraints",
        "text-start",
        "text-delta",
        "text-end",
        "text-start",
        "text-delta",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
    ]
    trace_data = next(event for event in events if event["type"] == "data-trace")[
        "data"
    ]
    assert isinstance(trace_data, list)
    assert trace_data == []
    assert [
        event["delta"]
        for event in events
        if event.get("id") == "user-1-assistant-annotation"
        and event["type"] == "text-delta"
    ] == ["Keep the load light.", " Stop if knee pain increases."]


def test_generation_service_replays_annotation_trace_events_after_postgres_restart() -> (
    None
):
    replay_thread_id = "annotation-postgres-replay-thread"
    isolated_thread_id = "annotation-postgres-isolated-thread"
    _delete_postgres_threads(replay_thread_id, isolated_thread_id)

    try:
        with _annotation_generation_client(
            intent_count=3,
            annotation_llm=_two_note_annotation_llm(),
        ) as client:
            first = _generate_annotation_stream(
                client,
                thread_id=replay_thread_id,
                message_id="annotation-postgres-message-1",
                text="Build a careful full-body workout.",
            )
            replayed = _generate_annotation_stream(
                client,
                thread_id=replay_thread_id,
                message_id="annotation-postgres-message-2",
                text="Make one adjustment.",
            )
            isolated = _generate_annotation_stream(
                client,
                thread_id=isolated_thread_id,
                message_id="annotation-postgres-isolated-message-1",
                text="Build another workout.",
            )

        packing_trace = _expected_packing_trace()
        prior_annotations = _expected_annotation_trace()
        assert _trace_data(first) == packing_trace
        assert _annotation_text_deltas(first) == [
            "Add more rest after March.",
            "Reduce the load on Box Squat.",
        ]
        assert _trace_data(replayed) == [
            *packing_trace,
            *prior_annotations,
            *packing_trace,
        ]
        assert _trace_data(isolated) == packing_trace
    finally:
        _delete_postgres_threads(replay_thread_id, isolated_thread_id)


def test_generate_stream_enforces_a_session_injury_without_persisting_it(
    seeded_generation_graph: None,
) -> None:
    before = get_member_injuries(MEMBER_ID)
    with _generation_client(
        [
            {
                "focus": "full-body",
                "targets": [],
                "exclusions": [],
                "injuries": ["her left knee is bothering her"],
                "equipment": [],
            }
        ]
    ) as client:
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
    with _generation_client([intent, intent]) as client:
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


@contextmanager
def _generation_client(
    responses: Iterable[Mapping[str, object]],
) -> Iterator[TestClient]:
    with generation_test_adapters(llm=FakeLLM(responses)):
        yield _client(turn_runner=run_generation_session)


@contextmanager
def _annotation_generation_client(
    *,
    intent_count: int,
    annotation_llm: FakeAnnotationLLM,
) -> Iterator[TestClient]:
    with generation_test_adapters(
        llm=FakeLLM([_full_body_intent()] * intent_count),
        annotation_llm=annotation_llm,
        catalog_reader=_annotation_catalog,
        member_context_reader=lambda member_id: GenerationMemberContext(
            equipment_ids=(),
            disliked_exercise_ids=(),
        ),
        verdict_evaluator=_clear_verdicts,
        checkpointer_factory=open_postgres_checkpointer,
    ):
        yield _client(turn_runner=run_generation_session)


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


def _generate_annotation_stream(
    client: TestClient,
    *,
    thread_id: str,
    message_id: str,
    text: str,
) -> str:
    response = client.post(
        f"/api/members/{MEMBER_ID}/generate",
        json={
            "id": thread_id,
            "window": 20,
            "messages": [
                {
                    "id": message_id,
                    "role": "user",
                    "parts": [{"type": "text", "text": text}],
                }
            ],
        },
    )
    assert response.status_code == 200
    return response.text


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


def _trace_data(stream: str) -> list[dict[str, Any]]:
    trace = next(event for event in _events(stream) if event["type"] == "data-trace")[
        "data"
    ]
    assert isinstance(trace, list)
    return trace


def _annotation_text_deltas(stream: str) -> list[object]:
    return [
        event["delta"]
        for event in _events(stream)
        if event["type"] == "text-delta" and str(event["id"]).endswith("-annotation")
    ]


def _expected_packing_trace() -> list[dict[str, object]]:
    return [
        {
            "kind": "packing",
            "action": "selected",
            "section": section,
            "exercise_id": exercise_id,
            "reason": (
                "score 2: goal match 0 + coverage gain 1 + priority tier 1 "
                "- caution 0 - dislike 0."
            ),
            "used": [exercise_id],
            "score": 2,
            "wasGeneratedBy": "pack",
            "wasAttributedTo": "graph",
        }
        for section, exercise_id in (
            ("warm-up", "ex-warm"),
            ("main", "ex-main"),
            ("cool-down", "ex-cool"),
        )
    ]


def _expected_annotation_trace() -> list[dict[str, object]]:
    return [
        {
            "kind": "agent",
            "action": "annotation",
            "reason": "Added a structurally validated tighten-only coaching note.",
            "used": [exercise_id],
            "wasGeneratedBy": "annotate",
            "wasAttributedTo": "agent",
        }
        for exercise_id in ("ex-warm", "ex-main")
    ]


def _full_body_intent() -> dict[str, object]:
    return {
        "focus": "full-body",
        "targets": [],
        "exclusions": [],
        "injuries": [],
        "equipment": [],
    }


def _two_note_annotation_llm() -> FakeAnnotationLLM:
    return FakeAnnotationLLM(
        [
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-warm",
                        "tightening_kind": "add-rest",
                    },
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-load",
                    },
                ]
            }
        ]
    )


def _delete_postgres_threads(*thread_ids: str) -> None:
    with open_postgres_checkpointer() as checkpointer:
        for thread_id in thread_ids:
            checkpointer.delete_thread(thread_id)


def _annotation_catalog() -> tuple[CatalogExercise, ...]:
    return (
        _annotation_exercise("ex-warm", "March", "mobility - dynamic"),
        _annotation_exercise("ex-main", "Box Squat", "lower squat"),
        _annotation_exercise("ex-cool", "Breathing", "regen"),
    )


def _annotation_exercise(
    exercise_id: str,
    name: str,
    movement_pattern: str,
) -> CatalogExercise:
    return CatalogExercise(
        exercise_id=exercise_id,
        name=name,
        movement_patterns=(movement_pattern,),
        movement_pattern_ids=(f"pattern-{exercise_id}",),
        muscle_groups=("full body",),
        muscle_group_ids=("muscle-full-body",),
        joint_ids=(),
        equipment_ids=(),
        priority_tier=1,
        is_reps=True,
        is_duration=False,
        supports_weight=False,
        estimated_rep_duration=0.1,
        is_bilateral=False,
        side=None,
        bilateral_pair_id=None,
    )


def _clear_verdicts(
    member_id: str,
    exercise_ids: tuple[str, ...],
    session_injuries: tuple[ResolvedMention, ...],
) -> tuple[Verdict, ...]:
    return tuple(
        Verdict(
            exercise_id=exercise_id,
            status="clear",
            walked_path=WalkedPath(nodes=(), edges=()),
            decisions=(),
            trace=(),
        )
        for exercise_id in exercise_ids
    )


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
