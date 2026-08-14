import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from app.graph import MemberContext, get_member_context, ingest_kg1, ingest_kg2

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = REPOSITORY_ROOT / "data"
MEMBER_ID = "mbr_01HX9JORDAN"


def test_ingest_kg1_rejects_uncited_condition_row(tmp_path: Path) -> None:
    data_directory = tmp_path / "data"
    shutil.copytree(DATA_DIRECTORY, data_directory)
    conditions_path = data_directory / "contraindications.json"
    conditions = json.loads(conditions_path.read_bytes())
    del conditions[0]["citation"]
    conditions_path.write_text(json.dumps(conditions))

    with pytest.raises(ValueError, match="Condition row 0 requires one citation"):
        ingest_kg1(data_directory)


def test_ingest_kg1_reconciles_seed_owned_catalog_and_preserves_other_sources(
    tmp_path: Path,
) -> None:
    catalog_a_directory = tmp_path / "catalog-a"
    catalog_b_directory = tmp_path / "catalog-b"
    other_source_directory = tmp_path / "other-source"
    other_source_cleanup_directory = tmp_path / "other-source-cleanup"
    for directory in (
        catalog_a_directory,
        catalog_b_directory,
        other_source_directory,
        other_source_cleanup_directory,
    ):
        shutil.copytree(DATA_DIRECTORY, directory)

    _extend_kg1_catalog(catalog_a_directory)
    _set_other_ontology_source(other_source_directory, include_extra_node=True)
    _set_other_ontology_source(other_source_cleanup_directory, include_extra_node=False)

    try:
        ingest_kg1(other_source_cleanup_directory)
        baseline_counts = ingest_kg1(catalog_b_directory)

        catalog_a_counts = ingest_kg1(catalog_a_directory)
        catalog_b_counts = ingest_kg1(catalog_b_directory)

        assert catalog_b_counts == baseline_counts
        assert {
            label: catalog_a_counts.nodes[label] - catalog_b_counts.nodes[label]
            for label in catalog_a_counts.nodes
        } == {
            "Exercise": 1,
            "MuscleGroup": 1,
            "Joint": 1,
            "MovementPattern": 1,
            "Equipment": 1,
            "Injury": 1,
            "AnatomicalStructure": 1,
            "ClinicalFinding": 1,
        }

        ingest_kg1(other_source_directory)
        first_counts = ingest_kg1(catalog_b_directory)
        second_counts = ingest_kg1(catalog_b_directory)

        expected_nodes = dict(baseline_counts.nodes)
        expected_nodes["AnatomicalStructure"] += 1
        assert first_counts.nodes == expected_nodes
        assert first_counts.edges == baseline_counts.edges
        assert second_counts == first_counts
    finally:
        ingest_kg1(other_source_cleanup_directory)
        ingest_kg1(catalog_b_directory)


def test_ingest_kg2_reconciles_seed_owned_nodes_and_preserves_other_sources(
    tmp_path: Path,
) -> None:
    seed_data_directory = tmp_path / "seed-data"
    other_data_directory = tmp_path / "other-data"
    shutil.copytree(DATA_DIRECTORY, seed_data_directory)
    shutil.copytree(DATA_DIRECTORY, other_data_directory)

    seed_member_path = seed_data_directory / "member-context.json"
    other_member_path = other_data_directory / "member-context-other-source.json"
    (other_data_directory / "member-context.json").rename(other_member_path)
    base_member_bytes = seed_member_path.read_bytes()
    base_member = cast(dict[str, Any], json.loads(base_member_bytes))

    obsolete_title = "Obsolete seed workout"
    obsolete_task_text = "Obsolete seed coach task"
    survivor_title = "Workout from another source"
    survivor_task_text = "Coach task from another source"
    seed_member_path.write_text(
        json.dumps(
            _member_fixture(
                base_member,
                workout={
                    "date": "2026-05-01",
                    "title": obsolete_title,
                    "planned": True,
                    "completed": True,
                    "duration_min": 30,
                    "rpe": 6,
                    "exercises": [],
                },
                task={"type": "celebrate", "text": obsolete_task_text},
            )
        )
    )
    other_member_path.write_text(
        json.dumps(
            _member_fixture(
                base_member,
                workout={
                    "date": "2026-05-02",
                    "title": survivor_title,
                    "planned": True,
                    "completed": True,
                    "duration_min": 35,
                    "rpe": 7,
                    "exercises": [],
                },
                task={"type": "celebrate", "text": survivor_task_text},
            )
        )
    )

    try:
        ingest_kg2(seed_data_directory)
        obsolete_ids = _matching_ids(
            _member_context(), obsolete_title, obsolete_task_text
        )

        ingest_kg2(other_data_directory)
        survivor_ids = _matching_ids(
            _member_context(), survivor_title, survivor_task_text
        )

        seed_member_path.write_bytes(base_member_bytes)
        first_counts = ingest_kg2(seed_data_directory)
        first_context = _member_context()
        second_counts = ingest_kg2(seed_data_directory)
        second_context = _member_context()

        assert first_counts == second_counts
        assert first_context == second_context
        assert obsolete_ids.isdisjoint(_session_and_task_ids(first_context))
        assert survivor_ids <= _session_and_task_ids(first_context)
    finally:
        other_member_path.write_bytes(base_member_bytes)
        ingest_kg2(other_data_directory)
        seed_member_path.write_bytes(base_member_bytes)
        ingest_kg2(seed_data_directory)


