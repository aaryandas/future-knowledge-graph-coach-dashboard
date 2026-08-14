from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.generation._catalog import (
    read_catalog_exercises,
    read_generation_member_context,
)
from app.generation.graph import (
    CatalogReader,
    GenerationTurn,
    MemberContextReader,
    VerdictEvaluator,
)
from app.generation.graph import run_generation_session as run_checkpointed_session
from app.generation.llm import AnnotationLLM, IntentLLM
from app.generation.persistence import open_postgres_checkpointer
from app.safety import evaluate_safety


def run_generation_session(
    member_id: str,
    coach_message: str,
    window: int,
    thread_id: str,
    message_id: str,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    llm: IntentLLM | None = None,
    annotation_llm: AnnotationLLM | None = None,
    catalog_reader: CatalogReader = read_catalog_exercises,
    member_context_reader: MemberContextReader = read_generation_member_context,
    verdict_evaluator: VerdictEvaluator = evaluate_safety,
) -> GenerationTurn:
    if checkpointer is not None:
        return run_checkpointed_session(
            member_id,
            coach_message,
            window,
            thread_id,
            checkpointer=checkpointer,
            llm=llm,
            annotation_llm=annotation_llm,
            message_id=message_id,
            catalog_reader=catalog_reader,
            member_context_reader=member_context_reader,
            verdict_evaluator=verdict_evaluator,
        )
    with open_postgres_checkpointer() as stored_checkpointer:
        return run_checkpointed_session(
            member_id,
            coach_message,
            window,
            thread_id,
            checkpointer=stored_checkpointer,
            llm=llm,
            annotation_llm=annotation_llm,
            message_id=message_id,
            catalog_reader=catalog_reader,
            member_context_reader=member_context_reader,
            verdict_evaluator=verdict_evaluator,
        )
