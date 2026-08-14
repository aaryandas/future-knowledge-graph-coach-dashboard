from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

type ObservationKind = Literal[
    "sleep-night",
    "adherence-week",
    "message-pattern-day",
    "resting-hr",
    "hrv",
    "weight",
    "blood-panel",
    "dexa",
]


@dataclass(frozen=True)
class RelevanceWindow:
    days: int | None
    latest_value: bool
    stale_after_days: int


OBSERVATION_RELEVANCE_WINDOWS: Final[Mapping[ObservationKind, RelevanceWindow]] = (
    MappingProxyType(
        {
            "sleep-night": RelevanceWindow(
                days=7, latest_value=False, stale_after_days=7
            ),
            "adherence-week": RelevanceWindow(
                days=28, latest_value=False, stale_after_days=28
            ),
            "message-pattern-day": RelevanceWindow(
                days=28, latest_value=False, stale_after_days=28
            ),
            "resting-hr": RelevanceWindow(
                days=30, latest_value=False, stale_after_days=30
            ),
            "hrv": RelevanceWindow(days=30, latest_value=False, stale_after_days=30),
            "weight": RelevanceWindow(days=90, latest_value=False, stale_after_days=90),
            "blood-panel": RelevanceWindow(
                days=None, latest_value=True, stale_after_days=180
            ),
            "dexa": RelevanceWindow(days=None, latest_value=True, stale_after_days=180),
        }
    )
)

NEW_MEMBER_MAX_TENURE_DAYS: Final = 30
NEW_MEMBER_MIN_COMPLETED_WORKOUTS: Final = 4
RECOVERING_INJURY_STATUSES: Final = frozenset({"active", "recovering"})
