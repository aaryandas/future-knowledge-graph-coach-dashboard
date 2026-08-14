import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, LiteralString, cast

from app.graph.conditions import CONDITIONS_SOURCE, AuthoredConditions, load_conditions
from app.graph.schema import (
    EDGE_TYPES,
    EXERCISE_TAXONOMIES,
    NODE_LABELS,
    EdgeType,
    NodeLabel,
)
from app.graph.store import neo4j_session
from neo4j import ManagedTransaction, Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIRECTORY = REPOSITORY_ROOT / "data"
CATALOG_SOURCE = "data/exercises.json"

type JsonObject = dict[str, Any]


@dataclass(frozen=True)
class Node:
    id: str
    properties: JsonObject


@dataclass(frozen=True)
class Edge:
    id: str
    source_id: str
    target_id: str
    properties: JsonObject


@dataclass(frozen=True)
class NodeBatch:
    label: NodeLabel
    rows: list[Node]


@dataclass(frozen=True)
class EdgeBatch:
    source_label: NodeLabel
    edge_type: EdgeType
    target_label: NodeLabel
    rows: list[Edge]


@dataclass(frozen=True)
class KG1Payload:
    nodes: list[NodeBatch]
    edges: list[EdgeBatch]


@dataclass(frozen=True)
class KG1Counts:
    nodes: dict[NodeLabel, int]
    edges: dict[EdgeType, int]


def ingest_kg1(data_directory: Path = DEFAULT_DATA_DIRECTORY) -> KG1Counts:
    payload = _load_kg1(data_directory)
    ingested_at = datetime.now(UTC).isoformat()

    with neo4j_session() as session:
        _ensure_constraints(session)
        session.execute_write(_merge_payload, payload, ingested_at)
        return _read_counts(session)


def _load_kg1(data_directory: Path) -> KG1Payload:
    catalog_path = data_directory / "exercises.json"
    catalog_bytes = catalog_path.read_bytes()
    exercises = cast(list[JsonObject], json.loads(catalog_bytes))
    catalog_version = sha256(catalog_bytes).hexdigest()

    ontology_directory = data_directory / "ontology"
    snomed = _read_object(ontology_directory / "snomed-ct.json")
    mappings = _read_object(ontology_directory / "skos-mappings.json")
    conditions = load_conditions(data_directory / "conditions.json")

    node_batches, exercise_edge_batches = _catalog_batches(exercises, catalog_version)
    snomed_node_batches, snomed_edge_batches, concept_labels = _snomed_batches(snomed)
    condition_node_batches, condition_edge_batches, injury_findings = (
        _condition_batches(conditions, node_batches, concept_labels)
    )
    mapping_edge_batches = _mapping_batches(mappings, concept_labels, injury_findings)

    return KG1Payload(
        nodes=[*node_batches, *snomed_node_batches, *condition_node_batches],
        edges=[
            *exercise_edge_batches,
            *snomed_edge_batches,
            *mapping_edge_batches,
            *condition_edge_batches,
        ],
    )


