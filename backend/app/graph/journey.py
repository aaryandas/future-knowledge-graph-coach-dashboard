from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.graph.constants import (
    NEW_MEMBER_MAX_TENURE_DAYS,
    NEW_MEMBER_MIN_COMPLETED_WORKOUTS,
    RECOVERING_INJURY_STATUSES,
)

type JourneyStageName = Literal["new", "building", "recovering"]


@dataclass(frozen=True)
class JourneyStageEvidence:
    member_node_id: str
    member_since: str
    tenure_days: int
    injury_node_ids: tuple[str, ...]
    injury_statuses: tuple[str, ...]
    workout_session_node_ids: tuple[str, ...]
    workout_session_count: int
    completed_workout_count: int


@dataclass(frozen=True)
class JourneyStage:
    stage: JourneyStageName
    evidence: JourneyStageEvidence


def derive_journey_stage(
    *,
    member_node_id: str,
    member_since: str,
    injuries: tuple[tuple[str, str], ...],
    workout_sessions: tuple[tuple[str, bool], ...],
    as_of: date,
) -> JourneyStage:
    tenure_days = max(0, (as_of - date.fromisoformat(member_since)).days)
    injury_node_ids = tuple(node_id for node_id, _ in injuries)
    injury_statuses = tuple(status for _, status in injuries)
    workout_session_node_ids = tuple(node_id for node_id, _ in workout_sessions)
    completed_workout_count = sum(completed for _, completed in workout_sessions)

    if any(status in RECOVERING_INJURY_STATUSES for status in injury_statuses):
        stage: JourneyStageName = "recovering"
    elif (
        tenure_days <= NEW_MEMBER_MAX_TENURE_DAYS
        or completed_workout_count < NEW_MEMBER_MIN_COMPLETED_WORKOUTS
    ):
        stage = "new"
    else:
        stage = "building"

    return JourneyStage(
        stage=stage,
        evidence=JourneyStageEvidence(
            member_node_id=member_node_id,
            member_since=member_since,
            tenure_days=tenure_days,
            injury_node_ids=injury_node_ids,
            injury_statuses=injury_statuses,
            workout_session_node_ids=workout_session_node_ids,
            workout_session_count=len(workout_sessions),
            completed_workout_count=completed_workout_count,
        ),
    )
