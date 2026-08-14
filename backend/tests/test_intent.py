from dataclasses import FrozenInstanceError

import httpx
import pytest
from app.generation.testing import (
    FakeLLM,
    Intent,
    InterpretationFailure,
    InterpretationFailureReason,
    LLMProviderError,
    build_intent_llm,
    interpret,
)
from langchain_openai import ChatOpenAI


def test_interpret_returns_raw_mentions_without_concept_ids() -> None:
    llm = FakeLLM(
        [
            {
                "focus": "lower-body",
                "targets": ["my Quads"],
                "exclusions": ["sissy squats"],
                "injuries": ["her left knee is bothering her"],
                "equipment": ["dumbbells", "a kettlebell"],
            }
        ]
    )

    result = interpret(
        "30 min lower body at home; avoid sissy squats because her left knee hurts",
        llm=llm,
    )

    assert result == Intent(
        focus="lower-body",
        targets=("my Quads",),
        exclusions=("sissy squats",),
        injuries=("her left knee is bothering her",),
        equipment=("dumbbells", "a kettlebell"),
    )
    assert len(llm.calls) == 1


def test_interpret_uses_the_same_edge_for_an_adjustment_delta() -> None:
    llm = FakeLLM(
        [
            {
                "focus": None,
                "targets": [],
                "exclusions": ["deadlifts"],
                "injuries": [],
                "equipment": [],
            }
        ]
    )

    result = interpret("Exclude deadlifts", llm=llm)

    assert result == Intent(
        focus=None,
        targets=(),
        exclusions=("deadlifts",),
        injuries=(),
        equipment=(),
    )


def test_interpret_retries_one_provider_error() -> None:
    llm = FakeLLM(
        [
            LLMProviderError("offline"),
            {
                "focus": "full-body",
                "targets": [],
                "exclusions": [],
                "injuries": [],
                "equipment": [],
            },
        ]
    )

    result = interpret("Full body", llm=llm)

    assert isinstance(result, Intent)
    assert len(llm.calls) == 2


def test_interpret_returns_visible_failure_for_empty_provider_choices() -> None:
    requests: list[httpx.Request] = []

    def empty_choices(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": []})

    with httpx.Client(transport=httpx.MockTransport(empty_choices)) as http_client:
        chat_model = ChatOpenAI(
            api_key="test",
            base_url="https://openrouter.test/api/v1",
            model="test-model",
            max_retries=0,
            http_client=http_client,
        )
        llm = build_intent_llm(chat_model)
        assert llm is not None
        result = interpret("Build a workout", llm=llm)

    assert result == InterpretationFailure(
        reason="provider-error",
        message="I could not interpret that coach message. Please rephrase it.",
        attempts=2,
    )
    assert len(requests) == 2


@pytest.mark.parametrize(
    ("responses", "reason"),
    [
        (
            [LLMProviderError("offline"), LLMProviderError("still offline")],
            "provider-error",
        ),
        (
            [
                {"focus": "strength"},
                {"focus": "strength"},
            ],
            "invalid-output",
        ),
    ],
)
def test_interpret_returns_visible_failure_after_one_retry(
    responses: list[dict[str, object] | LLMProviderError],
    reason: InterpretationFailureReason,
) -> None:
    llm = FakeLLM(responses)

    result = interpret("Build a workout", llm=llm)

    assert result == InterpretationFailure(
        reason=reason,
        message="I could not interpret that coach message. Please rephrase it.",
        attempts=2,
    )
    assert len(llm.calls) == 2


def test_interpret_returns_visible_failure_without_an_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = interpret("Full body")

    assert result == InterpretationFailure(
        reason="llm-unavailable",
        message="Coach message interpretation is unavailable.",
        attempts=0,
    )


def test_intent_is_frozen() -> None:
    intent = Intent(
        focus="full-body",
        targets=(),
        exclusions=(),
        injuries=(),
        equipment=(),
    )

    with pytest.raises(FrozenInstanceError):
        intent.focus = "lower-body"  # ty: ignore[invalid-assignment]  # Verify immutability.
