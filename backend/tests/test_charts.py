from collections.abc import Sequence
from datetime import date
from typing import cast

import pytest
from app.copilot.testing import CopilotTurn, run_copilot_turn
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


def test_registered_render_chart_exposes_only_valid_kind_window_inputs() -> None:
    ingest_kg2()
    llm = _ChartLLM("sleep_week", "7-days")

    run_copilot_turn(
        MEMBER_ID,
        "Draw a chart",
        checkpointer=InMemorySaver(),
        llm=llm,
        as_of=AS_OF,
    )

    assert llm.render_chart_schema is not None
    properties = cast(
        "dict[str, dict[str, object]]", llm.render_chart_schema["properties"]
    )
    assert set(properties) == {"chart"}
    chart_input = _schema_definition(
        llm.render_chart_schema, properties["chart"].get("$ref")
    )
    variants = cast("list[dict[str, object]]", chart_input["anyOf"])
    assert {
        kind: windows
        for variant in variants
        for kind, windows in (
            _kind_windows(llm.render_chart_schema, variant.get("$ref")),
        )
    } == {
        "adherence_trend": ("7-days", "28-days"),
        "sleep_week": ("7-days",),
        "message_pattern": ("7-days", "28-days"),
        "four_week_comparison": ("28-days",),
    }


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
        self.render_chart_schema: dict[str, object] | None = None

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
        *,
        require_tool_call: bool = False,
    ) -> object:
        if not self._tool_called:
            render_chart = next(tool for tool in tools if tool.name == "render_chart")
            self.render_chart_schema = cast(
                "dict[str, object]", render_chart.args_schema
            )
            properties = self.render_chart_schema.get("properties")
            nested_input = isinstance(properties, dict) and "chart" in properties
            args = (
                {"chart": {"kind": self._kind, "window": self._window}}
                if nested_input
                else {"kind": self._kind, "window": self._window}
            )
            self._tool_called = True
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "render_chart",
                        "args": args,
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


def _run_chart_turn(member_id: str, kind: str, window: str) -> CopilotTurn:
    turn = run_copilot_turn(
        member_id,
        "Draw a chart",
        checkpointer=InMemorySaver(),
        llm=_ChartLLM(kind, window),
        as_of=AS_OF,
    )
    assert isinstance(turn, CopilotTurn)
    return turn


def _point_date(point: dict[str, object]) -> object:
    return point.get("observed_at") or point.get("date") or point.get("week_of")


def _kind_windows(
    schema: dict[str, object],
    variant_ref: object,
) -> tuple[str, tuple[str, ...]]:
    variant = _schema_definition(schema, variant_ref)
    properties = cast("dict[str, dict[str, object]]", variant["properties"])
    kind = properties["kind"].get("const")
    window = _schema_definition(schema, properties["window"].get("$ref"))
    allowed = window.get("enum", (window.get("const"),))
    assert isinstance(kind, str)
    assert isinstance(allowed, list | tuple)
    assert all(isinstance(value, str) for value in allowed)
    return kind, tuple(cast("list[str] | tuple[str, ...]", allowed))


def _schema_definition(
    schema: dict[str, object],
    reference: object,
) -> dict[str, object]:
    assert isinstance(reference, str)
    definitions = schema.get("$defs")
    assert isinstance(definitions, dict)
    definition = definitions.get(reference.removeprefix("#/$defs/"))
    assert isinstance(definition, dict)
    return cast("dict[str, object]", definition)
