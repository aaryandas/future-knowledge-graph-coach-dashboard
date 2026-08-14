from app.api.graph_view import create_graph_view_router
from app.graph import GraphEdge, GraphNeighborhood, GraphNode
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _graph_neighborhood(member_id: str) -> GraphNeighborhood | None:
    if member_id != "mbr_01HX9JORDAN":
        return None
    return GraphNeighborhood(
        member_id=member_id,
        nodes=(
            GraphNode(
                id=member_id,
                kind="Member",
                graph="Member Context Graph (KG2)",
                label="Jordan Rivera",
                properties={"name": "Jordan Rivera"},
            ),
            GraphNode(
                id="inj_knee_left",
                kind="MemberInjury",
                graph="Member Context Graph (KG2)",
                label="left knee",
                properties={"status": "recovering", "severity": "mild"},
            ),
        ),
        edges=(
            GraphEdge(
                id=f"{member_id}:has:inj_knee_left",
                source=member_id,
                target="inj_knee_left",
                kind="has",
            ),
        ),
    )


def _client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(create_graph_view_router(_graph_neighborhood))
    return TestClient(test_app)


def test_graph_neighborhood_returns_glossary_verbatim_labels() -> None:
    response = _client().get("/api/members/mbr_01HX9JORDAN/graph-neighborhood")

    assert response.status_code == 200
    assert response.json() == {
        "type": "data-graph-neighborhood",
        "member_id": "mbr_01HX9JORDAN",
        "nodes": [
            {
                "id": "mbr_01HX9JORDAN",
                "kind": "Member",
                "graph": "Member Context Graph (KG2)",
                "label": "Jordan Rivera",
                "properties": {"name": "Jordan Rivera"},
            },
            {
                "id": "inj_knee_left",
                "kind": "MemberInjury",
                "graph": "Member Context Graph (KG2)",
                "label": "left knee",
                "properties": {"status": "recovering", "severity": "mild"},
            },
        ],
        "edges": [
            {
                "id": "mbr_01HX9JORDAN:has:inj_knee_left",
                "source": "mbr_01HX9JORDAN",
                "target": "inj_knee_left",
                "kind": "has",
            }
        ],
    }


def test_graph_neighborhood_returns_404_for_unknown_member() -> None:
    response = _client().get("/api/members/unknown/graph-neighborhood")

    assert response.status_code == 404
    assert response.json() == {"detail": "Member not found"}
