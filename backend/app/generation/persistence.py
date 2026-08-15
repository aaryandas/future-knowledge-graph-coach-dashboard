import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields
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
    DerivedExclusionRule,
    GenerationFailure,
    Plan,
    PlanEntry,
    PlanSection,
    ResolvedIntent,
    ResolvedMention,
)
from app.generation._trace import (
    AgentTraceEvent,
    PackingTraceEvent,
    ResolutionTraceEvent,
    SubstitutionTraceEvent,
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
_TRACE_EVENT_BY_KIND = {
    "agent": AgentTraceEvent,
    "packing": PackingTraceEvent,
    "resolution": ResolutionTraceEvent,
    "substitution": SubstitutionTraceEvent,
    "verdict": VerdictTraceEvent,
}
_TRACE_EVENT_TYPES = tuple(_TRACE_EVENT_BY_KIND.values())
_CHECKPOINT_TYPES = (
    *_TRACE_EVENT_TYPES,
    AgentDecision,
    Candidate,
    CatalogExercise,
    ConstraintSet,
    DerivedExclusionRule,
    GenerationFailure,
    GraphDecision,
    Intent,
    Plan,
    PlanEntry,
    PlanSection,
    Resolution,
    ResolutionCandidate,
    ResolvedIntent,
    ResolvedMention,
    Verdict,
    WalkedEdge,
    WalkedNode,
    WalkedPath,
)
_TRACE_EVENT_MARKER = "__generation_trace_event__"
_TUPLE_MARKER = "__generation_tuple__"


class _GenerationCheckpointSerializer:
    def __init__(self) -> None:
        self._serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        return self._serde.dumps_typed(_encode_trace_events(obj))

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        return _decode_trace_events(self._serde.loads_typed(data))


@contextmanager
def open_postgres_checkpointer(
    database_url: str | None = None,
) -> Iterator[BaseCheckpointSaver[Any]]:
    connection_string = database_url or os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL)
    serde = _GenerationCheckpointSerializer()
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


def _encode_trace_events(value: Any) -> Any:
    if isinstance(value, _TRACE_EVENT_TYPES):
        return {
            _TRACE_EVENT_MARKER: value.kind,
            "fields": {
                event_field.name: _encode_trace_events(getattr(value, event_field.name))
                for event_field in fields(value)
                if event_field.init
            },
        }
    if isinstance(value, dict):
        return {key: _encode_trace_events(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return {_TUPLE_MARKER: [_encode_trace_events(item) for item in value]}
    if isinstance(value, list):
        return [_encode_trace_events(item) for item in value]
    return value


def _decode_trace_events(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {_TUPLE_MARKER}:
            items = value[_TUPLE_MARKER]
            if not isinstance(items, list):
                raise RuntimeError("Generation checkpoint contains an invalid tuple")
            return tuple(_decode_trace_events(item) for item in items)
        if set(value) == {_TRACE_EVENT_MARKER, "fields"}:
            kind = value[_TRACE_EVENT_MARKER]
            event_fields = value["fields"]
            if not isinstance(kind, str) or not isinstance(event_fields, dict):
                raise RuntimeError(
                    "Generation checkpoint contains an invalid TraceEvent"
                )
            event_type = _TRACE_EVENT_BY_KIND.get(kind)
            if event_type is None:
                raise RuntimeError(
                    "Generation checkpoint contains an unknown TraceEvent"
                )
            return event_type(
                **{
                    key: _decode_trace_events(item)
                    for key, item in event_fields.items()
                }
            )
        return {key: _decode_trace_events(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_decode_trace_events(item) for item in value)
    if isinstance(value, list):
        return [_decode_trace_events(item) for item in value]
    return value
