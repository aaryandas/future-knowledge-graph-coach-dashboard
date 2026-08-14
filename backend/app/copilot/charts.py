from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Literal, cast

from langchain_core.tools import tool

from app.graph import (
    ObservationKind,
    ObservationView,
    RelevanceWindowName,
    get_member_node_id,
    get_observations,
    scope_relevance_window,
)

type ChartKind = Literal[
    "adherence_trend",
    "sleep_week",
    "message_pattern",
    "four_week_comparison",
]
type ChartWindow = RelevanceWindowName
type SleepWeekWindow = Literal["7-days"]
type FourWeekComparisonWindow = Literal["28-days"]
type ChartNumber = int | float

CHART_KINDS: tuple[ChartKind, ...] = (
    "adherence_trend",
    "sleep_week",
    "message_pattern",
    "four_week_comparison",
)
CHART_WINDOWS: tuple[ChartWindow, ...] = ("7-days", "28-days")


@dataclass(frozen=True)
class CategoryAxis:
    label: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class NumericAxis:
    label: str
    unit: str
    minimum: ChartNumber
    maximum: ChartNumber
    ticks: tuple[ChartNumber, ...]


@dataclass(frozen=True)
class ChartAxes:
    x: CategoryAxis
    y: NumericAxis


@dataclass(frozen=True)
class AdherenceTrendPoint:
    observed_at: str
    completion_percent: ChartNumber
    observation_node_id: str


@dataclass(frozen=True)
class SleepWeekPoint:
    observed_at: str
    hours: ChartNumber
    observation_node_id: str


@dataclass(frozen=True)
class MessagePatternPoint:
    date: str
    member_count: int
    coach_count: int
    observation_node_id: str


@dataclass(frozen=True)
class FourWeekComparisonPoint:
    week_of: str
    completion_percent: ChartNumber
    observation_node_id: str


@dataclass(frozen=True)
class AdherenceTrendChart:
    kind: Literal["adherence_trend"]
    window: ChartWindow
    axes: ChartAxes
    series: tuple[AdherenceTrendPoint, ...]
    observation_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class SleepWeekChart:
    kind: Literal["sleep_week"]
    window: SleepWeekWindow
    axes: ChartAxes
    series: tuple[SleepWeekPoint, ...]
    observation_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MessagePatternChart:
    kind: Literal["message_pattern"]
    window: ChartWindow
    axes: ChartAxes
    series: tuple[MessagePatternPoint, ...]
    observation_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class FourWeekComparisonChart:
    kind: Literal["four_week_comparison"]
    window: FourWeekComparisonWindow
    axes: ChartAxes
    series: tuple[FourWeekComparisonPoint, ...]
    observation_node_ids: tuple[str, ...]


type ChartData = (
    AdherenceTrendChart | SleepWeekChart | MessagePatternChart | FourWeekComparisonChart
)


