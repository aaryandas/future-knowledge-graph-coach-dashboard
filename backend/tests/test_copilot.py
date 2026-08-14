import json
from dataclasses import is_dataclass
from typing import Any, get_args, get_origin, get_type_hints

import pytest
from app.copilot import (
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
)

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
)


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


def _contains_list(annotation: Any) -> bool:
    return get_origin(annotation) is list or any(
        _contains_list(argument) for argument in get_args(annotation)
    )
