from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Literal, cast

from langchain_core.tools import tool

from app.graph import (
    ChatMessageView,
    ObservationView,
    get_chat_messages,
    get_member_node_id,
    get_observations,
)

type ChartKind = Literal[
    "adherence_trend",
    "sleep_week",
    "message_pattern",
    "four_week_comparison",
]
type ChartWindow = Literal["7-days", "28-days"]
type ChartNumber = int | float

CHART_KINDS: tuple[ChartKind, ...] = (
    "adherence_trend",
    "sleep_week",
    "message_pattern",
    "four_week_comparison",
)
CHART_WINDOWS: tuple[ChartWindow, ...] = ("7-days", "28-days")
_WINDOW_DAYS: dict[ChartWindow, int] = {"7-days": 7, "28-days": 28}


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
    chat_message_node_ids: tuple[str, ...]


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
    window: ChartWindow
    axes: ChartAxes
    series: tuple[SleepWeekPoint, ...]
    observation_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class MessagePatternChart:
    kind: Literal["message_pattern"]
    window: ChartWindow
    axes: ChartAxes
    series: tuple[MessagePatternPoint, ...]
    chat_message_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class FourWeekComparisonChart:
    kind: Literal["four_week_comparison"]
    window: ChartWindow
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
    """Build one chart from `observed` Observations or `said|received` ChatMessages; supply only kind and window."""
    member_node_id = get_member_node_id(member_id)
    read_date = as_of or datetime.now(UTC).date()
    if kind == "message_pattern":
        data = _message_pattern(
            get_chat_messages(member_id) if member_node_id is not None else (),
            window,
            as_of=read_date,
        )
        return RenderChartResult(
            data=data,
            node_ids=_node_ids(member_node_id, data.chat_message_node_ids),
        )

    observations = (
        get_observations(member_id, as_of=read_date)
        if member_node_id is not None
        else ()
    )
    if kind == "adherence_trend":
        adherence = _adherence_observations(observations, window)
        data = _adherence_trend(adherence, window)
    elif kind == "sleep_week":
        sleep = _sleep_observations(observations, window)
        data = _sleep_week(sleep, window)
    else:
        adherence = _adherence_observations(observations, window)
        data = _four_week_comparison(adherence, window)
    return RenderChartResult(
        data=data,
        node_ids=_node_ids(member_node_id, data.observation_node_ids),
    )


def _adherence_observations(
    observations: tuple[ObservationView, ...],
    window: ChartWindow,
) -> tuple[ObservationView, ...]:
    return tuple(
        sorted(
            (
                observation
                for observation in observations
                if observation.kind == "adherence-week"
                and observation.value is not None
                and observation.age_days <= _WINDOW_DAYS[window]
            ),
            key=lambda observation: (observation.observed_at, observation.node_id),
        )
    )


def _sleep_observations(
    observations: tuple[ObservationView, ...],
    window: ChartWindow,
) -> tuple[ObservationView, ...]:
    return tuple(
        sorted(
            (
                observation
                for observation in observations
                if observation.kind == "sleep-night"
                and observation.value is not None
                and observation.age_days <= _WINDOW_DAYS[window]
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
    window: ChartWindow,
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
        window=window,
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
    messages: tuple[ChatMessageView, ...],
    window: ChartWindow,
    *,
    as_of: date,
) -> MessagePatternChart:
    grouped: dict[str, list[ChatMessageView]] = defaultdict(list)
    for message in messages:
        observed_on = datetime.fromisoformat(message.timestamp).date()
        age_days = max(0, (as_of - observed_on).days)
        if age_days <= _WINDOW_DAYS[window]:
            grouped[observed_on.isoformat()].append(message)
    series = tuple(
        MessagePatternPoint(
            date=observed_on,
            member_count=sum(message.sender == "member" for message in daily_messages),
            coach_count=sum(message.sender == "coach" for message in daily_messages),
            chat_message_node_ids=tuple(
                message.node_id
                for message in sorted(daily_messages, key=lambda item: item.node_id)
            ),
        )
        for observed_on, daily_messages in sorted(grouped.items())
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
        chat_message_node_ids=tuple(
            node_id for point in series for node_id in point.chat_message_node_ids
        ),
    )


def _four_week_comparison(
    observations: tuple[ObservationView, ...],
    window: ChartWindow,
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
        window=window,
        axes=_adherence_axes(tuple(point.week_of for point in series)),
        series=series,
        observation_node_ids=tuple(point.observation_node_id for point in series),
    )


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
