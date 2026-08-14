"""Test adapters for generation internals."""

from collections.abc import Iterable, Iterator, Sequence

from langchain_core.messages import BaseMessage

from app.generation._model import (
    CatalogExercise,
    GenerationMemberContext,
    Plan,
    PlanEntry,
    PlanSection,
    ResolvedMention,
)
from app.generation._trace import AgentTraceEvent
from app.generation.graph import run_generation_session as run_checkpointed_session
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
from app.safety import Verdict, WalkedPath


class FakeAnnotationLLM:
    def __init__(self, parts: Iterable[str | LLMProviderError]) -> None:
        self._parts = tuple(parts)
        self._calls: list[tuple[BaseMessage, ...]] = []
        self._parts_requested = 0

    @property
    def calls(self) -> tuple[tuple[BaseMessage, ...], ...]:
        return tuple(self._calls)

    @property
    def parts_requested(self) -> int:
        return self._parts_requested

    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[str]:
        self._calls.append(tuple(messages))
        for part in self._parts:
            self._parts_requested += 1
            if isinstance(part, LLMProviderError):
                raise part
            yield part


__all__ = [
    "AgentTraceEvent",
    "CatalogExercise",
    "FakeAnnotationLLM",
    "FakeLLM",
    "GenerationMemberContext",
    "Intent",
    "InterpretationFailure",
    "InterpretationFailureReason",
    "LLMProviderError",
    "Plan",
    "PlanEntry",
    "PlanSection",
    "ResolvedMention",
    "Verdict",
    "WalkedPath",
    "build_intent_llm",
    "interpret",
    "run_checkpointed_session",
]
