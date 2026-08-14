from dataclasses import FrozenInstanceError
from typing import cast

import pytest
from app.generation import (
    FakeLLM,
    Intent,
    InterpretationFailure,
    InterpretationFailureReason,
    LLMProviderError,
    interpret,
)
from app.generation.llm import _OpenRouterIntentLLM
from langchain_core.language_models import BaseChatModel


class _ProviderResponseShapeFake:
    def __init__(self, error_type: type[Exception]) -> None:
        self._error_type = error_type
        self.calls = 0

    def with_structured_output(
        self,
        _schema: object,
        *,
        method: str,
    ) -> "_ProviderResponseShapeFake":
        assert method == "json_schema"
        return self

    def invoke(self, _messages: list[object]) -> object:
        self.calls += 1
        raise self._error_type("invalid provider response shape")


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


@pytest.mark.parametrize("error_type", [ValueError, KeyError, TypeError])
def test_interpret_returns_visible_failure_for_provider_response_shape_error(
    error_type: type[Exception],
) -> None:
    provider = _ProviderResponseShapeFake(error_type)
    llm = _OpenRouterIntentLLM(cast("BaseChatModel", provider))

    result = interpret("Build a workout", llm=llm)

    assert result == InterpretationFailure(
        reason="provider-error",
        message="I could not interpret that coach message. Please rephrase it.",
        attempts=2,
    )
    assert provider.calls == 2


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
        intent.focus = "lower-body"  # ty: ignore[invalid-assignment]
