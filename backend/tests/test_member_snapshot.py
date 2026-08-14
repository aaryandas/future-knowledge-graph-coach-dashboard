from datetime import date

from app.api.member_snapshot import create_member_snapshot_router
from app.graph import (
    CoachTaskView,
    GoalView,
    JourneyStage,
    JourneyStageEvidence,
    MemberContext,
    MemberInjuryView,
    MemberProfile,
    MorningBrief,
    ObservationKind,
    ObservationView,
    WorkoutSessionView,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

MEMBER_ID = "mbr_01HX9JORDAN"


def _member_context(member_id: str) -> MemberContext | None:
    if member_id != MEMBER_ID:
        return None
    observations = (
        _observation("adherence-week", "2026-06-02", 50, age_days=72, stale=True),
        _observation("adherence-week", "2026-05-26", 75, age_days=79, stale=True),
        _observation("adherence-week", "2026-05-19", 100, age_days=86, stale=True),
        _observation("adherence-week", "2026-05-12", 100, age_days=93, stale=True),
        *(
            _observation(
                "sleep-night", observed_at, value, age_days=age_days, stale=True
            )
            for observed_at, value, age_days in (
                ("2026-05-28", 6.1, 77),
                ("2026-05-29", 5.4, 76),
                ("2026-05-30", 7.2, 75),
                ("2026-05-31", 6.0, 74),
                ("2026-06-01", 5.1, 73),
                ("2026-06-02", 7.8, 72),
                ("2026-06-03", 6.3, 71),
            )
        ),
    )
    workouts = (
        _workout("2026-06-03", completed=True),
        _workout("2026-06-01", completed=True),
        _workout("2026-05-29", completed=False),
        _workout("2026-05-27", completed=True),
    )
    return MemberContext(
        profile=MemberProfile(
            node_id=MEMBER_ID,
            name="Jordan Rivera",
            age=41,
            sex="female",
            height_cm=168,
            weight_kg=71.2,
            timezone="America/Los_Angeles",
            member_since="2024-09-15",
            coach_id="coach_01HXSAM",
            tier="1:1 Coaching",
            preferred_session_minutes=30,
            training_days_per_week=4,
            preferred_days=("Monday", "Tuesday", "Thursday", "Saturday"),
            preference_notes="",
            equipment_available=(),
            dislikes=(),
            equipment_node_ids=(),
            exercise_node_ids=(),
        ),
        journey_stage=JourneyStage(
            stage="recovering",
            evidence=JourneyStageEvidence(
                member_node_id=MEMBER_ID,
                member_since="2024-09-15",
                tenure_days=697,
                injury_node_ids=(f"{MEMBER_ID}:injury:inj_knee_left",),
                injury_statuses=("recovering",),
                workout_session_node_ids=tuple(workout.node_id for workout in workouts),
                workout_session_count=4,
                completed_workout_count=3,
            ),
        ),
        goals=(
            GoalView(
                node_id=f"{MEMBER_ID}:goal:goal_strength",
                external_id="goal_strength",
                text="Build lower-body strength",
                priority=1,
                target_date="2026-09-01",
            ),
        ),
        injuries=(
            MemberInjuryView(
                node_id=f"{MEMBER_ID}:injury:inj_knee_left",
                external_id="inj_knee_left",
                region="left knee",
                joint="knee",
                status="recovering",
                severity="mild",
                since="2026-05-10",
                notes="",
                snomedct_hint=None,
                clinical_finding_mentions=("patellofemoral pain syndrome",),
                clinical_finding_ids=("snomedct:430725003",),
            ),
        ),
        workout_sessions=workouts,
        observations=observations,
        chat_messages=(),
        morning_brief=MorningBrief(
            generated_for="2026-06-04",
            churn_risk_level="elevated",
            churn_risk_reasons=("one", "two", "three"),
            barriers=(),
            coach_tasks=(
                CoachTaskView(
                    node_id=f"{MEMBER_ID}:coach-task:celebrate",
                    generated_for="2026-06-04",
                    type="celebrate",
                    text="Congratulate Jordan on yesterday's session.",
                    status="open",
                    addressed_node_ids=(workouts[0].node_id,),
                ),
                CoachTaskView(
                    node_id=f"{MEMBER_ID}:coach-task:risk",
                    generated_for="2026-06-04",
                    type="review_risk",
                    text="Check churn risk.",
                    status="open",
                    addressed_node_ids=(),
                ),
            ),
        ),
    )


def _observation(
    kind: ObservationKind,
    observed_at: str,
    value: float,
    *,
    age_days: int,
    stale: bool,
) -> ObservationView:
    return ObservationView(
        node_id=f"{MEMBER_ID}:observation:{kind}:{observed_at}",
        kind=kind,
        observed_at=observed_at,
        age_days=age_days,
        stale=stale,
        value=value,
        unit=None,
        measurements=(),
    )


def _workout(observed_at: str, *, completed: bool) -> WorkoutSessionView:
    return WorkoutSessionView(
        node_id=f"{MEMBER_ID}:workout:{observed_at}",
        date=observed_at,
        title="Workout",
        planned=True,
        completed=completed,
        duration_min=30 if completed else 0,
        rpe=6 if completed else None,
        exercise_mentions=(),
        exercise_ids=(),
    )


def _client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(
        create_member_snapshot_router(
            _member_context,
            date_reader=lambda: date(2026, 8, 13),
        )
    )
    return TestClient(test_app)


def test_member_snapshot_returns_identity_stats_brief_and_journey_stage() -> None:
    response = _client().get(f"/api/members/{MEMBER_ID}/snapshot")

    assert response.status_code == 200
    part = response.json()
    assert part["type"] == "data-member-snapshot"
    assert part["identity"] == {
        "name": "Jordan Rivera",
        "tier": "1:1 Coaching",
        "age": 41,
        "sex": "female",
        "member_since": "2024-09-15",
        "tenure_days": 697,
        "injury": {
            "id": f"{MEMBER_ID}:injury:inj_knee_left",
            "region": "left knee",
            "finding": "patellofemoral pain syndrome",
            "status": "recovering",
        },
        "goals": [
            {
                "id": f"{MEMBER_ID}:goal:goal_strength",
                "text": "Build lower-body strength",
            }
        ],
    }
    assert part["stats"] == {
        "adherence": {
            "value": 50.0,
            "suffix": "%",
            "trend": "down",
            "trend_text": "from 100% · 3 wks",
            "source": {
                "observed_at": "2026-06-02",
                "age_days": 72,
                "stale": True,
            },
        },
        "sleep": {
            "value": 6.3,
            "suffix": "/ 7 h",
            "trend": "neutral",
            "trend_text": "No prior period",
            "source": {
                "observed_at": "2026-06-03",
                "age_days": 71,
                "stale": True,
            },
        },
        "sessions": {
            "value": 2,
            "suffix": "/ 4",
            "trend": "up",
            "trend_text": "from 1 last wk",
            "source": {
                "observed_at": "2026-06-03",
                "age_days": 71,
                "stale": True,
            },
        },
        "churn_risk": {
            "value": "elevated",
            "suffix": None,
            "trend": "neutral",
            "trend_text": "3 signals",
            "source": {
                "observed_at": "2026-06-04",
                "age_days": 70,
                "stale": True,
            },
        },
    }
    assert len(part["morning_brief"]["coach_tasks"]) == 2
    assert part["morning_brief"]["source"]["age_days"] == 70
    assert part["journey_stage"]["stage"] == "recovering"
    assert part["journey_stage"]["evidence"]["completed_workout_count"] == 3


def test_member_snapshot_returns_404_for_unknown_member() -> None:
    response = _client().get("/api/members/unknown/snapshot")

    assert response.status_code == 404
    assert response.json() == {"detail": "Member not found"}
