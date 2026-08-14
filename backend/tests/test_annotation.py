from collections.abc import Iterator
from contextlib import contextmanager
from inspect import signature
from typing import cast

import pytest
from app.generation import GenerationTurn, run_generation_session
from app.generation.testing import (
    CatalogExercise,
    FakeAnnotationLLM,
    FakeLLM,
    GenerationMemberContext,
    InMemorySaver,
    LLMProviderError,
    ResolvedMention,
    TraceEvent,
    Verdict,
    WalkedPath,
    generation_test_adapters,
)

MEMBER_ID = "mbr_01HX9JORDAN"
THREAD_ID = "annotation-test-thread"


def test_generation_session_streams_each_template_as_its_pair_validates() -> None:
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

    with _run_turn(annotation_llm=annotation_llm) as (turn, checkpointer):
        parts = iter(turn.coaching_note_parts)

        assert not any(event.kind == "agent" for event in turn.trace)
        assert next(parts) == "Reduce the load on Box Squat."
        assert annotation_llm.parts_requested == 1
        assert tuple(parts) == ("Stop Box Squat if you feel pain.",)
        assert len(annotation_llm.calls) == 1
        system_prompt = str(annotation_llm.calls[0][0].content)
        plan_context = str(annotation_llm.calls[0][1].content)
        assert "structured caution form" in system_prompt
        assert "caution_text" not in system_prompt
        assert "plan_item_id=ex-main" in plan_context
        assert [event.kind for event in _checkpoint_trace(checkpointer)[-2:]] == [
            "agent",
            "agent",
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
    with _run_turn(annotation_llm=FakeAnnotationLLM([payload])) as (turn, _):
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

    with _run_turn(annotation_llm=annotation_llm) as (turn, _):
        assert tuple(turn.coaching_note_parts) == (expected,)


def test_generation_session_drops_the_whole_note_on_mid_note_provider_error() -> None:
    annotation_llm = FakeAnnotationLLM(
        [
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                    }
                ]
            },
            LLMProviderError("offline"),
        ]
    )

    with _run_turn(annotation_llm=annotation_llm) as (turn, checkpointer):
        assert tuple(turn.coaching_note_parts) == ()
        assert annotation_llm.parts_requested == 2
        assert not any(
            event.kind == "agent" for event in _checkpoint_trace(checkpointer)
        )


def test_generation_session_without_an_api_key_has_no_coaching_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with _run_turn() as (turn, _):
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
) -> Iterator[tuple[GenerationTurn, InMemorySaver]]:
    with generation_test_adapters(
        llm=FakeLLM(
            [
                {
                    "focus": "full-body",
                    "targets": [],
                    "exclusions": [],
                    "injuries": [],
                    "equipment": [],
                }
            ]
        ),
        annotation_llm=annotation_llm,
        catalog_reader=_catalog,
        member_context_reader=lambda member_id: GenerationMemberContext(
            equipment_ids=(),
            disliked_exercise_ids=(),
        ),
        verdict_evaluator=_clear_verdicts,
    ) as checkpointer:
        yield (
            run_generation_session(
                MEMBER_ID,
                "Build a careful full-body workout.",
                20,
                THREAD_ID,
                "annotation-user-message",
            ),
            checkpointer,
        )


def _checkpoint_trace(checkpointer: InMemorySaver) -> tuple[TraceEvent, ...]:
    checkpoint = checkpointer.get({"configurable": {"thread_id": THREAD_ID}})
    assert checkpoint is not None
    channel_values = checkpoint["channel_values"]
    assert isinstance(channel_values, dict)
    trace = channel_values["trace"]
    assert isinstance(trace, tuple)
    return cast("tuple[TraceEvent, ...]", trace)


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
