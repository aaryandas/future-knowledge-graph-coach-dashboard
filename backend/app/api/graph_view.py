from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import Literal, cast

from fastapi import APIRouter, HTTPException
from neo4j.time import Date, DateTime, Time
from pydantic import BaseModel, ConfigDict

from app.graph import get_member_context
from app.graph.store import neo4j_session

type GraphNodeKind = Literal[
    "Exercise",
    "MuscleGroup",
    "Joint",
    "MovementPattern",
    "Equipment",
    "Injury",
    "AnatomicalStructure",
    "ClinicalFinding",
    "Member",
    "Goal",
    "MemberInjury",
    "WorkoutSession",
    "Observation",
    "ChatMessage",
    "Barrier",
    "CoachTask",
]
type GraphEdgeKind = Literal[
    "targets",
    "loads",
    "performs",
    "requires",
    "findingSite",
    "isA",
    "exactMatch",
    "contraindicates",
    "pursues",
    "has",
    "owns",
    "performed",
    "observed",
    "said",
    "received",
    "dislikes",
    "included",
    "evidencedBy",
    "addresses",
]
type GraphName = Literal["Movement/Clinical Graph (KG1)", "Member Context Graph (KG2)"]
type GraphPropertyValue = (
    str | int | float | bool | None | list[str] | list[int] | list[float] | list[bool]
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


type GraphNeighborhoodReader = Callable[[str], GraphNeighborhoodPart | None]

_KG2_KINDS = frozenset(
    {
        "Member",
        "Goal",
        "MemberInjury",
        "WorkoutSession",
        "Observation",
        "ChatMessage",
        "Barrier",
        "CoachTask",
    }
)

_GRAPH_NEIGHBORHOOD_QUERY = """
MATCH (member:Member {id: $member_id})
CALL (member) {
  MATCH (member)-[relationship:pursues]->(target:Goal)
  WITH member, relationship, target
  ORDER BY target.priority, target.id
  LIMIT 2
  RETURN member AS source, relationship, target, 10 AS lane

  UNION ALL

  MATCH (member)-[relationship:has]->(target:MemberInjury)
  WITH member, relationship, target
  ORDER BY target.since DESC, target.id
  LIMIT 1
  RETURN member AS source, relationship, target, 20 AS lane

  UNION ALL

  MATCH (member)-[relationship:owns]->(target:Equipment)
  WITH member, relationship, target
  ORDER BY target.name, target.id
  LIMIT 3
  RETURN member AS source, relationship, target, 30 AS lane

  UNION ALL

  MATCH (member)-[:has]->(source:MemberInjury)
        -[relationship:exactMatch]->(target:ClinicalFinding)
  WITH source, relationship, target
  ORDER BY source.since DESC, target.id
  LIMIT 1
  RETURN source, relationship, target, 40 AS lane

  UNION ALL

  MATCH (member)-[:has]->(:MemberInjury)-[:exactMatch]->(target:ClinicalFinding)
        <-[relationship:exactMatch]-(source:Injury)
  WITH source, relationship, target
  ORDER BY source.id, target.id
  LIMIT 1
  RETURN source, relationship, target, 50 AS lane

  UNION ALL

  MATCH (member)-[:has]->(:MemberInjury)-[:exactMatch]->(:ClinicalFinding)
        <-[:exactMatch]-(source:Injury)
        -[relationship:contraindicates]->(target:MovementPattern)
  WITH source, relationship, target
  ORDER BY target.name, target.id
  LIMIT 1
  RETURN source, relationship, target, 60 AS lane

  UNION ALL

  MATCH (member)-[:has]->(:MemberInjury)-[:exactMatch]->(:ClinicalFinding)
        <-[:exactMatch]-(:Injury)-[:contraindicates]->(target:MovementPattern)
        <-[relationship:performs]-(source:Exercise)
  WITH source, relationship, target
  ORDER BY source.priority_tier, source.name, source.id
  LIMIT 3
  RETURN source, relationship, target, 70 AS lane
}
RETURN source.id AS source_id,
       labels(source)[0] AS source_kind,
       properties(source) AS source_properties,
       type(relationship) AS edge_kind,
       target.id AS target_id,
       labels(target)[0] AS target_kind,
       properties(target) AS target_properties,
       lane
ORDER BY lane, target_id, source_id
"""


def read_graph_neighborhood(member_id: str) -> GraphNeighborhoodPart | None:
    """Read Member branches and the MemberInjury safety path into KG1."""
    context = get_member_context(member_id)
    if context is None:
        return None

    profile_properties = cast(dict[str, object], asdict(context.profile))
    profile_properties.pop("node_id")
    nodes = {
        context.profile.node_id: GraphNode(
            id=context.profile.node_id,
            kind="Member",
            graph="Member Context Graph (KG2)",
            label=context.profile.name,
            properties=_properties(profile_properties),
        )
    }
    edges: list[GraphEdge] = []

    with neo4j_session() as session:
        records = session.run(
            _GRAPH_NEIGHBORHOOD_QUERY,
            member_id=context.profile.node_id,
        )
        for record in records:
            source = _node(
                record["source_id"],
                record["source_kind"],
                record["source_properties"],
            )
            target = _node(
                record["target_id"],
                record["target_kind"],
                record["target_properties"],
            )
            nodes[source.id] = source
            nodes[target.id] = target
            edge_kind = cast(GraphEdgeKind, record["edge_kind"])
            edges.append(
                GraphEdge(
                    id=f"{source.id}:{edge_kind}:{target.id}",
                    source=source.id,
                    target=target.id,
                    kind=edge_kind,
                )
            )

    return GraphNeighborhoodPart(
        member_id=context.profile.node_id,
        nodes=list(nodes.values()),
        edges=edges,
    )


def create_graph_view_router(
    neighborhood_reader: GraphNeighborhoodReader = read_graph_neighborhood,
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
        neighborhood = neighborhood_reader(member_id)
        if neighborhood is None:
            raise HTTPException(status_code=404, detail="Member not found")
        return neighborhood

    return router


def _node(node_id: object, kind: object, raw_properties: object) -> GraphNode:
    if not isinstance(node_id, str) or not isinstance(kind, str):
        raise TypeError("Graph neighborhood node requires string id and kind")
    if not isinstance(raw_properties, Mapping):
        raise TypeError(f"Graph neighborhood node {node_id} has no properties")
    properties = _properties(cast(Mapping[str, object], raw_properties))
    node_kind = cast(GraphNodeKind, kind)
    return GraphNode(
        id=node_id,
        kind=node_kind,
        graph=_graph_name(node_kind),
        label=_node_label(node_id, properties),
        properties=properties,
    )


def _properties(
    raw_properties: Mapping[str, object],
) -> dict[str, GraphPropertyValue]:
    properties: dict[str, GraphPropertyValue] = {}
    for key, value in raw_properties.items():
        properties[key] = _property_value(value)
    return properties


def _property_value(value: object) -> GraphPropertyValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Date | DateTime | Time):
        return value.iso_format()
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        items = list(value)
        if all(isinstance(item, bool) for item in items):
            return cast(list[bool], items)
        if all(isinstance(item, int) and not isinstance(item, bool) for item in items):
            return cast(list[int], items)
        if all(isinstance(item, float) for item in items):
            return cast(list[float], items)
        if all(isinstance(item, str) for item in items):
            return cast(list[str], items)
    raise RuntimeError(f"Unsupported graph property value: {value!r}")


def _graph_name(kind: GraphNodeKind) -> GraphName:
    if kind in _KG2_KINDS:
        return "Member Context Graph (KG2)"
    return "Movement/Clinical Graph (KG1)"


def _node_label(node_id: str, properties: Mapping[str, GraphPropertyValue]) -> str:
    for key in ("name", "text", "region", "preferred_term", "kind"):
        value = properties.get(key)
        if isinstance(value, str) and value:
            return value
    return node_id


router = create_graph_view_router()
