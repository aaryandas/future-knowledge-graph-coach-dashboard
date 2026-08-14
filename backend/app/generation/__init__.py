"""Run or adjust a persisted generation session."""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.generation._catalog import (
    read_catalog_exercises,
    read_generation_member_context,
)
from app.generation._safety import evaluate_generation_safety
from app.generation.graph import (
    CatalogReader,
    GenerationTurn,
    MemberContextReader,
    VerdictEvaluator,
)
from app.generation.graph import (
    run_generation_session as run_checkpointed_generation_session,
)
from app.generation.llm import IntentLLM
from app.generation.service import (
    run_generation_session as run_persisted_generation_session,
)


def run_generation_session(
    member_id: str,
    coach_message: str,
    window: int,
    thread_id: str,
    message_id: str | None = None,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    llm: IntentLLM | None = None,
    catalog_reader: CatalogReader = read_catalog_exercises,
    member_context_reader: MemberContextReader = read_generation_member_context,
    verdict_evaluator: VerdictEvaluator = evaluate_generation_safety,
) -> GenerationTurn:
    if checkpointer is None:
        if message_id is None:
            raise ValueError("A generation message id is required for persistence.")
        return run_persisted_generation_session(
            member_id,
            coach_message,
            window,
            thread_id,
            message_id,
        )
    return run_checkpointed_generation_session(
        member_id,
        coach_message,
        window,
        thread_id,
        checkpointer=checkpointer,
        llm=llm,
        message_id=message_id,
        catalog_reader=catalog_reader,
        member_context_reader=member_context_reader,
        verdict_evaluator=verdict_evaluator,
    )


__all__ = [
    "GenerationTurn",
    "run_generation_session",
]
