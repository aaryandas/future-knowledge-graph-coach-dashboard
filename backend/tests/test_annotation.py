from collections.abc import Iterator
from contextlib import contextmanager
from inspect import signature

import pytest
from app.generation import GenerationTurn, run_generation_session
from app.generation.persistence import open_postgres_checkpointer
from app.generation.testing import (
    CatalogExercise,
    CheckpointerFactory,
    FakeAnnotationLLM,
    FakeLLM,
    GenerationMemberContext,
    LLMProviderError,
    ResolvedMention,
    Verdict,
    WalkedPath,
    generation_test_adapters,
)

MEMBER_ID = "mbr_01HX9JORDAN"
THREAD_ID = "annotation-test-thread"


def test_generation_session_buffers_complete_form_before_emitting_templates() -> None:
    annotation_llm = FakeAnnotationLLM(
        [
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-load",
                    }
                ]
            },
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-load",
                    },
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "stop-on-pain",
                    },
                ]
            },
        ]
    )

    with _run_turn(annotation_llm=annotation_llm) as turn:
        parts = iter(turn.coaching_note_parts)

        assert not any(event.kind == "agent" for event in turn.trace)
        assert next(parts) == "Reduce the load on Box Squat."
        assert annotation_llm.parts_requested == 2
        assert tuple(parts) == ("Stop Box Squat if you feel pain.",)
        assert len(annotation_llm.calls) == 1
        system_prompt = str(annotation_llm.calls[0][0].content)
        plan_context = str(annotation_llm.calls[0][1].content)
        assert "structured caution form" in system_prompt
        assert "caution_text" not in system_prompt
        assert "plan_item_id=ex-main" in plan_context
        replayed = _run_next_turn()

        assert [event.used for event in replayed.trace if event.kind == "agent"] == [
            ("ex-main",),
            ("ex-main",),
        ]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "cautions": [
                    {
                        "plan_item_id": "not-in-plan",
                        "tightening_kind": "reduce-load",
                    }
                ]
            },
            (),
        ),
        (
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "substitute",
                    }
                ]
            },
            (),
        ),
        (
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-load",
                        "caution_text": "Use deadlifts instead.",
                    }
                ]
            },
            (),
        ),
        (
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-range",
                        "caution_text": "Avoid the pain-free range.",
                    }
                ]
            },
            (),
        ),
        (
            {
                "cautions": [
                    {
                        "plan_item_id": "not-in-plan",
                        "tightening_kind": "reduce-load",
                    },
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "stop-on-pain",
                    },
                ]
            },
            ("Stop Box Squat if you feel pain.",),
        ),
        ({"cautions": [], "remove_plan_item_ids": ["ex-main"]}, ()),
    ],
)
def test_generation_session_only_emits_closed_pair_templates(
    payload: dict[str, object],
    expected: tuple[str, ...],
) -> None:
    with _run_turn(annotation_llm=FakeAnnotationLLM([payload])) as turn:
        assert tuple(turn.coaching_note_parts) == expected


@pytest.mark.parametrize(
    ("tightening_kind", "expected"),
    [
        ("reduce-load", "Reduce the load on Box Squat."),
        ("reduce-range", "Reduce the range of motion for Box Squat."),
        ("stop-on-pain", "Stop Box Squat if you feel pain."),
        ("add-rest", "Add more rest after Box Squat."),
    ],
)
def test_generation_session_renders_each_tightening_kind_from_a_fixed_template(
    tightening_kind: str,
    expected: str,
) -> None:
    annotation_llm = FakeAnnotationLLM(
        [
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": tightening_kind,
                    }
                ]
            }
        ]
    )

    with _run_turn(annotation_llm=annotation_llm) as turn:
        assert tuple(turn.coaching_note_parts) == (expected,)


def test_generation_session_drops_the_whole_note_on_mid_note_provider_error() -> None:
    annotation_llm = FakeAnnotationLLM(
        [
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-load",
                    }
                ]
            },
            LLMProviderError("offline"),
        ]
    )

    with _run_turn(annotation_llm=annotation_llm) as turn:
        assert tuple(turn.coaching_note_parts) == ()
        assert annotation_llm.parts_requested == 2
        replayed = _run_next_turn()

        assert not any(event.kind == "agent" for event in replayed.trace)


