from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol, cast

from app.graph.constants import (
    OBSERVATION_RELEVANCE_WINDOWS,
    ObservationKind,
)


@dataclass(frozen=True)
class ObservationFreshness:
    age_days: int
    stale: bool


class RelevanceScopedObservation(Protocol):
    @property
    def kind(self) -> ObservationKind: ...

    @property
    def stale(self) -> bool: ...


def current_date() -> date:
    return datetime.now(UTC).date()


def as_observation_kind(value: str) -> ObservationKind:
    if value not in OBSERVATION_RELEVANCE_WINDOWS:
        raise ValueError(f"Observation has unsupported kind {value}")
    return cast(ObservationKind, value)


def observation_freshness(
    kind: ObservationKind,
    observed_at: str,
    *,
    as_of: date,
) -> ObservationFreshness:
    observed_on = _observed_date(observed_at)
    age_days = max(0, (as_of - observed_on).days)
    window = OBSERVATION_RELEVANCE_WINDOWS[kind]
    return ObservationFreshness(
        age_days=age_days,
        stale=age_days > window.stale_after_days,
    )


def scope_observations[T: RelevanceScopedObservation](
    observations: Iterable[T],
) -> tuple[T, ...]:
    scoped: list[T] = []
    latest_value_kinds: set[ObservationKind] = set()
    for observation in observations:
        window = OBSERVATION_RELEVANCE_WINDOWS[observation.kind]
        if window.latest_value:
            if observation.kind in latest_value_kinds:
                continue
            latest_value_kinds.add(observation.kind)
            scoped.append(observation)
        elif not observation.stale:
            scoped.append(observation)
    return tuple(scoped)


def _observed_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value).date()
