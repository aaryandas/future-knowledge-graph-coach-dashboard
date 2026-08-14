import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from app.graph import get_member_context, ingest_kg2

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = REPOSITORY_ROOT / "data"
MEMBER_ID = "mbr_01HX9JORDAN"


@pytest.mark.parametrize(
    ("kind", "as_of", "expected_dates", "expected_ages", "expected_stale"),
    [
        ("sleep-night", date(2026, 6, 10), ("2026-06-03",), (7,), (False,)),
        ("sleep-night", date(2026, 6, 11), (), (), ()),
        ("adherence-week", date(2026, 6, 30), ("2026-06-02",), (28,), (False,)),
        ("adherence-week", date(2026, 7, 1), (), (), ()),
        ("resting-hr", date(2026, 7, 4), ("2026-06-04",), (30,), (False,)),
        ("resting-hr", date(2026, 7, 5), (), (), ()),
        ("hrv", date(2026, 7, 4), ("2026-06-04",), (30,), (False,)),
        ("hrv", date(2026, 7, 5), (), (), ()),
        ("weight", date(2026, 8, 31), ("2026-06-02",), (90,), (False,)),
        ("weight", date(2026, 9, 1), (), (), ()),
        ("blood-panel", date(2026, 10, 17), ("2026-04-20",), (180,), (False,)),
        ("blood-panel", date(2026, 10, 18), ("2026-04-20",), (181,), (True,)),
        ("dexa", date(2026, 9, 26), ("2026-03-30",), (180,), (False,)),
        ("dexa", date(2026, 9, 27), ("2026-03-30",), (181,), (True,)),
    ],
)
def test_member_context_applies_each_observation_relevance_window(
    kind: str,
    as_of: date,
    expected_dates: tuple[str, ...],
    expected_ages: tuple[int, ...],
    expected_stale: tuple[bool, ...],
) -> None:
    ingest_kg2()

    member_context = get_member_context(MEMBER_ID, as_of=as_of)

    assert member_context is not None
    observations = tuple(
        observation
        for observation in member_context.observations
        if observation.kind == kind
    )
    assert tuple(observation.observed_at for observation in observations) == (
        expected_dates
    )
    assert tuple(observation.age_days for observation in observations) == expected_ages
    assert tuple(observation.stale for observation in observations) == expected_stale


@pytest.mark.parametrize(
    (
        "member_suffix",
        "member_since",
        "injury_status",
        "completed_workouts",
        "expected_stage",
    ),
    [
        ("recovering", "2026-08-01", "recovering", 0, "recovering"),
        ("new", "2026-08-01", None, 4, "new"),
        ("building", "2025-08-01", None, 4, "building"),
    ],
)
def test_member_context_derives_journey_stage_with_recovering_precedence(
    tmp_path: Path,
    member_suffix: str,
    member_since: str,
    injury_status: str | None,
    completed_workouts: int,
    expected_stage: str,
) -> None:
    data_directory = tmp_path / "data"
    shutil.copytree(DATA_DIRECTORY, data_directory)
    member_path = data_directory / "member-context.json"
    member = json.loads(member_path.read_bytes())
    member_id = f"{MEMBER_ID}_{member_suffix}"
    member["profile"]["id"] = member_id
    member["profile"]["member_since"] = member_since
    member["injuries"] = [] if injury_status is None else member["injuries"]
    if injury_status is not None:
        member["injuries"][0]["status"] = injury_status
    for index, workout in enumerate(member["workout_history"]):
        workout["completed"] = index < completed_workouts
    member_path.write_text(json.dumps(member))
    ingest_kg2(data_directory)

    member_context = get_member_context(member_id, as_of=date(2026, 8, 13))

    assert member_context is not None
    assert member_context.journey_stage.stage == expected_stage
    assert member_context.journey_stage.evidence.member_node_id == member_id
    assert member_context.journey_stage.evidence.completed_workout_count == (
        completed_workouts
    )
    assert member_context.journey_stage.evidence.injury_statuses == (
        () if injury_status is None else (injury_status,)
    )


def test_member_context_keeps_churn_risk_separate_from_journey_stage() -> None:
    ingest_kg2()

    member_context = get_member_context(MEMBER_ID, as_of=date(2026, 12, 10))

    assert member_context is not None
    assert member_context.journey_stage.stage == "recovering"
    assert member_context.journey_stage.evidence.injury_statuses == ("recovering",)
    assert member_context.morning_brief.churn_risk_level == "elevated"
    assert tuple(observation.kind for observation in member_context.observations) == (
        "blood-panel",
        "dexa",
    )
    dexa = member_context.observations[1]
    assert dexa.observed_at == "2026-03-30"
    assert dexa.age_days == 255
    assert dexa.stale is True
