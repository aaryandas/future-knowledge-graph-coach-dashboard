import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection
from psycopg.rows import dict_row

from app.generation._model import (
    Candidate,
    CatalogExercise,
    ConstraintSet,
    GenerationFailure,
    Plan,
    PlanEntry,
    PlanSection,
    ResolvedIntent,
    ResolvedMention,
)
from app.generation._trace import (
    PackingTraceEvent,
    ResolutionTraceEvent,
    VerdictTraceEvent,
)
from app.generation.intent import Intent
from app.resolver import Candidate as ResolutionCandidate
from app.resolver import Resolution
from app.safety import (
    AgentDecision,
    GraphDecision,
    Verdict,
    WalkedEdge,
    WalkedNode,
    WalkedPath,
)

_DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/coach"
_CHECKPOINT_TYPES = (
    AgentDecision,
    Candidate,
    CatalogExercise,
    ConstraintSet,
    GenerationFailure,
    GraphDecision,
    Intent,
    PackingTraceEvent,
    Plan,
    PlanEntry,
    PlanSection,
    Resolution,
    ResolutionCandidate,
    ResolutionTraceEvent,
    ResolvedIntent,
    ResolvedMention,
    Verdict,
    VerdictTraceEvent,
    WalkedEdge,
    WalkedNode,
    WalkedPath,
)


@contextmanager
def open_postgres_checkpointer(
    database_url: str | None = None,
) -> Iterator[BaseCheckpointSaver[Any]]:
    connection_string = database_url or os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL)
    serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)
    with Connection.connect(
        connection_string,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,  # ty: ignore[invalid-argument-type]  # psycopg overload omits the dict row type.
    ) as connection:
        dict_connection = cast("Connection[dict[str, Any]]", connection)
        checkpointer = PostgresSaver(dict_connection, serde=serde)
        checkpointer.setup()
        yield checkpointer
