"""Test adapters for generation internals."""

from app.generation._model import Plan, PlanEntry, PlanSection
from app.generation.annotation import (
    FakeAnnotationLLM,
    annotate,
    build_annotation_llm,
)
from app.generation.intent import (
    Intent,
    InterpretationFailure,
    InterpretationFailureReason,
    interpret,
)
from app.generation.llm import (
    FakeLLM,
    LLMProviderError,
    build_intent_llm,
)

__all__ = [
    "FakeAnnotationLLM",
    "FakeLLM",
    "Intent",
    "InterpretationFailure",
    "InterpretationFailureReason",
    "LLMProviderError",
    "Plan",
    "PlanEntry",
    "PlanSection",
    "annotate",
    "build_annotation_llm",
    "build_intent_llm",
    "interpret",
]