def test_generation_service_replays_annotation_trace_events_by_thread() -> None:
    with _annotation_test_adapters(
        intent_count=3,
        annotation_llm=_two_note_annotation_llm(),
    ):
        first = run_generation_session(
            MEMBER_ID,
            "Build a careful full-body workout.",
            20,
            "annotation-replay-thread",
            "annotation-replay-message-1",
        )

        assert not any(event.kind == "agent" for event in first.trace)
        assert tuple(first.coaching_note_parts) == (
            "Add more rest after March.",
            "Reduce the load on Box Squat.",
        )

        replayed = run_generation_session(
            MEMBER_ID,
            "Make one adjustment.",
            20,
            "annotation-replay-thread",
            "annotation-replay-message-2",
        )
        isolated = run_generation_session(
            MEMBER_ID,
            "Build another workout.",
            20,
            "annotation-isolated-thread",
            "annotation-isolated-message-1",
        )

    assert [event.used for event in replayed.trace if event.kind == "agent"] == [
        ("ex-warm",),
        ("ex-main",),
    ]
    assert not any(event.kind == "agent" for event in isolated.trace)


def test_generation_service_does_not_replay_a_failed_note_from_postgres() -> None:
    thread_id = "annotation-postgres-failed-note-thread"
    _delete_postgres_threads(thread_id)
    annotation_llm = FakeAnnotationLLM(
        [
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-load",
                    }
                ]
            },
            LLMProviderError("offline"),
        ]
    )

    try:
        with _annotation_test_adapters(
            intent_count=2,
            annotation_llm=annotation_llm,
            checkpointer_factory=open_postgres_checkpointer,
        ):
            first = run_generation_session(
                MEMBER_ID,
                "Build a careful full-body workout.",
                20,
                thread_id,
                "annotation-postgres-failed-message-1",
            )
            assert tuple(first.coaching_note_parts) == ()

            replayed = run_generation_session(
                MEMBER_ID,
                "Make one adjustment.",
                20,
                thread_id,
                "annotation-postgres-failed-message-2",
            )

        assert not any(event.kind == "agent" for event in replayed.trace)
    finally:
        _delete_postgres_threads(thread_id)


def test_generation_session_without_an_api_key_has_no_coaching_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with _run_turn() as turn:
        assert tuple(turn.coaching_note_parts) == ()
        assert not any(event.kind == "agent" for event in turn.trace)


def test_generation_service_facade_exposes_only_session_inputs() -> None:
    assert tuple(signature(run_generation_session).parameters) == (
        "member_id",
        "coach_message",
        "window",
        "thread_id",
        "message_id",
    )


@contextmanager
def _run_turn(
    *,
    annotation_llm: FakeAnnotationLLM | None = None,
) -> Iterator[GenerationTurn]:
    with _annotation_test_adapters(
        intent_count=2,
        annotation_llm=annotation_llm,
    ):
        yield run_generation_session(
            MEMBER_ID,
            "Build a careful full-body workout.",
            20,
            THREAD_ID,
            "annotation-user-message",
        )


def _run_next_turn(
    *,
    thread_id: str = THREAD_ID,
) -> GenerationTurn:
    return run_generation_session(
        MEMBER_ID,
        "Make one adjustment.",
        20,
        thread_id,
        "annotation-next-user-message",
    )


@contextmanager
def _annotation_test_adapters(
    *,
    intent_count: int,
    annotation_llm: FakeAnnotationLLM | None,
    checkpointer_factory: CheckpointerFactory | None = None,
) -> Iterator[None]:
    with generation_test_adapters(
        llm=FakeLLM([_full_body_intent()] * intent_count),
        annotation_llm=annotation_llm,
        catalog_reader=_catalog,
        member_context_reader=lambda member_id: GenerationMemberContext(
            equipment_ids=(),
            disliked_exercise_ids=(),
        ),
        verdict_evaluator=_clear_verdicts,
        checkpointer_factory=checkpointer_factory,
    ):
        yield


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


def _catalog() -> tuple[CatalogExercise, ...]:
    return (
        _exercise("ex-warm", "March", "mobility - dynamic"),
        _exercise("ex-main", "Box Squat", "lower squat"),
        _exercise("ex-cool", "Breathing", "regen"),
    )


def _exercise(
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
