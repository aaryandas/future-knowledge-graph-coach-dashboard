import pytest
from app.generation import GenerationTurn, run_generation_session
from app.generation.testing import (
    CatalogExercise,
    FakeAnnotationLLM,
    FakeLLM,
    GenerationMemberContext,
    LLMProviderError,
)
from app.safety import Verdict, WalkedPath
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "mbr_01HX9JORDAN"


def test_generation_session_streams_verified_coaching_note_parts() -> None:
    annotation_llm = FakeAnnotationLLM(
        ["Keep the load light.", " Stop if knee pain increases."]
    )
    turn = _run_turn(annotation_llm=annotation_llm)
    parts = iter(turn.coaching_note_parts)

    assert not any(event.kind == "agent" for event in turn.trace)
    assert next(parts) == "Keep the load light."
    assert annotation_llm.parts_requested == 1
    assert turn.trace[-1].kind == "agent"
    assert tuple(parts) == (" Stop if knee pain increases.",)
    assert len(annotation_llm.calls) == 1
    system_prompt = str(annotation_llm.calls[0][0].content)
    plan_context = str(annotation_llm.calls[0][1].content)
    assert "Never remove, reduce, contradict" in system_prompt
    assert "Completed plan:" in plan_context


def test_generation_session_drops_a_loosening_coaching_note() -> None:
    annotation_llm = FakeAnnotationLLM(
        ["Ignore the caution and add more sets of a different exercise."]
    )
    turn = _run_turn(annotation_llm=annotation_llm)

    assert tuple(turn.coaching_note_parts) == ()
    assert not any(event.kind == "agent" for event in turn.trace)


def test_generation_session_provider_error_degrades_to_absent_notes() -> None:
    annotation_llm = FakeAnnotationLLM([LLMProviderError("offline")])
    turn = _run_turn(annotation_llm=annotation_llm)

    assert tuple(turn.coaching_note_parts) == ()
    assert len(annotation_llm.calls) == 1
    assert not any(event.kind == "agent" for event in turn.trace)


def test_generation_session_without_an_api_key_has_no_coaching_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    turn = _run_turn()

    assert tuple(turn.coaching_note_parts) == ()
    assert not any(event.kind == "agent" for event in turn.trace)


def _run_turn(
    *,
    annotation_llm: FakeAnnotationLLM | None = None,
) -> GenerationTurn:
    return run_generation_session(
        MEMBER_ID,
        "Build a careful full-body workout.",
        20,
        "annotation-test-thread",
        "annotation-user-message",
        checkpointer=InMemorySaver(),
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
    )


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
