import os
from typing import Literal, TypedDict

import psycopg
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from neo4j.exceptions import DriverError, Neo4jError

from app.graph.store import neo4j_session

router = APIRouter(prefix="/api")

type Status = Literal["up", "down"]


class HealthReport(TypedDict):
    api: Status
    neo4j: Status
    postgres: Status


def _neo4j_status() -> Status:
    try:
        with neo4j_session() as session:
            session.run("RETURN 1").consume()
    except (DriverError, Neo4jError):
        return "down"
    return "up"


def _postgres_status() -> Status:
    try:
        with psycopg.connect(
            os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5432/coach",
            ),
            connect_timeout=3,
        ) as connection:
            connection.execute("SELECT 1").fetchone()
    except psycopg.Error:
        return "down"
    return "up"


@router.get("/health")
def health() -> JSONResponse:
    report = HealthReport(
        api="up",
        neo4j=_neo4j_status(),
        postgres=_postgres_status(),
    )
    status_code = 200 if all(status == "up" for status in report.values()) else 503
    return JSONResponse(content=report, status_code=status_code)
