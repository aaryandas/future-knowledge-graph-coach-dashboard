import os
from collections.abc import Callable
from typing import Literal, TypedDict

import psycopg
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.graph.store import graph_is_available

type Status = Literal["up", "down"]
type AvailabilityProbe = Callable[[], bool]


class HealthReport(TypedDict):
    api: Status
    neo4j: Status
    postgres: Status


def _postgres_is_available() -> bool:
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
        return False
    return True


def create_health_router(
    neo4j_probe: AvailabilityProbe = graph_is_available,
    postgres_probe: AvailabilityProbe = _postgres_is_available,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> JSONResponse:
        report = HealthReport(
            api="up",
            neo4j="up" if neo4j_probe() else "down",
            postgres="up" if postgres_probe() else "down",
        )
        status_code = 200 if all(status == "up" for status in report.values()) else 503
        return JSONResponse(content=report, status_code=status_code)

    return router


router = create_health_router()
