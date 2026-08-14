from typing import Literal

import pytest
from app.generation.testing import (
    FakeAnnotationLLM,
    LLMProviderError,
    Plan,
    PlanEntry,
    PlanSection,
    annotate,
)


def test_annotation_streams_short_tighten_only_coaching_note_parts() -> None:
    llm = FakeAnnotationLLM(["Keep the load light.", " Stop if knee pain increases."])

    parts = tuple(annotate(_plan(), "Build a careful lower-body session.", llm=llm))

    assert parts == (
        "Keep the load light.",
        " Stop if knee pain increases.",
    )
    assert len(llm.calls) == 1
    system_prompt = str(llm.calls[0][0].content)
    plan_context = str(llm.calls[0][1].content)
    assert "Never remove, reduce, contradict" in system_prompt
    assert "verdict=caution" in plan_context
    assert "caution=Use a pain-free range." in plan_context


def test_annotation_provider_error_degrades_to_absent_notes() -> None:
    llm = FakeAnnotationLLM(
        ["This partial note must not escape.", LLMProviderError("offline")]
    )

    assert tuple(annotate(_plan(), "Build a workout.", llm=llm)) == ()
    assert len(llm.calls) == 1


def test_annotation_without_an_api_key_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    assert tuple(annotate(_plan(), "Build a workout.")) == ()


def _plan() -> Plan:
    warm_up_entry = _entry("ex-warm", "March", verdict="clear", caution_note=None)
    main_entry = _entry(
        "ex-main",
        "Box Squat",
        verdict="caution",
        caution_note="Use a pain-free range.",
    )
    cool_down_entry = _entry(
        "ex-cool",
        "Breathing",
        verdict="clear",
        caution_note=None,
    )
    return Plan(
        warm_up=PlanSection(
            section="warm-up",
            entries=(warm_up_entry,),
            minutes=3.0,
        ),
        main=PlanSection(section="main", entries=(main_entry,), minutes=14.0),
        cool_down=PlanSection(
            section="cool-down",
            entries=(cool_down_entry,),
            minutes=3.0,
        ),
        requested_minutes=20,
        packed_minutes=20.0,
    )


def _entry(
    exercise_id: str,
    name: str,
    *,
    verdict: Literal["exclude", "caution", "clear"],
    caution_note: str | None,
) -> PlanEntry:
    return PlanEntry(
        exercise_id=exercise_id,
        name=name,
        sets=2,
        reps=8,
        hold_minutes=None,
        rest_minutes=0.5,
        per_side=False,
        supports_weight=False,
        verdict=verdict,
        caution_note=caution_note,
        minutes=3.0,
    )