def _read_object(path: Path) -> JsonObject:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _catalog_batches(
    exercises: list[JsonObject], version: str
) -> tuple[list[NodeBatch], list[EdgeBatch]]:
    exercise_rows: list[Node] = []
    taxonomy_rows: dict[NodeLabel, dict[str, Node]] = defaultdict(dict)
    edge_rows: dict[tuple[NodeLabel, EdgeType], list[Edge]] = defaultdict(list)
    taxonomy_fields = {field for field, _, _, _ in EXERCISE_TAXONOMIES}

    for exercise in exercises:
        exercise_id = _required_string(exercise, "id")
        properties = {
            key: value
            for key, value in exercise.items()
            if key != "id" and key not in taxonomy_fields
        }
        properties.update(source=CATALOG_SOURCE, version=version)
        exercise_rows.append(Node(id=exercise_id, properties=properties))

        for field, label, edge_type, id_prefix in EXERCISE_TAXONOMIES:
            terms = exercise.get(field)
            if not isinstance(terms, list) or not all(
                isinstance(term, str) for term in terms
            ):
                raise ValueError(f"Exercise {exercise_id} has invalid {field}")

            for term in terms:
                target_id = f"fkg:{id_prefix}/{_slug(term)}"
                taxonomy_rows[label][target_id] = Node(
                    id=target_id,
                    properties={
                        "name": term,
                        "source": CATALOG_SOURCE,
                        "version": version,
                    },
                )
                edge_id = f"{exercise_id}:{edge_type}:{target_id}"
                edge_rows[(label, edge_type)].append(
                    Edge(
                        id=edge_id,
                        source_id=exercise_id,
                        target_id=target_id,
                        properties={
                            "source": CATALOG_SOURCE,
                            "version": version,
                        },
                    )
                )

    _require_unique_ids(exercise_rows, CATALOG_SOURCE)
    nodes = [NodeBatch("Exercise", exercise_rows)]
    nodes.extend(
        NodeBatch(label, list(rows.values())) for label, rows in taxonomy_rows.items()
    )
    edges = [
        EdgeBatch("Exercise", edge_type, target_label, rows)
        for (target_label, edge_type), rows in edge_rows.items()
    ]
    return nodes, edges


def _snomed_batches(
    artifact: JsonObject,
) -> tuple[list[NodeBatch], list[EdgeBatch], dict[str, NodeLabel]]:
    source, version = _artifact_stamp(artifact)
    concepts = artifact.get("concepts")
    edges = artifact.get("edges")
    if not isinstance(concepts, list) or not isinstance(edges, list):
        raise TypeError("SNOMED artifact must contain concepts and edges")

    node_rows: dict[NodeLabel, list[Node]] = defaultdict(list)
    concept_labels: dict[str, NodeLabel] = {}
    for value in concepts:
        concept = _object(value, "SNOMED concept")
        concept_id = _required_string(concept, "id")
        label = _node_label(_required_string(concept, "kind"))
        if label not in ("AnatomicalStructure", "ClinicalFinding"):
            raise ValueError(f"Unsupported SNOMED concept kind: {label}")
        if concept_id in concept_labels:
            raise ValueError(f"Duplicate SNOMED concept id: {concept_id}")
        concept_labels[concept_id] = label
        properties = {
            key: item for key, item in concept.items() if key not in {"id", "kind"}
        }
        properties.update(source=source, version=version)
        node_rows[label].append(Node(id=concept_id, properties=properties))

    edge_rows: dict[tuple[NodeLabel, EdgeType, NodeLabel], list[Edge]] = defaultdict(
        list
    )
    for value in edges:
        edge = _object(value, "SNOMED edge")
        source_id = _required_string(edge, "source_id")
        target_id = _required_string(edge, "target_id")
        edge_type = _edge_type(_required_string(edge, "type"))
        key = (
            _concept_label(concept_labels, source_id),
            edge_type,
            _concept_label(concept_labels, target_id),
        )
        properties = {
            item_key: item
            for item_key, item in edge.items()
            if item_key not in {"id", "source_id", "target_id", "type"}
        }
        properties.update(source=source, version=version)
        edge_rows[key].append(
            Edge(
                id=_required_string(edge, "id"),
                source_id=source_id,
                target_id=target_id,
                properties=properties,
            )
        )

    nodes = [NodeBatch(label, rows) for label, rows in node_rows.items()]
    grouped_edges = [
        EdgeBatch(source_label, edge_type, target_label, rows)
        for (source_label, edge_type, target_label), rows in edge_rows.items()
    ]
    return nodes, grouped_edges, concept_labels


