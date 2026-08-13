import os
from functools import cache

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError


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


def graph_is_available() -> bool:
    """Report whether the graph store can serve queries."""
    try:
        with _driver().session(
            database=os.getenv("NEO4J_DATABASE", "neo4j")
        ) as session:
            session.run("RETURN 1").consume()
    except (DriverError, Neo4jError):
        return False
    return True