@dataclass(frozen=True)
class RenderChartResult:
    data: ChartData
    node_ids: tuple[str, ...]

    @property
    def data_part(self) -> dict[str, object]:
        return {
            "type": "data-chart",
            "data": json.loads(json.dumps(asdict(self.data))),
        }

    def __str__(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@tool
def render_chart(
    member_id: str,
    kind: ChartKind,
    window: ChartWindow,
    as_of: date | None = None,
) -> RenderChartResult:
    """Build one chart from `Member -[:observed]-> Observation`; supply only kind and window."""
    _validate_window(kind, window)
    member_node_id = get_member_node_id(member_id)
    read_date = as_of or datetime.now(UTC).date()
    observations = (
        get_observations(member_id, as_of=read_date)
        if member_node_id is not None
        else ()
    )
    if kind == "adherence_trend":
        adherence = _chart_observations(
            observations,
            kind="adherence-week",
            window=window,
            as_of=read_date,
        )
        data = _adherence_trend(adherence, window)
    elif kind == "sleep_week":
        sleep = _chart_observations(
            observations,
            kind="sleep-night",
            window=window,
            as_of=read_date,
        )
        data = _sleep_week(sleep)
    elif kind == "message_pattern":
        message_pattern = _chart_observations(
            observations,
            kind="message-pattern-day",
            window=window,
            as_of=read_date,
        )
        data = _message_pattern(message_pattern, window)
    else:
        adherence = _chart_observations(
            observations,
            kind="adherence-week",
            window=window,
            as_of=read_date,
        )
        data = _four_week_comparison(adherence)
    return RenderChartResult(
        data=data,
        node_ids=_node_ids(member_node_id, data.observation_node_ids),
    )


def _validate_window(kind: ChartKind, window: ChartWindow) -> None:
    if kind == "sleep_week" and window != "7-days":
        raise ValueError("sleep_week requires window 7-days")
    if kind == "four_week_comparison" and window != "28-days":
        raise ValueError("four_week_comparison requires window 28-days")


def _chart_observations(
    observations: tuple[ObservationView, ...],
    *,
    kind: ObservationKind,
    window: RelevanceWindowName,
    as_of: date,
) -> tuple[ObservationView, ...]:
    return tuple(
        sorted(
            scope_relevance_window(
                (
                    observation
                    for observation in observations
                    if observation.kind == kind and observation.value is not None
                ),
                window=window,
                observed_at=lambda observation: observation.observed_at,
                as_of=as_of,
            ),
            key=lambda observation: (observation.observed_at, observation.node_id),
        )
    )


def _adherence_trend(
    observations: tuple[ObservationView, ...],
    window: ChartWindow,
) -> AdherenceTrendChart:
    series = tuple(
        AdherenceTrendPoint(
            observed_at=observation.observed_at,
            completion_percent=cast(ChartNumber, observation.value),
            observation_node_id=observation.node_id,
        )
        for observation in observations
    )
    return AdherenceTrendChart(
        kind="adherence_trend",
        window=window,
        axes=_adherence_axes(tuple(point.observed_at for point in series)),
        series=series,
        observation_node_ids=tuple(point.observation_node_id for point in series),
    )


def _sleep_week(
    observations: tuple[ObservationView, ...],
) -> SleepWeekChart:
    series = tuple(
        SleepWeekPoint(
            observed_at=observation.observed_at,
            hours=cast(ChartNumber, observation.value),
            observation_node_id=observation.node_id,
        )
        for observation in observations
    )
    return SleepWeekChart(
        kind="sleep_week",
        window="7-days",
        axes=ChartAxes(
            x=CategoryAxis(
                label="Night",
                values=tuple(point.observed_at for point in series),
            ),
            y=NumericAxis(
                label="Sleep",
                unit="hours",
                minimum=0,
                maximum=9,
                ticks=(0, 3, 6, 9),
            ),
        ),
        series=series,
        observation_node_ids=tuple(point.observation_node_id for point in series),
    )


def _message_pattern(
    observations: tuple[ObservationView, ...],
    window: ChartWindow,
) -> MessagePatternChart:
    series = tuple(
        MessagePatternPoint(
            date=observation.observed_at,
            member_count=_integer_measurement(observation, "member_count"),
            coach_count=_integer_measurement(observation, "coach_count"),
            observation_node_id=observation.node_id,
        )
        for observation in observations
    )
    maximum = max(
        (point.member_count + point.coach_count for point in series),
        default=1,
    )
    return MessagePatternChart(
        kind="message_pattern",
        window=window,
        axes=ChartAxes(
            x=CategoryAxis(
                label="Date",
                values=tuple(point.date for point in series),
            ),
            y=NumericAxis(
                label="Messages",
                unit="count",
                minimum=0,
                maximum=maximum,
                ticks=tuple(range(maximum + 1)),
            ),
        ),
        series=series,
        observation_node_ids=tuple(point.observation_node_id for point in series),
    )


def _four_week_comparison(
    observations: tuple[ObservationView, ...],
) -> FourWeekComparisonChart:
    series = tuple(
        FourWeekComparisonPoint(
            week_of=observation.observed_at,
            completion_percent=cast(ChartNumber, observation.value),
            observation_node_id=observation.node_id,
        )
        for observation in observations
    )
    return FourWeekComparisonChart(
        kind="four_week_comparison",
        window="28-days",
        axes=_adherence_axes(tuple(point.week_of for point in series)),
        series=series,
        observation_node_ids=tuple(point.observation_node_id for point in series),
    )


def _integer_measurement(observation: ObservationView, name: str) -> int:
    value = next(
        (
            measurement.value
            for measurement in observation.measurements
            if measurement.name == name
        ),
        None,
    )
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Observation {observation.node_id} requires integer {name}")
    return value


def _adherence_axes(values: tuple[str, ...]) -> ChartAxes:
    return ChartAxes(
        x=CategoryAxis(label="Week of", values=values),
        y=NumericAxis(
            label="Completion",
            unit="percent",
            minimum=0,
            maximum=100,
            ticks=(0, 25, 50, 75, 100),
        ),
    )


def _node_ids(
    member_node_id: str | None,
    data_node_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if member_node_id is None:
        return ()
    return tuple(dict.fromkeys((member_node_id, *data_node_ids)))
