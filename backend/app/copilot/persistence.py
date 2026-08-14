import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver

_DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/coach"


@contextmanager
def open_postgres_checkpointer(
    database_url: str | None = None,
) -> Iterator[BaseCheckpointSaver[Any]]:
    connection_string = database_url or os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL)
    with PostgresSaver.from_conn_string(connection_string) as checkpointer:
        checkpointer.setup()
        yield checkpointer