def _mapping_batches(
    artifact: JsonObject,
    concept_labels: dict[str, NodeLabel],
    injury_findings: dict[str, str],
) -> list[EdgeBatch]:
    source, version = _artifact_stamp(artifact)
    mappings = artifact.get("mappings")
    if not isinstance(mappings, list):
        raise TypeError("SKOS artifact must contain mappings")

    rows_by_labels: dict[tuple[NodeLabel, NodeLabel], list[Edge]] = defaultdict(list)
    mapped_injuries: set[str] = set()
    for value in mappings:
        mapping = _object(value, "SKOS mapping")
        source_id = _required_string(mapping, "source_id")
        if source_id.startswith("fkg:injury/"):
            source_label: NodeLabel = "Injury"
            expected_target_id = injury_findings.get(source_id)
            if expected_target_id is None:
                raise ValueError(f"Unknown authored Injury mapping source: {source_id}")
            mapped_injuries.add(source_id)
        elif source_id.startswith("fkg:joint/"):
            source_label = "Joint"
            expected_target_id = None
        else:
            raise ValueError(f"Unsupported exactMatch source: {source_id}")
        predicate = _required_string(mapping, "predicate")
        if predicate != "skos:exactMatch":
            raise ValueError(f"Unsupported SKOS predicate: {predicate}")
        target_id = _required_string(mapping, "target_id")
        if expected_target_id is not None and target_id != expected_target_id:
            raise ValueError(
                f"Authored Injury {source_id} must exactMatch {expected_target_id}"
            )
        target_label = _concept_label(concept_labels, target_id)
        properties = {
            key: item
            for key, item in mapping.items()
            if key not in {"id", "source_id", "target_id"}
        }
        properties.update(source=source, version=version)
        rows_by_labels[(source_label, target_label)].append(
            Edge(
                id=_required_string(mapping, "id"),
                source_id=source_id,
                target_id=target_id,
                properties=properties,
            )
        )

    missing_mappings = injury_findings.keys() - mapped_injuries
    if missing_mappings:
        missing = ", ".join(sorted(missing_mappings))
        raise ValueError(f"Authored Injuries lack exactMatch mappings: {missing}")

    return [
        EdgeBatch(source_label, "exactMatch", target_label, rows)
        for (source_label, target_label), rows in rows_by_labels.items()
    ]


def _condition_batches(
    artifact: AuthoredConditions,
    catalog_node_batches: list[NodeBatch],
    concept_labels: dict[str, NodeLabel],
) -> tuple[list[NodeBatch], list[EdgeBatch], dict[str, str]]:
    catalog_ids = {
        batch.label: {node.id for node in batch.rows} for batch in catalog_node_batches
    }
    injury_nodes: dict[str, Node] = {}
    injury_findings: dict[str, str] = {}
    edge_rows: dict[NodeLabel, list[Edge]] = defaultdict(list)

    for row in artifact.rows:
        if concept_labels.get(row.clinical_finding_id) != "ClinicalFinding":
            raise ValueError(
                f"Authored Injury {row.injury_id} references unknown ClinicalFinding: "
                f"{row.clinical_finding_id}"
            )
        if row.target_id not in catalog_ids.get(row.target_kind, set()):
            raise ValueError(
                f"Authored Injury {row.injury_id} references unknown "
                f"{row.target_kind}: {row.target_id}"
            )

        existing_finding = injury_findings.get(row.injury_id)
        if existing_finding is not None and existing_finding != row.clinical_finding_id:
            raise ValueError(
                f"Authored Injury {row.injury_id} has conflicting ClinicalFindings"
            )
        existing_node = injury_nodes.get(row.injury_id)
        if existing_node is not None and existing_node.properties["name"] != row.name:
            raise ValueError(f"Authored Injury {row.injury_id} has conflicting names")

        injury_findings[row.injury_id] = row.clinical_finding_id
        injury_nodes[row.injury_id] = Node(
            id=row.injury_id,
            properties={
                "name": row.name,
                "clinical_finding_id": row.clinical_finding_id,
                "source": CONDITIONS_SOURCE,
                "version": artifact.version,
            },
        )
        edge_rows[row.target_kind].append(
            Edge(
                id=f"{row.injury_id}:contraindicates:{row.target_id}",
                source_id=row.injury_id,
                target_id=row.target_id,
                properties={
                    "verdict": row.verdict,
                    "note": row.note,
                    "citation": row.citation,
                    "citation_url": row.citation_url,
                    "source": CONDITIONS_SOURCE,
                    "version": artifact.version,
                },
            )
        )

    nodes = [NodeBatch("Injury", list(injury_nodes.values()))]
    edges = [
        EdgeBatch("Injury", "contraindicates", target_label, rows)
        for target_label, rows in edge_rows.items()
    ]
    return nodes, edges, injury_findings


