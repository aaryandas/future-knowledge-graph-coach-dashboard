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
