from app.graph import ingest_kg1, ingest_kg2
from app.main import app
from fastapi.testclient import TestClient


def test_ci_smoke_ingests_kg1_and_kg2_and_reports_health() -> None:
    first_kg1_counts = ingest_kg1()
    first_kg2_counts = ingest_kg2()
    second_kg1_counts = ingest_kg1()
    second_kg2_counts = ingest_kg2()

    response = TestClient(app).get("/api/health")

    assert second_kg1_counts == first_kg1_counts
    assert second_kg2_counts == first_kg2_counts
    assert response.status_code == 200
    assert response.json() == {
        "api": "up",
        "neo4j": "up",
        "postgres": "up",
    }