def _member_fixture(
    base_member: dict[str, Any],
    *,
    workout: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    member = deepcopy(base_member)
    cast(list[dict[str, Any]], member["workout_history"]).append(workout)
    coach_brief = cast(dict[str, Any], member["coach_brief"])
    cast(list[dict[str, Any]], coach_brief["morning_tasks"]).append(task)
    return member


def _extend_kg1_catalog(data_directory: Path) -> None:
    exercises_path = data_directory / "exercises.json"
    exercises = cast(list[dict[str, Any]], json.loads(exercises_path.read_bytes()))
    exercises.append(
        {
            "id": "test:gnt-275:obsolete-exercise",
            "name": "GNT-275 obsolete exercise",
            "muscle_groups": ["gnt-275 obsolete muscle group"],
            "joints_loaded": ["gnt-275 obsolete joint"],
            "movement_patterns": ["gnt-275 obsolete pattern"],
            "equipment_required": ["GNT-275 Obsolete Equipment"],
            "is_bilateral": False,
            "side": None,
            "priority_tier": 3,
            "is_reps": True,
            "is_duration": False,
            "supports_weight": False,
            "estimated_rep_duration": 1.0,
            "bilateral_pair_id": None,
        }
    )
    exercises_path.write_text(json.dumps(exercises))

    snomed_path = data_directory / "ontology" / "snomed-ct.json"
    snomed = cast(dict[str, Any], json.loads(snomed_path.read_bytes()))
    concepts = cast(list[dict[str, Any]], snomed["concepts"])
    concepts.extend(
        (
            {
                "id": "snomedct:test-gnt-275-anatomy",
                "code": "test-gnt-275-anatomy",
                "kind": "AnatomicalStructure",
                "preferred_term": "GNT-275 obsolete anatomical structure",
                "synonyms": [],
            },
            {
                "id": "snomedct:test-gnt-275-finding",
                "code": "test-gnt-275-finding",
                "kind": "ClinicalFinding",
                "preferred_term": "GNT-275 obsolete clinical finding",
                "synonyms": [],
            },
        )
    )
    snomed_path.write_text(json.dumps(snomed))

    conditions_path = data_directory / "contraindications.json"
    conditions = cast(list[dict[str, Any]], json.loads(conditions_path.read_bytes()))
    conditions.append(
        {
            "id": "fkg:injury/gnt-275-obsolete-injury",
            "name": "GNT-275 obsolete Injury",
            "clinical_finding_id": "snomedct:test-gnt-275-finding",
            "target_kind": "MovementPattern",
            "target_id": "fkg:movement-pattern/gnt-275-obsolete-pattern",
            "level": "avoid",
            "note": "Test-only obsolete seed knowledge.",
            "citation": {
                "reference": "GNT-275 seam fixture",
                "url": "https://example.com/gnt-275",
            },
        }
    )
    conditions_path.write_text(json.dumps(conditions))

    mappings_path = data_directory / "ontology" / "skos-mappings.json"
    mappings = cast(dict[str, Any], json.loads(mappings_path.read_bytes()))
    mapping_rows = cast(list[dict[str, Any]], mappings["mappings"])
    mapping_rows.append(
        {
            "id": "fkg:injury/gnt-275-obsolete-injury:exactMatch:snomedct:test-gnt-275-finding",
            "source_id": "fkg:injury/gnt-275-obsolete-injury",
            "predicate": "skos:exactMatch",
            "target_id": "snomedct:test-gnt-275-finding",
        }
    )
    mappings_path.write_text(json.dumps(mappings))


def _set_other_ontology_source(
    data_directory: Path, *, include_extra_node: bool
) -> None:
    snomed_path = data_directory / "ontology" / "snomed-ct.json"
    snomed = cast(dict[str, Any], json.loads(snomed_path.read_bytes()))
    snomed["artifact_id"] = "test:gnt-275:other-ontology-source"
    if include_extra_node:
        concepts = cast(list[dict[str, Any]], snomed["concepts"])
        concepts.append(
            {
                "id": "test:gnt-275:other-anatomical-structure",
                "code": "test-gnt-275-other-anatomy",
                "kind": "AnatomicalStructure",
                "preferred_term": "GNT-275 other-source anatomical structure",
                "synonyms": [],
            }
        )
    snomed_path.write_text(json.dumps(snomed))


def _member_context() -> MemberContext:
    context = get_member_context(MEMBER_ID)
    assert context is not None
    return context


def _matching_ids(context: MemberContext, title: str, task_text: str) -> set[str]:
    workout_id = next(
        session.node_id
        for session in context.workout_sessions
        if session.title == title
    )
    task_id = next(
        task.node_id
        for task in context.morning_brief.coach_tasks
        if task.text == task_text
    )
    return {workout_id, task_id}


def _session_and_task_ids(context: MemberContext) -> set[str]:
    return {
        *(session.node_id for session in context.workout_sessions),
        *(task.node_id for task in context.morning_brief.coach_tasks),
    }
