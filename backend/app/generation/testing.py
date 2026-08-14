"""Test adapters for the checkpointed generation session."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from app.generation import service as _generation_service
from app.generation._catalog import (
    read_catalog_exercises,
    read_generation_member_context,
)
from app.generation._model import (
    CatalogExercise,
    ConstraintSet,
    GenerationMemberContext,
    Plan,
    PlanEntry,
    PlanSection,
    ResolvedIntent,
    ResolvedMention,
)
from app.generation._safety import evaluate_generation_safety
from app.generation.graph import (
    CatalogReader,
    GenerationTurn,
    MemberContextReader,
    VerdictEvaluator,
)
from app.generation.graph import (
    run_generation_session as _run_checkpointed_generation_session,
)
from app.generation.intent import (
    Intent,
    InterpretationFailure,
    InterpretationFailureReason,
    interpret,
)
from app.generation.llm import (
    FakeLLM,
    IntentLLM,
    LLMProviderError,
    build_intent_llm,
)
from app.resolver import Resolution
from app.safety import Verdict, WalkedPath


@contextmanager
def generation_test_adapters(
    *,
    llm: IntentLLM,
    catalog_reader: CatalogReader,
    member_context_reader: MemberContextReader,
    verdict_evaluator: VerdictEvaluator,
) -> Iterator[None]:
    checkpointer = InMemorySaver()
    test_llm = llm
    test_catalog_reader = catalog_reader
    test_member_context_reader = member_context_reader
    test_verdict_evaluator = verdict_evaluator
    stored_checkpointer_factory = _generation_service.open_postgres_checkpointer
    stored_runner = _generation_service.run_checkpointed_session

    @contextmanager
    def open_in_memory_checkpointer(
        database_url: str | None = None,
    ) -> Iterator[BaseCheckpointSaver[Any]]:
        del database_url
        yield checkpointer

    def run_with_test_adapters(
        member_id: str,
        coach_message: str,
        window: int,
        thread_id: str,
        *,
        checkpointer: BaseCheckpointSaver[Any],
        llm: IntentLLM | None = None,
        message_id: str | None = None,
        catalog_reader: CatalogReader = read_catalog_exercises,
        member_context_reader: MemberContextReader = read_generation_member_context,
        verdict_evaluator: VerdictEvaluator = evaluate_generation_safety,
    ) -> GenerationTurn:
        del llm, catalog_reader, member_context_reader, verdict_evaluator
        return _run_checkpointed_generation_session(
            member_id,
            coach_message,
            window,
            thread_id,
            checkpointer=checkpointer,
            llm=test_llm,
            message_id=message_id,
            catalog_reader=test_catalog_reader,
            member_context_reader=test_member_context_reader,
            verdict_evaluator=test_verdict_evaluator,
        )

    _generation_service.open_postgres_checkpointer = open_in_memory_checkpointer
    # ty cannot prove that a local replacement matches the imported function.
    _generation_service.run_checkpointed_session = run_with_test_adapters  # ty: ignore[invalid-assignment]
    try:
        yield
    finally:
        _generation_service.open_postgres_checkpointer = stored_checkpointer_factory
        _generation_service.run_checkpointed_session = stored_runner


__all__ = [
    "CatalogExercise",
    "ConstraintSet",
    "FakeLLM",
    "GenerationMemberContext",
    "InMemorySaver",
    "Intent",
    "InterpretationFailure",
    "InterpretationFailureReason",
    "LLMProviderError",
    "Plan",
    "PlanEntry",
    "PlanSection",
    "Resolution",
    "ResolvedIntent",
    "ResolvedMention",
    "Verdict",
    "WalkedPath",
    "build_intent_llm",
    "generation_test_adapters",
    "interpret",
]