def _artifact_stamp(artifact: JsonObject) -> tuple[str, str]:
    return (
        _required_string(artifact, "artifact_id"),
        _required_string(artifact, "version"),
    )


def _required_string(value: JsonObject, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Expected non-empty string at {key}")
    return item


def _object(value: Any, description: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(f"{description} must be a JSON object")
    return value


def _node_label(value: str) -> NodeLabel:
    if value not in NODE_LABELS:
        raise ValueError(f"Unsupported node label: {value}")
    return value


def _edge_type(value: str) -> EdgeType:
    if value not in EDGE_TYPES:
        raise ValueError(f"Unsupported edge type: {value}")
    return value


def _concept_label(labels: dict[str, NodeLabel], concept_id: str) -> NodeLabel:
    try:
        return labels[concept_id]
    except KeyError as error:
        raise ValueError(f"Unknown SNOMED concept id: {concept_id}") from error


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError(f"Cannot create stable id from {value!r}")
    return slug


def _require_unique_ids(nodes: list[Node], source: str) -> None:
    ids = [node.id for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{source} contains duplicate ids")


def _ensure_constraints(session: Session) -> None:
    for label in NODE_LABELS:
        constraint_name = f"kg1_{_slug(label)}_id"
        session.run(
            _cypher(
                f"""
            CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
            FOR (node:`{label}`) REQUIRE node.id IS UNIQUE
            """
            )
        ).consume()


def _merge_payload(
    transaction: ManagedTransaction, payload: KG1Payload, ingested_at: str
) -> None:
    for batch in payload.nodes:
        transaction.run(
            _cypher(
                f"""
            UNWIND $rows AS row
            MERGE (node:`{batch.label}` {{id: row.id}})
            SET node += row.properties
            SET node.ingested_at = coalesce(node.ingested_at, datetime($ingested_at))
            """
            ),
            rows=[asdict(node) for node in batch.rows],
            ingested_at=ingested_at,
        ).consume()

    for batch in payload.edges:
        transaction.run(
            _cypher(
                f"""
            UNWIND $rows AS row
            MATCH (source:`{batch.source_label}` {{id: row.source_id}})
            MATCH (target:`{batch.target_label}` {{id: row.target_id}})
            MERGE (source)-[edge:`{batch.edge_type}` {{id: row.id}}]->(target)
            SET edge += row.properties
            SET edge.ingested_at = coalesce(edge.ingested_at, datetime($ingested_at))
            """
            ),
            rows=[asdict(edge) for edge in batch.rows],
            ingested_at=ingested_at,
        ).consume()


def _read_counts(session: Session) -> KG1Counts:
    node_counts = {
        label: _count(
            session, _cypher(f"MATCH (node:`{label}`) RETURN count(node) AS count")
        )
        for label in NODE_LABELS
    }
    edge_counts = {
        edge_type: _count(
            session,
            _cypher(f"MATCH ()-[edge:`{edge_type}`]->() RETURN count(edge) AS count"),
        )
        for edge_type in EDGE_TYPES
    }
    return KG1Counts(nodes=node_counts, edges=edge_counts)


def _cypher(query: str) -> LiteralString:
    # Interpolated fragments come only from the closed schema constants.
    return cast(LiteralString, query)


def _count(session: Session, query: LiteralString) -> int:
    record = session.run(query).single(strict=True)
    return cast(int, record["count"])
