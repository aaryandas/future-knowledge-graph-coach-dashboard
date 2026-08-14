from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type ChartWindow = Literal["7-days", "28-days"]
type SleepWeekWindow = Literal["7-days"]
type FourWeekComparisonWindow = Literal["28-days"]
type ChartNumber = int | float


class CategoryAxis(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    values: list[str]


class NumericAxis(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    unit: str
    minimum: ChartNumber
    maximum: ChartNumber
    ticks: list[ChartNumber]


class ChartAxes(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: CategoryAxis
    y: NumericAxis


class AdherenceTrendPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    observed_at: str
    completion_percent: ChartNumber
    observation_node_id: str


class SleepWeekPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    observed_at: str
    hours: ChartNumber
    observation_node_id: str


class MessagePatternPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str
    member_count: int
    coach_count: int
    observation_node_id: str


class FourWeekComparisonPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    week_of: str
    completion_percent: ChartNumber
    observation_node_id: str


class AdherenceTrendChart(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["adherence_trend"]
    window: ChartWindow
    axes: ChartAxes
    series: list[AdherenceTrendPoint]
    observation_node_ids: list[str]


class SleepWeekChart(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["sleep_week"]
    window: SleepWeekWindow
    axes: ChartAxes
    series: list[SleepWeekPoint]
    observation_node_ids: list[str]


class MessagePatternChart(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["message_pattern"]
    window: ChartWindow
    axes: ChartAxes
    series: list[MessagePatternPoint]
    observation_node_ids: list[str]


class FourWeekComparisonChart(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["four_week_comparison"]
    window: FourWeekComparisonWindow
    axes: ChartAxes
    series: list[FourWeekComparisonPoint]
    observation_node_ids: list[str]


type DataChart = Annotated[
    AdherenceTrendChart
    | SleepWeekChart
    | MessagePatternChart
    | FourWeekComparisonChart,
    Field(discriminator="kind"),
]


class DataChartPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["data-chart"] = "data-chart"
    data: DataChart


__all__ = [
    "AdherenceTrendChart",
    "AdherenceTrendPoint",
    "CategoryAxis",
    "ChartAxes",
    "DataChart",
    "DataChartPart",
    "FourWeekComparisonChart",
    "FourWeekComparisonPoint",
    "MessagePatternChart",
    "MessagePatternPoint",
    "NumericAxis",
    "SleepWeekChart",
    "SleepWeekPoint",
]
