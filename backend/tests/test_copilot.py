import json
from dataclasses import is_dataclass
from datetime import date
from typing import Any, get_args, get_origin, get_type_hints

import pytest
from app.copilot.context import (
    COPILOT_TONE_FACT_LABELS,
    CopilotToneFact,
    get_copilot_tone_facts,
)
from app.copilot.tools import (
    BarrierData,
    ChatMessageData,
    ChatMessagesResult,
    CoachTaskData,
    GoalData,
    MemberGoalsResult,
    MemberInjuriesResult,
    MemberInjuryData,
    MemberProfileData,
    MemberProfileResult,
    MorningBriefData,
    MorningBriefResult,
    ObservationData,
    ObservationMeasurement,
    ObservationsResult,
    WorkoutSessionData,
    WorkoutSessionsResult,
    get_chat_messages,
    get_member_goals,
    get_member_injuries,
    get_member_profile,
    get_morning_brief,
    get_observations,
    get_workout_sessions,
)
from app.graph import ingest_kg2

DOMAIN_VALUE_TYPES = (
    ObservationMeasurement,
    ObservationData,
    ObservationsResult,
    WorkoutSessionData,
    WorkoutSessionsResult,
    ChatMessageData,
    ChatMessagesResult,
    GoalData,
    MemberGoalsResult,
    MemberInjuryData,
    MemberInjuriesResult,
    BarrierData,
    CoachTaskData,
    MorningBriefData,
    MorningBriefResult,
    MemberProfileData,
    MemberProfileResult,
    CopilotToneFact,
)

MEMBER_ID = "mbr_01HX9JORDAN"


@pytest.mark.parametrize("domain_value_type", DOMAIN_VALUE_TYPES)
def test_retrieval_tool_domain_values_are_frozen_dataclasses(
    domain_value_type: type[Any],
) -> None:
    assert is_dataclass(domain_value_type)
    assert domain_value_type.__dataclass_params__.frozen
    assert not any(
        _contains_list(annotation)
        for annotation in get_type_hints(domain_value_type).values()
    )


def test_retrieval_tool_result_serializes_as_typed_json() -> None:
    result = MemberGoalsResult(
        goals=(
            GoalData(
                node_id="goal:strength",
                external_id="strength",
                text="Build strength",
                priority=1,
                target_date=None,
            ),
        ),
        node_ids=("member:1", "goal:strength"),
    )

    assert json.loads(str(result)) == {
        "goals": [
            {
                "node_id": "goal:strength",
                "external_id": "strength",
                "text": "Build strength",
                "priority": 1,
                "target_date": None,
            }
        ],
        "node_ids": ["member:1", "goal:strength"],
    }


def test_observation_tool_scopes_windows_and_returns_stale_labs_with_age() -> None:
    ingest_kg2()

    result = get_observations.invoke(
        {"member_id": MEMBER_ID, "as_of": date(2026, 12, 10)}
    )

    assert isinstance(result, ObservationsResult)
    assert tuple(observation.kind for observation in result.observations) == (
        "blood-panel",
        "dexa",
    )
    assert tuple(observation.age_days for observation in result.observations) == (
        234,
        255,
    )
    assert all(observation.stale for observation in result.observations)
    assert result.node_ids == (
        MEMBER_ID,
        f"{MEMBER_ID}:observation:blood-panel:2026-04-20",
        f"{MEMBER_ID}:observation:dexa:2026-03-30",
    )


@pytest.mark.parametrize(
    ("retrieval_tool", "result_field", "expected_count"),
    [
        (get_observations, "observations", 2),
        (get_workout_sessions, "workout_sessions", 0),
        (get_chat_messages, "chat_messages", 4),
        (get_member_goals, "goals", 3),
        (get_member_injuries, "injuries", 1),
        (get_morning_brief, "morning_brief", 0),
        (get_member_profile, "profile", 1),
    ],
)
def test_each_retrieval_tool_applies_its_relevance_window(
    retrieval_tool: Any,
    result_field: str,
    expected_count: int,
) -> None:
    ingest_kg2()

    result = retrieval_tool.invoke(
        {"member_id": MEMBER_ID, "as_of": date(2026, 12, 10)}
    )

    value = getattr(result, result_field)
    actual_count = len(value) if isinstance(value, tuple) else int(value is not None)
    assert actual_count == expected_count
    assert result.node_ids[0] == MEMBER_ID


@pytest.mark.parametrize(
    "retrieval_tool",
    [
        get_observations,
        get_workout_sessions,
        get_chat_messages,
        get_member_goals,
        get_member_injuries,
        get_morning_brief,
        get_member_profile,
    ],
)
def test_each_retrieval_tool_returns_no_node_ids_for_unknown_member(
    retrieval_tool: Any,
) -> None:
    ingest_kg2()

    result = retrieval_tool.invoke(
        {"member_id": "unknown-member", "as_of": date(2026, 12, 10)}
    )

    assert result.node_ids == ()


def test_copilot_context_exposes_two_labeled_tone_facts() -> None:
    ingest_kg2()

    facts = get_copilot_tone_facts(MEMBER_ID, as_of=date(2026, 6, 4))

    assert (
        tuple(fact.label for fact in facts)
        == COPILOT_TONE_FACT_LABELS
        == (
            "Journey stage",
            "Churn risk",
        )
    )
    assert tuple(fact.value for fact in facts) == ("recovering", "elevated")
    assert all(fact.evidence_node_ids for fact in facts)


def _contains_list(annotation: Any) -> bool:
    return get_origin(annotation) is list or any(
        _contains_list(argument) for argument in get_args(annotation)
    )
