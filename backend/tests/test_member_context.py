from datetime import date, timedelta

import pytest
from app.graph import (
    OBSERVATION_RELEVANCE_WINDOWS,
    JourneyStageName,
    ObservationKind,
    derive_journey_stage,
    get_member_context,
    ingest_kg2,
    observation_freshness,
)

MEMBER_ID = "mbr_01HX9JORDAN"


def test_observation_relevance_windows_match_each_kind_cadence() -> None:
    assert {
        kind: (window.days, window.latest_value, window.stale_after_days)
        for kind, window in OBSERVATION_RELEVANCE_WINDOWS.items()
    } == {
        "sleep-night": (7, False, 7),
        "adherence-week": (28, False, 28),
        "resting-hr": (30, False, 30),
        "hrv": (30, False, 30),
        "weight": (90, False, 90),
        "blood-panel": (None, True, 180),
        "dexa": (None, True, 180),
    }


@pytest.mark.parametrize(
    ("kind", "age_days", "stale"),
    [
        ("sleep-night", 7, False),
        ("sleep-night", 8, True),
        ("adherence-week", 28, False),
        ("adherence-week", 29, True),
        ("resting-hr", 30, False),
        ("hrv", 31, True),
        ("weight", 91, True),
        ("blood-panel", 180, False),
        ("dexa", 181, True),
    ],
)
def test_stale_is_computed_from_the_injected_read_date(
    kind: ObservationKind, age_days: int, stale: bool
) -> None:
    as_of = date(2026, 8, 13)

    freshness = observation_freshness(
        kind,
        (as_of - timedelta(days=age_days)).isoformat(),
        as_of=as_of,
    )

    assert freshness.age_days == age_days
    assert freshness.stale is stale


@pytest.mark.parametrize(
    ("member_since", "injuries", "workouts", "expected_stage"),
    [
        (
            "2026-08-01",
            (("injury:1", "recovering"),),
            (),
            "recovering",
        ),
        ("2026-08-01", (), (), "new"),
        (
            "2025-08-01",
            (),
            tuple((f"workout:{index}", True) for index in range(4)),
            "building",
        ),
    ],
)
def test_journey_stage_precedence_is_recovering_then_new_then_building(
    member_since: str,
    injuries: tuple[tuple[str, str], ...],
    workouts: tuple[tuple[str, bool], ...],
    expected_stage: JourneyStageName,
) -> None:
    journey_stage = derive_journey_stage(
        member_node_id="member:1",
        member_since=member_since,
        injuries=injuries,
        workout_sessions=workouts,
        as_of=date(2026, 8, 13),
    )

    assert journey_stage.stage == expected_stage
    assert journey_stage.evidence.member_node_id == "member:1"
    assert journey_stage.evidence.injury_node_ids == tuple(
        node_id for node_id, _ in injuries
    )
    assert journey_stage.evidence.workout_session_node_ids == tuple(
        node_id for node_id, _ in workouts
    )


def test_member_context_load_derives_journey_stage_and_scopes_stale_values() -> None:
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
