from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.graph import (
    GraphEdgeKind,
    GraphName,
    GraphNeighborhood,
    GraphNodeKind,
    GraphPropertyValue,
    get_graph_neighborhood,
)


class GraphNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: GraphNodeKind
    graph: GraphName
    label: str
    properties: dict[str, GraphPropertyValue]


class GraphEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source: str
    target: str
    kind: GraphEdgeKind


class GraphNeighborhoodPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-graph-neighborhood"] = "data-graph-neighborhood"
    member_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


type GraphNeighborhoodReader = Callable[[str], GraphNeighborhood | None]


def create_graph_view_router(
    neighborhood_reader: GraphNeighborhoodReader = get_graph_neighborhood,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get(
        "/members/{member_id}/graph-neighborhood",
        response_model=GraphNeighborhoodPart,
        summary="Read a member graph neighborhood",
        description=(
            "Reads Member → pursues|has|owns, then MemberInjury → exactMatch ← "
            "Injury → contraindicates → MovementPattern ← performs ← Exercise."
        ),
    )
    def graph_neighborhood(member_id: str) -> GraphNeighborhoodPart:
        graph_neighborhood = neighborhood_reader(member_id)
        if graph_neighborhood is None:
            raise HTTPException(status_code=404, detail="Member not found")
        return GraphNeighborhoodPart(
            member_id=graph_neighborhood.member_id,
            nodes=[
                GraphNode(
                    id=node.id,
                    kind=node.kind,
                    graph=node.graph,
                    label=node.label,
                    properties=dict(node.properties),
                )
                for node in graph_neighborhood.nodes
            ],
            edges=[
                GraphEdge(
                    id=edge.id,
                    source=edge.source,
                    target=edge.target,
                    kind=edge.kind,
                )
                for edge in graph_neighborhood.edges
            ],
        )

    return router


router = create_graph_view_router()
