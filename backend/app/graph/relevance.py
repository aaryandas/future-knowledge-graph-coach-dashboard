from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Final, Literal, Protocol, cast

from app.graph.constants import (
    OBSERVATION_RELEVANCE_WINDOWS,
    ObservationKind,
)

type RelevanceWindowName = Literal["7-days", "28-days"]

RELEVANCE_WINDOW_DAYS: Final = MappingProxyType({"7-days": 7, "28-days": 28})


@dataclass(frozen=True)
class ObservationStaleness:
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


def observation_staleness(
    kind: ObservationKind,
    observed_at: str,
    *,
    as_of: date,
) -> ObservationStaleness:
    observed_on = _observed_date(observed_at)
    age_days = max(0, (as_of - observed_on).days)
    window = OBSERVATION_RELEVANCE_WINDOWS[kind]
    return ObservationStaleness(
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


def scope_relevance_window[T](
    values: Iterable[T],
    *,
    kind: ObservationKind | None = None,
    window: RelevanceWindowName | None = None,
    observed_at: Callable[[T], str | None],
    as_of: date,
) -> tuple[T, ...]:
    values = tuple(values)
    if kind is not None and window is not None:
        raise ValueError("A relevance read cannot select both kind and window")
    if kind is None and window is None:
        return values
    relevance_window = OBSERVATION_RELEVANCE_WINDOWS[kind] if kind is not None else None
    if relevance_window is not None and relevance_window.latest_value:
        return values[:1]
    stale_after_days = (
        relevance_window.stale_after_days
        if relevance_window is not None
        else RELEVANCE_WINDOW_DAYS[cast(RelevanceWindowName, window)]
    )
    return tuple(
        value
        for value in values
        if (value_observed_at := observed_at(value)) is not None
        and _age_days(value_observed_at, as_of=as_of) <= stale_after_days
    )


def _observed_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value).date()


def _age_days(observed_at: str, *, as_of: date) -> int:
    return max(0, (as_of - _observed_date(observed_at)).days)
