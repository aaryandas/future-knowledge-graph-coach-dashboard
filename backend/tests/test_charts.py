from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

import pytest
from app.copilot.testing import (
    CHART_KINDS,
    CHART_WINDOWS,
    AdherenceTrendChart,
    AdherenceTrendPoint,
    CategoryAxis,
    ChartAxes,
    FourWeekComparisonChart,
    FourWeekComparisonPoint,
    MessagePatternChart,
    MessagePatternPoint,
    NumericAxis,
    RenderChartResult,
    SleepWeekChart,
    SleepWeekPoint,
    render_chart,
)
from app.graph import ingest_kg2

MEMBER_ID = "mbr_01HX9JORDAN"
AS_OF = date(2026, 6, 4)

CHART_DOMAIN_TYPES = (
    CategoryAxis,
    NumericAxis,
    ChartAxes,
    AdherenceTrendPoint,
    SleepWeekPoint,
    MessagePatternPoint,
    FourWeekComparisonPoint,
    AdherenceTrendChart,
    SleepWeekChart,
    MessagePatternChart,
    FourWeekComparisonChart,
    RenderChartResult,
)


def test_render_chart_exposes_only_the_closed_kinds_and_windows() -> None:
    assert CHART_KINDS == (
        "adherence_trend",
        "sleep_week",
        "message_pattern",
        "four_week_comparison",
    )
    assert CHART_WINDOWS == ("7-days", "28-days")
    schema = render_chart.get_input_jsonschema()
    assert tuple(schema["$defs"]["ChartKind"]["enum"]) == CHART_KINDS
    assert tuple(schema["$defs"]["ChartWindow"]["enum"]) == CHART_WINDOWS


@pytest.mark.parametrize("domain_type", CHART_DOMAIN_TYPES)
def test_chart_domain_values_are_frozen_dataclasses(domain_type: type[Any]) -> None:
    assert is_dataclass(domain_type)
    assert domain_type.__dataclass_params__.frozen


def test_adherence_trend_is_built_from_window_scoped_observations() -> None:
    result = _render("adherence_trend", "28-days")

    assert isinstance(result.data, AdherenceTrendChart)
    assert asdict(result.data) == {
        "kind": "adherence_trend",
        "window": "28-days",
        "axes": {
            "x": {
                "label": "Week of",
                "values": (
                    "2026-05-12",
                    "2026-05-19",
                    "2026-05-26",
                    "2026-06-02",
                ),
            },
            "y": {
                "label": "Completion",
                "unit": "percent",
                "minimum": 0,
                "maximum": 100,
                "ticks": (0, 25, 50, 75, 100),
            },
        },
        "series": (
            {
                "observed_at": "2026-05-12",
                "completion_percent": 100,
                "observation_node_id": (
                    f"{MEMBER_ID}:observation:adherence-week:2026-05-12"
                ),
            },
            {
                "observed_at": "2026-05-19",
                "completion_percent": 100,
                "observation_node_id": (
                    f"{MEMBER_ID}:observation:adherence-week:2026-05-19"
                ),
            },
            {
                "observed_at": "2026-05-26",
                "completion_percent": 75,
                "observation_node_id": (
                    f"{MEMBER_ID}:observation:adherence-week:2026-05-26"
                ),
            },
            {
                "observed_at": "2026-06-02",
                "completion_percent": 50,
                "observation_node_id": (
                    f"{MEMBER_ID}:observation:adherence-week:2026-06-02"
                ),
            },
        ),
        "observation_node_ids": (
            f"{MEMBER_ID}:observation:adherence-week:2026-05-12",
            f"{MEMBER_ID}:observation:adherence-week:2026-05-19",
            f"{MEMBER_ID}:observation:adherence-week:2026-05-26",
            f"{MEMBER_ID}:observation:adherence-week:2026-06-02",
        ),
    }
    assert result.node_ids == (MEMBER_ID, *result.data.observation_node_ids)


