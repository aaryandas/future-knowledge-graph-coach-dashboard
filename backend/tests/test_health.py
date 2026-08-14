from collections.abc import Callable

import pytest
from app.api.health import create_health_router
from app.main import app
from fastapi import FastAPI
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "api": "up",
        "neo4j": "up",
        "postgres": "up",
    }


def _probe(available: bool) -> Callable[[], bool]:
    def probe() -> bool:
        return available

    return probe


@pytest.mark.parametrize(
    ("neo4j_available", "postgres_available", "expected_report"),
    [
        (False, True, {"api": "up", "neo4j": "down", "postgres": "up"}),
        (True, False, {"api": "up", "neo4j": "up", "postgres": "down"}),
        (False, False, {"api": "up", "neo4j": "down", "postgres": "down"}),
    ],
)
def test_health_returns_503_when_a_store_is_down(
    neo4j_available: bool,
    postgres_available: bool,
    expected_report: dict[str, str],
) -> None:
    test_app = FastAPI()
    test_app.include_router(
        create_health_router(
            neo4j_probe=_probe(neo4j_available),
            postgres_probe=_probe(postgres_available),
        )
    )

    response = TestClient(test_app).get("/api/health")

    assert response.status_code == 503
    assert response.json() == expected_report
