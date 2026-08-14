import pickle
from collections.abc import Iterable, Iterator, Sequence
from inspect import signature
from typing import Any, cast

import pytest
from app.generation import GenerationTurn, run_generation_session
from app.generation._trace import TraceEvent
from app.generation.graph import (
    run_generation_session as run_test_generation_session,
)
from app.generation.testing import (
    CatalogExercise,
    FakeLLM,
    GenerationMemberContext,
    LLMProviderError,
    ResolvedMention,
)
from app.safety import Verdict, WalkedPath
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "mbr_01HX9JORDAN"
THREAD_ID = "annotation-test-thread"


class FakeStructuredAnnotationLLM:
    def __init__(self, parts: Iterable[object | LLMProviderError]) -> None:
        self._parts = tuple(parts)
        self._calls: list[tuple[BaseMessage, ...]] = []
        self._parts_requested = 0

    @property
    def calls(self) -> tuple[tuple[BaseMessage, ...], ...]:
        return tuple(self._calls)

    @property
    def parts_requested(self) -> int:
        return self._parts_requested

    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[object]:
        self._calls.append(tuple(messages))
        for part in self._parts:
            self._parts_requested += 1
            if isinstance(part, LLMProviderError):
                raise part
            yield part


class _PickleSerializer:
    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        return "pickle", pickle.dumps(obj)

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        _, value = data
        return pickle.loads(value)


def _in_memory_generation_checkpointer() -> InMemorySaver:
    return InMemorySaver(serde=_PickleSerializer())


def test_generation_session_streams_structured_coaching_note_text_verbatim() -> None:
    annotation_llm = FakeStructuredAnnotationLLM(
        [
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-load",
                        "caution_text": " Keep the load light. ",
                    },
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "stop-on-pain",
                        "caution_text": "Stop if knee pain increases.",
                    },
                ]
            }
        ]
    )
    checkpointer = _in_memory_generation_checkpointer()
    turn = _run_turn(annotation_llm=annotation_llm, checkpointer=checkpointer)
    parts = iter(turn.coaching_note_parts)

    assert not any(event.kind == "agent" for event in turn.trace)
    assert next(parts) == " Keep the load light. "
    assert annotation_llm.parts_requested == 1
    assert tuple(parts) == ("Stop if knee pain increases.",)
    assert len(annotation_llm.calls) == 1
    system_prompt = str(annotation_llm.calls[0][0].content)
    plan_context = str(annotation_llm.calls[0][1].content)
    assert "structured caution form" in system_prompt
    assert "plan_item_id=ex-main" in plan_context
    assert _checkpoint_trace(checkpointer)[-1].kind == "agent"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "cautions": [
                {
                    "plan_item_id": "not-in-plan",
                    "tightening_kind": "reduce-load",
                    "caution_text": "Keep the load light.",
                }
            ]
        },
        {
            "cautions": [
                {
                    "plan_item_id": "ex-main",
                    "tightening_kind": "substitute",
                    "caution_text": "Use a different exercise.",
                }
            ]
        },
        {
            "cautions": [
                {
                    "plan_item_id": "ex-main",
                    "tightening_kind": "add-rest",
                    "caution_text": "Take more rest.",
                    "replacement_id": "ex-warm",
                }
            ]
        },
        {"cautions": [], "remove_plan_item_ids": ["ex-main"]},
    ],
)
def test_generation_session_drops_invalid_structured_coaching_note(
    payload: dict[str, object],
) -> None:
    turn = _run_turn(annotation_llm=FakeStructuredAnnotationLLM([payload]))

    assert tuple(turn.coaching_note_parts) == ()
    assert not any(event.kind == "agent" for event in turn.trace)


def test_generation_session_drops_the_whole_note_on_mid_note_provider_error() -> None:
    annotation_llm = FakeStructuredAnnotationLLM(
        [
            {
                "cautions": [
                    {
                        "plan_item_id": "ex-main",
                        "tightening_kind": "reduce-range",
                        "caution_text": "Use a smaller range.",
                    }
                ]
            },
            LLMProviderError("offline"),
        ]
    )
    checkpointer = _in_memory_generation_checkpointer()
    turn = _run_turn(annotation_llm=annotation_llm, checkpointer=checkpointer)

    assert tuple(turn.coaching_note_parts) == ()
    assert annotation_llm.parts_requested == 2
    assert not any(event.kind == "agent" for event in _checkpoint_trace(checkpointer))


def test_generation_session_without_an_api_key_has_no_coaching_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    turn = _run_turn()

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


def _run_turn(
    *,
    annotation_llm: FakeStructuredAnnotationLLM | None = None,
    checkpointer: InMemorySaver | None = None,
) -> GenerationTurn:
    return run_test_generation_session(
        MEMBER_ID,
        "Build a careful full-body workout.",
        20,
        THREAD_ID,
        checkpointer=checkpointer or _in_memory_generation_checkpointer(),
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
        message_id="annotation-user-message",
        catalog_reader=_catalog,
        member_context_reader=lambda member_id: GenerationMemberContext(
            equipment_ids=(),
            disliked_exercise_ids=(),
        ),
        verdict_evaluator=_clear_verdicts,
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
