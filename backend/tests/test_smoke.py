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
    assert first_kg1_counts.nodes == {
        "AnatomicalStructure": 442,
        "ClinicalFinding": 4,
        "Equipment": 32,
        "Exercise": 53,
        "Injury": 4,
        "Joint": 9,
        "MovementPattern": 37,
        "MuscleGroup": 19,
    }
    assert first_kg1_counts.edges == {
        "contraindicates": 4,
        "exactMatch": 13,
        "findingSite": 4,
        "isA": 559,
        "loads": 133,
        "performs": 96,
        "requires": 71,
        "targets": 130,
    }
    assert response.status_code == 200
    assert response.json() == {
        "api": "up",
        "neo4j": "up",
        "postgres": "up",
    }
