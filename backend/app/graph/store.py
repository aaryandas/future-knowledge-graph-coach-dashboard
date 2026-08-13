import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

from neo4j import Driver, GraphDatabase, Session


@cache
def _driver() -> Driver:
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "coach-password"),
        ),
        connection_timeout=3,
    )


@contextmanager
def neo4j_session() -> Iterator[Session]:
    with _driver().session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
        yield session
