from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal

from langchain_core.tools import BaseTool, tool

from app.graph import (
    BarrierView,
    ChatMessageView,
    CoachTaskView,
    GoalView,
    MemberInjuryView,
    MemberProfile,
    MorningBrief,
    ObservationKind,
    ObservationView,
    WorkoutSessionView,
)
from app.graph import (
    get_chat_messages as read_chat_messages,
)
from app.graph import (
    get_member_goals as read_member_goals,
)
from app.graph import (
    get_member_injuries as read_member_injuries,
)
from app.graph import (
    get_member_node_id as read_member_node_id,
)
from app.graph import (
    get_member_profile as read_member_profile,
)
from app.graph import (
    get_morning_brief as read_morning_brief,
)
from app.graph import (
    get_observations as read_observations,
)
from app.graph import (
    get_workout_sessions as read_workout_sessions,
)

type ObservationScalar = str | int | float | bool
type ChatSender = Literal["member", "coach"]


@dataclass(frozen=True)
class _JsonToolResult:
    def __str__(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass(frozen=True)
class ObservationMeasurement:
    name: str
    value: ObservationScalar


@dataclass(frozen=True)
class ObservationData:
    node_id: str
    kind: ObservationKind
    observed_at: str
    age_days: int
    stale: bool
    value: int | float | None
    unit: str | None
    measurements: tuple[ObservationMeasurement, ...]


@dataclass(frozen=True)
class ObservationsResult(_JsonToolResult):
    observations: tuple[ObservationData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkoutSessionData:
    node_id: str
    date: str
    title: str
    planned: bool
    completed: bool
    duration_min: int
    rpe: int | float | None
    exercise_mentions: tuple[str, ...]
    exercise_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkoutSessionsResult(_JsonToolResult):
    workout_sessions: tuple[WorkoutSessionData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChatMessageData:
    node_id: str
    timestamp: str
    sender: ChatSender
    text: str
    attachments_json: str | None


@dataclass(frozen=True)
class ChatMessagesResult(_JsonToolResult):
    chat_messages: tuple[ChatMessageData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class GoalData:
    node_id: str
    external_id: str
    text: str
    priority: int
    target_date: str | None


@dataclass(frozen=True)
class MemberGoalsResult(_JsonToolResult):
    goals: tuple[GoalData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemberInjuryData:
    node_id: str
    external_id: str
    region: str
    joint: str
    status: str
    severity: str
    since: str
    notes: str
    snomedct_hint: str | None
    clinical_finding_mentions: tuple[str, ...]
    clinical_finding_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemberInjuriesResult(_JsonToolResult):
    injuries: tuple[MemberInjuryData, ...]
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class BarrierData:
    node_id: str
    kind: str
    copper_id: str
    reason: str
    risk_level: str
    evidence_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class CoachTaskData:
    node_id: str
    generated_for: str
    type: str
    text: str
    status: str
    addressed_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MorningBriefData:
    generated_for: str
    churn_risk_level: str
    churn_risk_reasons: tuple[str, ...]
    barriers: tuple[BarrierData, ...]
    coach_tasks: tuple[CoachTaskData, ...]


@dataclass(frozen=True)
class MorningBriefResult(_JsonToolResult):
    morning_brief: MorningBriefData | None
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemberProfileData:
    node_id: str
    name: str
    age: int
    sex: str
    height_cm: int | float
    weight_kg: int | float
    timezone: str
    member_since: str
    coach_id: str
    tier: str
    preferred_session_minutes: int
    training_days_per_week: int
    preferred_days: tuple[str, ...]
    preference_notes: str
    equipment_available: tuple[str, ...]
    dislikes: tuple[str, ...]


@dataclass(frozen=True)
class MemberProfileResult(_JsonToolResult):
    profile: MemberProfileData | None
    node_ids: tuple[str, ...]


@tool
def get_observations(member_id: str, as_of: date | None = None) -> ObservationsResult:
    """Read current `Member -[:observed]-> Observation` values and latest labs, newest first."""
    member_node_id = read_member_node_id(member_id)
    if member_node_id is None:
        return ObservationsResult(observations=(), node_ids=())
    observations = read_observations(member_id, as_of=as_of)
    return ObservationsResult(
        observations=tuple(
            _observation_data(observation) for observation in observations
        ),
        node_ids=_node_ids(
            member_node_id, (observation.node_id for observation in observations)
        ),
    )


@tool
def get_workout_sessions(
    member_id: str, as_of: date | None = None
) -> WorkoutSessionsResult:
    """Read current-adherence-window `Member -[:performed]-> WorkoutSession -[:included]-> Exercise`."""
    member_node_id = read_member_node_id(member_id)
    if member_node_id is None:
        return WorkoutSessionsResult(workout_sessions=(), node_ids=())
    workout_sessions = read_workout_sessions(member_id, as_of=as_of)
    return WorkoutSessionsResult(
        workout_sessions=tuple(
            _workout_session_data(workout) for workout in workout_sessions
        ),
        node_ids=_node_ids(
            member_node_id,
            (workout.node_id for workout in workout_sessions),
            (
                exercise_node_id
                for workout in workout_sessions
                for exercise_node_id in workout.exercise_ids
            ),
        ),
    )


@tool
def get_chat_messages(member_id: str, as_of: date | None = None) -> ChatMessagesResult:
    """Read `Member -[:said|received]-> ChatMessage`, newest first; chat has no relevance window."""
    member_node_id = read_member_node_id(member_id)
    if member_node_id is None:
        return ChatMessagesResult(chat_messages=(), node_ids=())
    chat_messages = read_chat_messages(member_id)
    return ChatMessagesResult(
        chat_messages=tuple(_chat_message_data(message) for message in chat_messages),
        node_ids=_node_ids(
            member_node_id,
            (message.node_id for message in chat_messages),
        ),
    )


@tool
def get_member_goals(member_id: str, as_of: date | None = None) -> MemberGoalsResult:
    """Read current `Member -[:pursues]-> Goal` records, highest priority first."""
    member_node_id = read_member_node_id(member_id)
    if member_node_id is None:
        return MemberGoalsResult(goals=(), node_ids=())
    goals = read_member_goals(member_id)
    return MemberGoalsResult(
        goals=tuple(_goal_data(goal) for goal in goals),
        node_ids=_node_ids(
            member_node_id,
            (goal.node_id for goal in goals),
        ),
    )


@tool
def get_member_injuries(
    member_id: str, as_of: date | None = None
) -> MemberInjuriesResult:
    """Read current `Member -[:has]-> MemberInjury -[:exactMatch]-> ClinicalFinding` records."""
    member_node_id = read_member_node_id(member_id)
    if member_node_id is None:
        return MemberInjuriesResult(injuries=(), node_ids=())
    injuries = read_member_injuries(member_id)
    return MemberInjuriesResult(
        injuries=tuple(_member_injury_data(injury) for injury in injuries),
        node_ids=_node_ids(
            member_node_id,
            (injury.node_id for injury in injuries),
            (
                finding_node_id
                for injury in injuries
                for finding_node_id in injury.clinical_finding_ids
            ),
        ),
    )


@tool
def get_morning_brief(member_id: str, as_of: date | None = None) -> MorningBriefResult:
    """Read the current-adherence-window brief through `addresses` and `evidencedBy`."""
    member_node_id = read_member_node_id(member_id)
    if member_node_id is None:
        return MorningBriefResult(morning_brief=None, node_ids=())
    morning_brief = read_morning_brief(member_id, as_of=as_of)
    if morning_brief is None:
        return MorningBriefResult(morning_brief=None, node_ids=(member_node_id,))
    return MorningBriefResult(
        morning_brief=_morning_brief_data(morning_brief),
        node_ids=_node_ids(
            member_node_id,
            (task.node_id for task in morning_brief.coach_tasks),
            (
                addressed_node_id
                for task in morning_brief.coach_tasks
                for addressed_node_id in task.addressed_node_ids
            ),
            (barrier.node_id for barrier in morning_brief.barriers),
            (
                evidence_node_id
                for barrier in morning_brief.barriers
                for evidence_node_id in barrier.evidence_node_ids
            ),
        ),
    )


@tool
def get_member_profile(
    member_id: str, as_of: date | None = None
) -> MemberProfileResult:
    """Read `Member -[:owns]-> Equipment` and `Member -[:dislikes]-> Exercise` with the Member profile."""
    profile = read_member_profile(member_id)
    if profile is None:
        return MemberProfileResult(profile=None, node_ids=())
    return MemberProfileResult(
        profile=_member_profile_data(profile),
        node_ids=_node_ids(
            profile.node_id,
            profile.equipment_node_ids,
            profile.exercise_node_ids,
        ),
    )


RETRIEVAL_TOOLS: tuple[BaseTool, ...] = (
    get_observations,
    get_workout_sessions,
    get_chat_messages,
    get_member_goals,
    get_member_injuries,
    get_morning_brief,
    get_member_profile,
)


def _observation_data(observation: ObservationView) -> ObservationData:
    return ObservationData(
        node_id=observation.node_id,
        kind=observation.kind,
        observed_at=observation.observed_at,
        age_days=observation.age_days,
        stale=observation.stale,
        value=observation.value,
        unit=observation.unit,
        measurements=tuple(
            ObservationMeasurement(name=value.name, value=value.value)
            for value in observation.measurements
        ),
    )


def _workout_session_data(workout: WorkoutSessionView) -> WorkoutSessionData:
    return WorkoutSessionData(
        node_id=workout.node_id,
        date=workout.date,
        title=workout.title,
        planned=workout.planned,
        completed=workout.completed,
        duration_min=workout.duration_min,
        rpe=workout.rpe,
        exercise_mentions=workout.exercise_mentions,
        exercise_ids=workout.exercise_ids,
    )


def _chat_message_data(message: ChatMessageView) -> ChatMessageData:
    if message.sender not in ("member", "coach"):
        raise ValueError(
            f"ChatMessage {message.node_id} has unsupported sender {message.sender}"
        )
    return ChatMessageData(
        node_id=message.node_id,
        timestamp=message.timestamp,
        sender=message.sender,
        text=message.text,
        attachments_json=message.attachments_json,
    )


def _goal_data(goal: GoalView) -> GoalData:
    return GoalData(
        node_id=goal.node_id,
        external_id=goal.external_id,
        text=goal.text,
        priority=goal.priority,
        target_date=goal.target_date,
    )


def _member_injury_data(injury: MemberInjuryView) -> MemberInjuryData:
    return MemberInjuryData(
        node_id=injury.node_id,
        external_id=injury.external_id,
        region=injury.region,
        joint=injury.joint,
        status=injury.status,
        severity=injury.severity,
        since=injury.since,
        notes=injury.notes,
        snomedct_hint=injury.snomedct_hint,
        clinical_finding_mentions=injury.clinical_finding_mentions,
        clinical_finding_ids=injury.clinical_finding_ids,
    )


def _member_profile_data(profile: MemberProfile) -> MemberProfileData:
    return MemberProfileData(
        node_id=profile.node_id,
        name=profile.name,
        age=profile.age,
        sex=profile.sex,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        timezone=profile.timezone,
        member_since=profile.member_since,
        coach_id=profile.coach_id,
        tier=profile.tier,
        preferred_session_minutes=profile.preferred_session_minutes,
        training_days_per_week=profile.training_days_per_week,
        preferred_days=profile.preferred_days,
        preference_notes=profile.preference_notes,
        equipment_available=profile.equipment_available,
        dislikes=profile.dislikes,
    )


def _morning_brief_data(morning_brief: MorningBrief) -> MorningBriefData:
    return MorningBriefData(
        generated_for=morning_brief.generated_for,
        churn_risk_level=morning_brief.churn_risk_level,
        churn_risk_reasons=morning_brief.churn_risk_reasons,
        barriers=tuple(_barrier_data(barrier) for barrier in morning_brief.barriers),
        coach_tasks=tuple(_coach_task_data(task) for task in morning_brief.coach_tasks),
    )


def _barrier_data(barrier: BarrierView) -> BarrierData:
    return BarrierData(
        node_id=barrier.node_id,
        kind=barrier.kind,
        copper_id=barrier.copper_id,
        reason=barrier.reason,
        risk_level=barrier.risk_level,
        evidence_node_ids=barrier.evidence_node_ids,
    )


def _coach_task_data(task: CoachTaskView) -> CoachTaskData:
    return CoachTaskData(
        node_id=task.node_id,
        generated_for=task.generated_for,
        type=task.type,
        text=task.text,
        status=task.status,
        addressed_node_ids=task.addressed_node_ids,
    )


def _node_ids(
    member_node_id: str | None,
    *node_id_groups: Iterable[str],
) -> tuple[str, ...]:
    node_ids: list[str] = []
    seen: set[str] = set()
    for node_id in () if member_node_id is None else (member_node_id,):
        seen.add(node_id)
        node_ids.append(node_id)
    for group in node_id_groups:
        for node_id in group:
            if node_id in seen:
                continue
            seen.add(node_id)
            node_ids.append(node_id)
    return tuple(node_ids)
