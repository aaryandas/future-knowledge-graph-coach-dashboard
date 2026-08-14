from collections.abc import Sequence
from datetime import date
from typing import cast

import pytest
from app.copilot.agent import run_copilot_turn
from app.copilot.context import CopilotToneFact
from app.graph import ingest_kg2
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "mbr_01HX9JORDAN"
AS_OF = date(2026, 6, 4)


@pytest.mark.parametrize(
    ("kind", "window", "expected_series"),
    [
        (
            "adherence_trend",
            "28-days",
            [
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
            ],
        ),
        (
            "sleep_week",
            "7-days",
            [
                {
                    "observed_at": observed_at,
                    "hours": hours,
                    "observation_node_id": (
                        f"{MEMBER_ID}:observation:sleep-night:{observed_at}"
                    ),
                }
                for observed_at, hours in (
                    ("2026-05-28", 6.1),
                    ("2026-05-29", 5.4),
                    ("2026-05-30", 7.2),
                    ("2026-05-31", 6.0),
                    ("2026-06-01", 5.1),
                    ("2026-06-02", 7.8),
                    ("2026-06-03", 6.3),
                )
            ],
        ),
        (
            "message_pattern",
            "28-days",
            [
                {
                    "date": observed_at,
                    "member_count": member_count,
                    "coach_count": coach_count,
                    "observation_node_id": (
                        f"{MEMBER_ID}:observation:message-pattern-day:{observed_at}"
                    ),
                }
                for observed_at, member_count, coach_count in (
                    ("2026-05-22", 1, 0),
                    ("2026-05-30", 1, 0),
                    ("2026-06-03", 1, 1),
                )
            ],
        ),
        (
            "four_week_comparison",
            "28-days",
            [
                {
                    "week_of": observed_at,
                    "completion_percent": completion_percent,
                    "observation_node_id": (
                        f"{MEMBER_ID}:observation:adherence-week:{observed_at}"
                    ),
                }
                for observed_at, completion_percent in (
                    ("2026-05-12", 100),
                    ("2026-05-19", 100),
                    ("2026-05-26", 75),
                    ("2026-06-02", 50),
                )
            ],
        ),
    ],
)
def test_registered_render_chart_emits_server_built_observation_payload(
    kind: str,
    window: str,
    expected_series: list[dict[str, object]],
) -> None:
    chart, sources = _render(kind, window)

    assert chart["kind"] == kind
    assert chart["window"] == window
    assert chart["series"] == expected_series
    observation_node_ids = cast("list[object]", chart["observation_node_ids"])
    assert observation_node_ids == [
        point["observation_node_id"] for point in expected_series
    ]
    axes = cast("dict[str, object]", chart["axes"])
    assert set(axes) == {"x", "y"}
    assert sources == {
        "sources": [
            {
                "tool": "render_chart",
                "node_ids": [MEMBER_ID, *observation_node_ids],
            }
        ]
    }


@pytest.mark.parametrize(
    ("kind", "expected_dates"),
    [
        ("adherence_trend", ["2026-06-02"]),
        ("message_pattern", ["2026-05-30", "2026-06-03"]),
    ],
)
def test_registered_render_chart_uses_graph_owned_seven_day_window(
    kind: str,
    expected_dates: list[str],
) -> None:
    chart, _ = _render(kind, "7-days")

    series = cast("list[dict[str, object]]", chart["series"])
    assert [_point_date(point) for point in series] == expected_dates


@pytest.mark.parametrize(
    ("kind", "window", "message"),
    [
        ("sleep_week", "28-days", "sleep_week requires window 7-days"),
        (
            "four_week_comparison",
            "7-days",
            "four_week_comparison requires window 28-days",
        ),
    ],
)
def test_registered_render_chart_rejects_contradictory_kind_window_metadata(
    kind: str,
    window: str,
    message: str,
) -> None:
    ingest_kg2()

    with pytest.raises(ValueError, match=message):
        _run_chart_turn(MEMBER_ID, kind, window)


def test_registered_render_chart_emits_empty_payload_for_unknown_member() -> None:
    chart, sources = _render("adherence_trend", "28-days", member_id="unknown-member")

    assert chart["series"] == []
    assert chart["observation_node_ids"] == []
    assert sources == {"sources": [{"tool": "render_chart", "node_ids": []}]}


class _ChartLLM:
    def __init__(self, kind: str, window: str) -> None:
        self._kind = kind
        self._window = window
        self._tool_called = False

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> object:
        if not self._tool_called:
            assert any(tool.name == "render_chart" for tool in tools)
            self._tool_called = True
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "render_chart",
                        "args": {"kind": self._kind, "window": self._window},
                        "id": "render-chart-1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="Chart ready.")


def _render(
    kind: str,
    window: str,
    *,
    member_id: str = MEMBER_ID,
) -> tuple[dict[str, object], object]:
    ingest_kg2()
    turn = _run_chart_turn(member_id, kind, window)
    assert [part.type for part in turn.data_parts] == [
        "data-chart",
        "data-sources",
    ]
    chart_part, sources_part = turn.data_parts
    assert isinstance(chart_part.data, dict)
    return cast("dict[str, object]", chart_part.data), sources_part.data


def _run_chart_turn(member_id: str, kind: str, window: str):
    return run_copilot_turn(
        member_id,
        "Draw a chart",
        checkpointer=InMemorySaver(),
        llm=_ChartLLM(kind, window),
        as_of=AS_OF,
        tone_fact_reader=_no_tone_facts,
    )


def _point_date(point: dict[str, object]) -> object:
    return point.get("observed_at") or point.get("date") or point.get("week_of")


def _no_tone_facts(
    member_id: str,
    *,
    as_of: date | None = None,
) -> tuple[CopilotToneFact, ...]:
    return ()