def test_sleep_week_is_built_from_the_seven_day_observation_window() -> None:
    result = _render("sleep_week", "28-days")

    assert isinstance(result.data, SleepWeekChart)
    assert tuple((point.observed_at, point.hours) for point in result.data.series) == (
        ("2026-05-28", 6.1),
        ("2026-05-29", 5.4),
        ("2026-05-30", 7.2),
        ("2026-05-31", 6.0),
        ("2026-06-01", 5.1),
        ("2026-06-02", 7.8),
        ("2026-06-03", 6.3),
    )
    assert result.data.window == "28-days"
    assert result.data.axes.y == NumericAxis(
        label="Sleep",
        unit="hours",
        minimum=0,
        maximum=9,
        ticks=(0, 3, 6, 9),
    )
    assert result.data.observation_node_ids == tuple(
        point.observation_node_id for point in result.data.series
    )


def test_message_pattern_is_built_from_chat_messages_in_the_requested_window() -> None:
    result = _render("message_pattern", "28-days")

    assert isinstance(result.data, MessagePatternChart)
    assert tuple(
        (point.date, point.member_count, point.coach_count)
        for point in result.data.series
    ) == (
        ("2026-05-22", 1, 0),
        ("2026-05-30", 1, 0),
        ("2026-06-03", 1, 1),
    )
    assert result.data.axes.y == NumericAxis(
        label="Messages",
        unit="count",
        minimum=0,
        maximum=2,
        ticks=(0, 1, 2),
    )
    assert result.data.chat_message_node_ids == tuple(
        node_id
        for point in result.data.series
        for node_id in point.chat_message_node_ids
    )
    assert result.node_ids == (MEMBER_ID, *result.data.chat_message_node_ids)


def test_four_week_comparison_is_built_from_adherence_observations() -> None:
    result = _render("four_week_comparison", "28-days")

    assert isinstance(result.data, FourWeekComparisonChart)
    assert tuple(
        (point.week_of, point.completion_percent) for point in result.data.series
    ) == (
        ("2026-05-12", 100),
        ("2026-05-19", 100),
        ("2026-05-26", 75),
        ("2026-06-02", 50),
    )
    assert result.data.observation_node_ids == tuple(
        point.observation_node_id for point in result.data.series
    )


@pytest.mark.parametrize(
    ("kind", "expected_dates"),
    [
        ("adherence_trend", ("2026-06-02",)),
        (
            "sleep_week",
            (
                "2026-05-28",
                "2026-05-29",
                "2026-05-30",
                "2026-05-31",
                "2026-06-01",
                "2026-06-02",
                "2026-06-03",
            ),
        ),
        ("message_pattern", ("2026-05-30", "2026-06-03")),
        ("four_week_comparison", ("2026-06-02",)),
    ],
)
def test_render_chart_applies_the_llm_selected_window(
    kind: str,
    expected_dates: tuple[str, ...],
) -> None:
    result = _render(kind, "7-days")

    dates = tuple(_point_date(point) for point in result.data.series)
    assert dates == expected_dates


def test_render_chart_returns_empty_server_built_payload_for_unknown_member() -> None:
    result = render_chart.invoke(
        {
            "member_id": "unknown-member",
            "kind": "adherence_trend",
            "window": "28-days",
            "as_of": AS_OF,
        }
    )

    assert isinstance(result, RenderChartResult)
    assert isinstance(result.data, AdherenceTrendChart)
    assert result.data.series == ()
    assert result.data.observation_node_ids == ()
    assert result.node_ids == ()


def _render(kind: str, window: str) -> RenderChartResult:
    ingest_kg2()
    result = render_chart.invoke(
        {
            "member_id": MEMBER_ID,
            "kind": kind,
            "window": window,
            "as_of": AS_OF,
        }
    )
    assert isinstance(result, RenderChartResult)
    return result


def _point_date(point: object) -> str:
    if isinstance(point, AdherenceTrendPoint | SleepWeekPoint):
        return point.observed_at
    if isinstance(point, MessagePatternPoint):
        return point.date
    if isinstance(point, FourWeekComparisonPoint):
        return point.week_of
    raise AssertionError(f"Unsupported chart point {point!r}")
