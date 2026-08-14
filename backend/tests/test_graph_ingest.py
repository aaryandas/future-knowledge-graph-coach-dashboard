import json
import shutil
from pathlib import Path

import pytest
from app.graph import ingest_kg1, ingest_kg2
from app.graph.store import neo4j_session

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = REPOSITORY_ROOT / "data"
SEED_SOURCE = "data/member-context.json"
TEST_NODE_IDS = (
    "mbr_01HX9JORDAN:workout:obsolete-index-0",
    "mbr_01HX9JORDAN:coach-task:obsolete-index-0",
    "test:runtime-workout-session",
    "test:runtime-coach-task",
)


def test_ingest_kg1_rejects_uncited_condition_row(tmp_path: Path) -> None:
    data_directory = tmp_path / "data"
    shutil.copytree(DATA_DIRECTORY, data_directory)
    conditions_path = data_directory / "contraindications.json"
    conditions = json.loads(conditions_path.read_bytes())
    del conditions[0]["citation"]
    conditions_path.write_text(json.dumps(conditions))

    with pytest.raises(ValueError, match="Condition row 0 requires one citation"):
        ingest_kg1(data_directory)


def test_ingest_kg2_reconciles_seed_owned_nodes_and_preserves_runtime_nodes() -> None:
    ingest_kg2()
    _delete_test_nodes()
    with neo4j_session() as session:
        session.run(
            """
            MATCH (member:Member {id: $member_id})
            MERGE (obsolete_session:WorkoutSession {id: $obsolete_session_id})
            SET obsolete_session.source = $seed_source,
                obsolete_session.version = 'obsolete'
            MERGE (member)-[:performed {id: $obsolete_performed_id}]
                ->(obsolete_session)
            MERGE (obsolete_task:CoachTask {id: $obsolete_task_id})
            SET obsolete_task.source = $seed_source,
                obsolete_task.version = 'obsolete'
            MERGE (obsolete_task)-[:addresses {id: $obsolete_addresses_id}]
                ->(obsolete_session)
            MERGE (runtime_session:WorkoutSession {id: $runtime_session_id})
            SET runtime_session.source = 'coach-confirmed',
                runtime_session.actor = 'coach'
            MERGE (member)-[:performed {id: $runtime_performed_id}]
                ->(runtime_session)
            MERGE (runtime_task:CoachTask {id: $runtime_task_id})
            SET runtime_task.source = 'coach-confirmed',
                runtime_task.actor = 'coach'
            MERGE (runtime_task)-[:addresses {id: $runtime_addresses_id}]
                ->(runtime_session)
            """,
            member_id="mbr_01HX9JORDAN",
            obsolete_session_id=TEST_NODE_IDS[0],
            obsolete_task_id=TEST_NODE_IDS[1],
            runtime_session_id=TEST_NODE_IDS[2],
            runtime_task_id=TEST_NODE_IDS[3],
            seed_source=SEED_SOURCE,
            obsolete_performed_id="test:obsolete-performed",
            obsolete_addresses_id="test:obsolete-addresses",
            runtime_performed_id="test:runtime-performed",
            runtime_addresses_id="test:runtime-addresses",
        ).consume()

    try:
        first_counts = ingest_kg2()
        first_seed_ids = _seed_owned_session_and_task_ids()
        first_surviving_test_ids = _surviving_test_node_ids()
        second_counts = ingest_kg2()

        assert first_seed_ids == _seed_owned_session_and_task_ids()
        assert first_counts == second_counts
        assert TEST_NODE_IDS[0] not in first_seed_ids
        assert TEST_NODE_IDS[1] not in first_seed_ids
        assert first_surviving_test_ids == {TEST_NODE_IDS[2], TEST_NODE_IDS[3]}
        assert _surviving_test_node_ids() == {TEST_NODE_IDS[2], TEST_NODE_IDS[3]}
    finally:
        _delete_test_nodes()


def _seed_owned_session_and_task_ids() -> set[str]:
    with neo4j_session() as session:
        records = session.run(
            """
            MATCH (node)
            WHERE (node:WorkoutSession OR node:CoachTask)
              AND node.source = $source
            RETURN node.id AS id
            """,
            source=SEED_SOURCE,
        )
        return {record["id"] for record in records}


def _surviving_test_node_ids() -> set[str]:
    with neo4j_session() as session:
        records = session.run(
            """
            MATCH (node)
            WHERE node.id IN $ids
            RETURN node.id AS id
            """,
            ids=list(TEST_NODE_IDS),
        )
        return {record["id"] for record in records}


def _delete_test_nodes() -> None:
    with neo4j_session() as session:
        session.run(
            """
            MATCH (node)
            WHERE node.id IN $ids
            DETACH DELETE node
            """,
            ids=list(TEST_NODE_IDS),
        ).consume()
