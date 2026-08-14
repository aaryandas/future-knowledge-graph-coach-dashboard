from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.graph import (
    MemberContext,
    ObservationKind,
    ObservationView,
    get_member_context,
)


class SnapshotSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    observed_at: str
    age_days: int
    stale: bool


class SnapshotStat(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str | int | float | None
    suffix: str | None
    trend: Literal["up", "down", "flat", "neutral"]
    trend_text: str
    source: SnapshotSource | None


class MemberIdentityGoal(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str


class MemberIdentityInjury(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    region: str
    finding: str | None
    status: str


class MemberIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    tier: str
    age: int
    sex: str
    member_since: str
    tenure_days: int
    injury: MemberIdentityInjury | None
    goals: list[MemberIdentityGoal]


class MemberSnapshotStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    adherence: SnapshotStat
    sleep: SnapshotStat
    sessions: SnapshotStat
    churn_risk: SnapshotStat


class CoachTaskSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    status: str


class MorningBriefSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_for: str
    source: SnapshotSource
    coach_tasks: list[CoachTaskSnapshot]


class JourneyStageEvidenceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_since: str
    tenure_days: int
    injury_node_ids: list[str]
    injury_statuses: list[str]
    workout_session_node_ids: list[str]
    workout_session_count: int
    completed_workout_count: int


class JourneyStageSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: Literal["new", "building", "recovering"]
    evidence: JourneyStageEvidenceSnapshot


class MemberSnapshotPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-member-snapshot"] = "data-member-snapshot"
    member_id: str
    identity: MemberIdentity
    stats: MemberSnapshotStats
    morning_brief: MorningBriefSnapshot
    journey_stage: JourneyStageSnapshot


type MemberContextReader = Callable[[str], MemberContext | None]
type DateReader = Callable[[], date]


def create_member_snapshot_router(
    context_reader: MemberContextReader = get_member_context,
    date_reader: DateReader = lambda: datetime.now(UTC).date(),
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get(
        "/members/{member_id}/snapshot",
        response_model=MemberSnapshotPart,
        summary="Read a member snapshot",
        description=(
            "Reads Member → pursues|has|performed|observed, CoachTask → addresses, "
            "and Barrier → evidencedBy through get_member_context(member_id)."
        ),
    )
    def member_snapshot(member_id: str) -> MemberSnapshotPart:
        context = context_reader(member_id)
        if context is None:
            raise HTTPException(status_code=404, detail="Member not found")
        return _member_snapshot_part(context, as_of=date_reader())

    return router


def _member_snapshot_part(context: MemberContext, *, as_of: date) -> MemberSnapshotPart:
    evidence = context.journey_stage.evidence
    injury = next(
        (
            value
            for value in context.injuries
            if value.status in {"active", "recovering"}
        ),
        context.injuries[0] if context.injuries else None,
    )
    brief_source = _dated_source(
        context.morning_brief.generated_for,
        as_of=as_of,
        stale_after_days=0,
    )
    return MemberSnapshotPart(
        member_id=context.profile.node_id,
        identity=MemberIdentity(
            name=context.profile.name,
            tier=context.profile.tier,
            age=context.profile.age,
            sex=context.profile.sex,
            member_since=context.profile.member_since,
            tenure_days=evidence.tenure_days,
            injury=(
                None
                if injury is None
                else MemberIdentityInjury(
                    id=injury.node_id,
                    region=injury.region,
                    finding=(
                        injury.clinical_finding_mentions[0]
                        if injury.clinical_finding_mentions
                        else None
                    ),
                    status=injury.status,
                )
            ),
            goals=[
                MemberIdentityGoal(id=goal.node_id, text=goal.text)
                for goal in context.goals
            ],
        ),
        stats=MemberSnapshotStats(
            adherence=_adherence_stat(context.observations),
            sleep=_sleep_stat(context.observations),
            sessions=_sessions_stat(context, as_of=as_of),
            churn_risk=SnapshotStat(
                value=context.morning_brief.churn_risk_level,
                suffix=None,
                trend="neutral",
                trend_text=(f"{len(context.morning_brief.churn_risk_reasons)} signals"),
                source=brief_source,
            ),
        ),
        morning_brief=MorningBriefSnapshot(
            generated_for=context.morning_brief.generated_for,
            source=brief_source,
            coach_tasks=[
                CoachTaskSnapshot(id=task.node_id, text=task.text, status=task.status)
                for task in context.morning_brief.coach_tasks
            ],
        ),
        journey_stage=JourneyStageSnapshot(
            stage=context.journey_stage.stage,
            evidence=JourneyStageEvidenceSnapshot(
                member_since=evidence.member_since,
                tenure_days=evidence.tenure_days,
                injury_node_ids=list(evidence.injury_node_ids),
                injury_statuses=list(evidence.injury_statuses),
                workout_session_node_ids=list(evidence.workout_session_node_ids),
                workout_session_count=evidence.workout_session_count,
                completed_workout_count=evidence.completed_workout_count,
            ),
        ),
    )


def _adherence_stat(observations: tuple[ObservationView, ...]) -> SnapshotStat:
    values = _observations_of_kind(observations, "adherence-week")
    if not values:
        return _unavailable_stat()
    latest = values[0]
    latest_value = latest.value
    if latest_value is None:
        return _unavailable_stat()
    if len(values) == 1:
        return SnapshotStat(
            value=latest_value,
            suffix="%",
            trend="neutral",
            trend_text="No prior period",
            source=_observation_source(latest),
        )
    prior = values[-1]
    prior_value = prior.value
    if prior_value is None:
        return SnapshotStat(
            value=latest_value,
            suffix="%",
            trend="neutral",
            trend_text="No prior period",
            source=_observation_source(latest),
        )
    weeks = max(
        1,
        round(
            (
                date.fromisoformat(latest.observed_at)
                - date.fromisoformat(prior.observed_at)
            ).days
            / 7
        ),
    )
    return SnapshotStat(
        value=latest_value,
        suffix="%",
        trend=_trend(latest_value - prior_value),
        trend_text=f"from {_compact_number(prior_value)}% · {weeks} wks",
        source=_observation_source(latest),
    )


def _sleep_stat(observations: tuple[ObservationView, ...]) -> SnapshotStat:
    values = _observations_of_kind(observations, "sleep-night")
    if not values:
        return _unavailable_stat()
    anchor = date.fromisoformat(values[0].observed_at)
    current_start = anchor - timedelta(days=6)
    prior_start = current_start - timedelta(days=7)
    current = tuple(
        observation
        for observation in values
        if current_start <= date.fromisoformat(observation.observed_at) <= anchor
    )
    prior = tuple(
        observation
        for observation in values
        if prior_start <= date.fromisoformat(observation.observed_at) < current_start
    )
    average = _observation_average(current)
    if average is None:
        return _unavailable_stat()
    prior_average = _observation_average(prior)
    return SnapshotStat(
        value=average,
        suffix="/ 7 h",
        trend=("neutral" if prior_average is None else _trend(average - prior_average)),
        trend_text=(
            "No prior period"
            if prior_average is None
            else f"from {_compact_number(prior_average)} h · prior 7d"
        ),
        source=_observation_source(values[0]),
    )


def _sessions_stat(context: MemberContext, *, as_of: date) -> SnapshotStat:
    anchor = date.fromisoformat(context.morning_brief.generated_for)
    week_start = anchor - timedelta(days=6)
    prior_week_start = week_start - timedelta(days=7)
    sessions = tuple(
        workout
        for workout in context.workout_sessions
        if week_start <= date.fromisoformat(workout.date) <= anchor
    )
    prior_sessions = tuple(
        workout
        for workout in context.workout_sessions
        if prior_week_start <= date.fromisoformat(workout.date) < week_start
    )
    completed = sum(workout.completed for workout in sessions)
    prior_completed = sum(workout.completed for workout in prior_sessions)
    target = context.profile.training_days_per_week
    latest = max(sessions, key=lambda workout: workout.date, default=None)
    return SnapshotStat(
        value=completed,
        suffix=f"/ {target}",
        trend=(
            "neutral" if not prior_sessions else _trend(completed - prior_completed)
        ),
        trend_text=(
            "No prior period"
            if not prior_sessions
            else f"from {prior_completed} last wk"
        ),
        source=(
            None
            if latest is None
            else _dated_source(latest.date, as_of=as_of, stale_after_days=7)
        ),
    )


def _observations_of_kind(
    observations: tuple[ObservationView, ...], kind: ObservationKind
) -> tuple[ObservationView, ...]:
    return tuple(
        sorted(
            (observation for observation in observations if observation.kind == kind),
            key=lambda observation: observation.observed_at,
            reverse=True,
        )
    )


def _observation_source(observation: ObservationView) -> SnapshotSource:
    return SnapshotSource(
        observed_at=observation.observed_at,
        age_days=observation.age_days,
        stale=observation.stale,
    )


def _observation_average(observations: tuple[ObservationView, ...]) -> float | None:
    measured = [
        value
        for observation in observations
        if (value := observation.value) is not None
    ]
    return None if not measured else round(sum(measured) / len(measured), 1)


def _dated_source(
    observed_at: str, *, as_of: date, stale_after_days: int
) -> SnapshotSource:
    age_days = max(0, (as_of - date.fromisoformat(observed_at)).days)
    return SnapshotSource(
        observed_at=observed_at,
        age_days=age_days,
        stale=age_days > stale_after_days,
    )


def _unavailable_stat() -> SnapshotStat:
    return SnapshotStat(
        value=None,
        suffix=None,
        trend="neutral",
        trend_text="Unavailable",
        source=None,
    )


def _trend(delta: float) -> Literal["up", "down", "flat"]:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _compact_number(value: float) -> str:
    return f"{value:g}"


router = create_member_snapshot_router()
