import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, cast

from app.copilot.testing import (
    MAX_TOOL_ROUNDS,
    CopilotDataPart,
    CopilotToneFact,
    CopilotTurn,
    FakeCopilotLLM,
    JsonValue,
    MemberGoalsResult,
    copilot_response,
    get_morning_brief,
    open_postgres_checkpointer,
    replay_copilot_history,
    run_copilot_turn,
    run_quick_prompt,
)
from app.graph import ingest_kg2
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "test-member-copilot"
SEED_MEMBER_ID = "mbr_01HX9JORDAN"
type _ChartKind = Literal["sleep_week"]
type _ChartWindow = Literal["7-days"]


def test_copilot_prunes_prior_retrieval_payloads_and_replays_persisted_data_parts() -> (
    None
):
    checkpointer = InMemorySaver()
    llm = FakeCopilotLLM(
        (
            _tool_call("goals-1"),
            AIMessage(content="Jordan's priority goal is strength."),
            _tool_call("profile-1", name="get_member_profile"),
            AIMessage(content="That goal fits Jordan's profile."),
        )
    )
    retrieval_tools = (_goals_tool(), _profile_tool())

    first_turn = run_copilot_turn(
        MEMBER_ID,
        "What is the priority goal?",
        checkpointer=checkpointer,
        llm=llm,
        message_id="user-1",
        retrieval_tools=retrieval_tools,
        tone_fact_reader=_no_tone_facts,
    )
    second_turn = run_copilot_turn(
        MEMBER_ID,
        "How does that fit Jordan?",
        checkpointer=checkpointer,
        llm=llm,
        message_id="user-2",
        retrieval_tools=retrieval_tools,
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(first_turn, CopilotTurn)
    assert isinstance(second_turn, CopilotTurn)
    first_sources = _source_payload(first_turn.data_parts)
    second_sources = _source_payload(second_turn.data_parts)
    assert first_sources == [
        {"tool": "get_member_goals", "node_ids": [MEMBER_ID, "goal:strength"]}
    ]
    assert second_sources == [
        {"tool": "get_member_profile", "node_ids": [MEMBER_ID]},
    ]
    assert [
        str(message.text)
        for message in llm.calls[3].messages
        if isinstance(message, HumanMessage)
    ] == ["What is the priority goal?", "How does that fit Jordan?"]
    assert not any(
        isinstance(message, ToolMessage) for message in llm.calls[2].messages
    )
    prior_answers = [
        message for message in llm.calls[2].messages if isinstance(message, AIMessage)
    ]
    assert len(prior_answers) == 1
    assert prior_answers[0].content == "Jordan's priority goal is strength."
    assert prior_answers[0].additional_kwargs == {}
    current_tool_messages = [
        message for message in llm.calls[3].messages if isinstance(message, ToolMessage)
    ]
    assert [message.name for message in current_tool_messages] == ["get_member_profile"]
    history = replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)
    assert [(message.role, message.text) for message in history] == [
        ("user", "What is the priority goal?"),
        ("assistant", "Jordan's priority goal is strength."),
        ("user", "How does that fit Jordan?"),
        ("assistant", "That goal fits Jordan's profile."),
    ]
    assert history[1].data_parts == first_turn.data_parts
    assert history[3].data_parts == second_turn.data_parts


def test_chart_payload_value_follow_up_is_regrounded_after_context_pruning() -> None:
    checkpointer = InMemorySaver()
    llm = _ChartPayloadFollowUpLLM()

    first_turn = run_copilot_turn(
        MEMBER_ID,
        "Show Jordan's sleep this week as a chart.",
        checkpointer=checkpointer,
        llm=llm,
        message_id="chart-follow-up-user-1",
        retrieval_tools=(_chart_tool(),),
        tone_fact_reader=_no_tone_facts,
    )
    second_turn = run_copilot_turn(
        MEMBER_ID,
        "What was the highest bar in that chart?",
        checkpointer=checkpointer,
        llm=llm,
        message_id="chart-follow-up-user-2",
        retrieval_tools=(_chart_tool(),),
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(first_turn, CopilotTurn)
    assert isinstance(second_turn, CopilotTurn)
    assert second_turn.text == "The highest bar was 7.5 hours on 2026-06-03."
    assert llm.retrieval_questions == [
        "Show Jordan's sleep this week as a chart.",
        "What was the highest bar in that chart?",
    ]
    assert _source_payload(second_turn.data_parts) == [
        {
            "tool": "render_chart",
            "node_ids": [MEMBER_ID, "observation:sleep:2026-06-03"],
        }
    ]
    assert (
        next(part for part in second_turn.data_parts if part.type == "data-chart").data
        == _chart_data()
    )
    follow_up_context = llm.calls[2]
    assert not any(isinstance(message, ToolMessage) for message in follow_up_context)
    prior_answers = [
        message for message in follow_up_context if isinstance(message, AIMessage)
    ]
    assert len(prior_answers) == 1
    assert prior_answers[0].content == "Here is Jordan's sleep chart."
    assert prior_answers[0].additional_kwargs == {}


def test_each_follow_up_requires_a_current_turn_tool_call() -> None:
    checkpointer = InMemorySaver()
    llm = _CurrentTurnRetrievalLLM()
    retrieval_tools = (_goals_tool(),)

    first_turn = run_copilot_turn(
        MEMBER_ID,
        "What is the priority goal?",
        checkpointer=checkpointer,
        llm=llm,
        message_id="current-retrieval-user-1",
        retrieval_tools=retrieval_tools,
        tone_fact_reader=_no_tone_facts,
    )
    second_turn = run_copilot_turn(
        MEMBER_ID,
        "What is the priority goal?",
        checkpointer=checkpointer,
        llm=llm,
        message_id="current-retrieval-user-2",
        retrieval_tools=retrieval_tools,
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(first_turn, CopilotTurn)
    assert isinstance(second_turn, CopilotTurn)
    assert first_turn.text == "Jordan's priority goal is strength."
    assert second_turn.text == "Jordan's priority goal is strength."
    assert llm.require_tool_calls == [True, False, True, False]


def test_copilot_stops_after_five_retrieval_tool_rounds() -> None:
    llm = FakeCopilotLLM(
        tuple(_tool_call(f"goals-{round_number}") for round_number in range(6))
    )

    turn = run_copilot_turn(
        MEMBER_ID,
        "Keep looking forever",
        checkpointer=InMemorySaver(),
        llm=llm,
        retrieval_tools=(_goals_tool(),),
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(turn, CopilotTurn)
    assert len(llm.calls) == MAX_TOOL_ROUNDS + 1
    assert len(_source_payload(turn.data_parts)) == MAX_TOOL_ROUNDS
    assert "five retrieval tool rounds" in turn.text


def test_copilot_provider_and_response_errors_are_visible_answers() -> None:
    for response in (RuntimeError("provider offline"), {"content": "not a message"}):
        checkpointer = InMemorySaver()

        turn = run_copilot_turn(
            MEMBER_ID,
            "How is Jordan doing?",
            checkpointer=checkpointer,
            llm=FakeCopilotLLM((response,)),
            retrieval_tools=(_goals_tool(),),
            tone_fact_reader=_no_tone_facts,
        )

        assert isinstance(turn, CopilotTurn)
        assert turn.text == "I could not answer that question. Please try again."
        assert _source_payload(turn.data_parts) == []
        assert replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)[1].text == (
            turn.text
        )


def test_copilot_provider_error_after_retrieval_keeps_sources() -> None:
    turn = run_copilot_turn(
        MEMBER_ID,
        "How is Jordan doing?",
        checkpointer=InMemorySaver(),
        llm=FakeCopilotLLM(
            (
                _tool_call("goals-before-provider-error"),
                RuntimeError("provider offline"),
            )
        ),
        retrieval_tools=(_goals_tool(),),
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(turn, CopilotTurn)
    assert turn.text == "I could not answer that question. Please try again."
    assert _source_payload(turn.data_parts) == [
        {"tool": "get_member_goals", "node_ids": [MEMBER_ID, "goal:strength"]}
    ]


def test_copilot_rejects_member_answer_without_current_retrieval() -> None:
    turn = run_copilot_turn(
        MEMBER_ID,
        "How is Jordan's adherence trending?",
        checkpointer=InMemorySaver(),
        llm=FakeCopilotLLM((AIMessage(content="Adherence is trending down."),)),
        retrieval_tools=(_goals_tool(),),
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(turn, CopilotTurn)
    assert turn.text == "I could not answer that question. Please try again."
    assert _source_payload(turn.data_parts) == []


def test_copilot_default_tool_registry_includes_render_chart() -> None:
    llm = FakeCopilotLLM((AIMessage(content="Ungrounded answer."),))

    run_copilot_turn(
        MEMBER_ID,
        "Draw a chart",
        checkpointer=InMemorySaver(),
        llm=llm,
        tone_fact_reader=_no_tone_facts,
    )

    assert "render_chart" in llm.calls[0].tool_names


def test_quick_prompt_is_a_canned_message_through_the_same_loop() -> None:
    llm = FakeCopilotLLM(
        (_tool_call("goals-quick"), AIMessage(content="Adherence is trending down."))
    )

    run_quick_prompt(
        MEMBER_ID,
        "adherence-trend",
        checkpointer=InMemorySaver(),
        llm=llm,
        retrieval_tools=(_goals_tool(),),
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(llm.calls[0].messages[-1], HumanMessage)
    assert str(llm.calls[0].messages[-1].text) == "How's adherence trending?"


def test_copilot_emits_chart_data_only_from_the_render_chart_tool() -> None:
    invented_chart = CopilotDataPart(
        type="data-chart",
        data={"kind": "sleep_week", "series": [{"hours": 1000}]},
    )
    llm = FakeCopilotLLM(
        (
            _tool_call("goals-before-chart", name="get_member_goals"),
            copilot_response("Invented chart.", data_parts=(invented_chart,)),
        )
    )

    turn = run_copilot_turn(
        MEMBER_ID,
        "Draw a chart",
        checkpointer=InMemorySaver(),
        llm=llm,
        retrieval_tools=(_goals_tool(),),
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(turn, CopilotTurn)
    assert [part.type for part in turn.data_parts] == ["data-sources"]


def test_churn_risk_answer_emits_graph_built_barriers_with_evidence() -> None:
    ingest_kg2()
    turn = run_copilot_turn(
        SEED_MEMBER_ID,
        "What is Jordan's churn risk?",
        checkpointer=InMemorySaver(),
        llm=FakeCopilotLLM(
            (
                _tool_call("brief-1", name="get_morning_brief"),
                AIMessage(content="Jordan's churn risk is elevated."),
            )
        ),
        as_of=date(2026, 6, 4),
        retrieval_tools=(get_morning_brief,),
        tone_fact_reader=_no_tone_facts,
    )

    assert isinstance(turn, CopilotTurn)
    assert [part.type for part in turn.data_parts] == [
        "data-sources",
        "data-brief",
    ]
    brief = turn.data_parts[1].data
    assert isinstance(brief, dict)
    raw_barriers = brief.get("barriers")
    assert isinstance(raw_barriers, list)
    assert all(isinstance(barrier, dict) for barrier in raw_barriers)
    barriers = cast("list[dict[str, object]]", raw_barriers)
    assert {barrier["kind"] for barrier in barriers} == {
        "adherence-decline",
        "work-fatigue",
    }
    assert all(barrier["evidence_node_ids"] for barrier in barriers)


def test_copilot_thread_and_data_parts_replay_after_restart() -> None:
    chart = CopilotDataPart(type="data-chart", data=_chart_data())
    llm = FakeCopilotLLM(
        (
            _tool_call(
                "chart-postgres",
                name="render_chart",
                args={"kind": "sleep_week", "window": "7-days"},
            ),
            AIMessage(content="A persisted answer."),
        )
    )
    with open_postgres_checkpointer() as checkpointer:
        checkpointer.delete_thread(MEMBER_ID)

    try:
        with open_postgres_checkpointer() as checkpointer:
            run_copilot_turn(
                MEMBER_ID,
                "Persist this answer",
                checkpointer=checkpointer,
                llm=llm,
                message_id="postgres-user-1",
                retrieval_tools=(_chart_tool(),),
                tone_fact_reader=_no_tone_facts,
            )

        with open_postgres_checkpointer() as checkpointer:
            history = replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)

        assert [message.id for message in history] == [
            "postgres-user-1",
            history[1].id,
        ]
        assert history[1].text == "A persisted answer."
        assert [part.type for part in history[1].data_parts] == [
            "data-chart",
            "data-sources",
        ]
        assert history[1].data_parts[0] == chart
    finally:
        with open_postgres_checkpointer() as checkpointer:
            checkpointer.delete_thread(MEMBER_ID)


def _tool_call(
    call_id: str,
    *,
    name: str = "get_member_goals",
    args: dict[str, object] | None = None,
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args or {},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


class _CurrentTurnRetrievalLLM:
    def __init__(self) -> None:
        self.require_tool_calls: list[bool] = []

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
        *,
        require_tool_call: bool = False,
    ) -> object:
        self.require_tool_calls.append(require_tool_call)
        if require_tool_call:
            return _tool_call(f"current-retrieval-{len(self.require_tool_calls)}")
        return AIMessage(content="Jordan's priority goal is strength.")


class _ChartPayloadFollowUpLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[BaseMessage, ...]] = []
        self.retrieval_questions: list[str] = []

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
        *,
        require_tool_call: bool = False,
    ) -> object:
        self.calls.append(tuple(messages))
        current_question = next(
            str(message.text)
            for message in reversed(messages)
            if isinstance(message, HumanMessage)
        )
        current_tool_result = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, ToolMessage)
            ),
            None,
        )
        if require_tool_call:
            if "that chart" in current_question:
                assert any(
                    isinstance(message, HumanMessage)
                    and "sleep this week" in str(message.text)
                    for message in messages
                )
            self.retrieval_questions.append(current_question)
            return _tool_call(
                f"chart-payload-{len(self.retrieval_questions)}",
                name="render_chart",
                args={"kind": "sleep_week", "window": "7-days"},
            )
        assert current_tool_result is not None
        raw_result = json.loads(str(current_tool_result.text))
        chart = cast("dict[str, object]", raw_result["data"])
        if "highest bar" not in current_question:
            return AIMessage(content="Here is Jordan's sleep chart.")
        series = cast("list[dict[str, object]]", chart["series"])
        highest = max(series, key=lambda point: cast("float", point["hours"]))
        return AIMessage(
            content=(
                f"The highest bar was {highest['hours']} hours "
                f"on {highest['observed_at']}."
            )
        )


@dataclass(frozen=True)
class _ChartResult:
    node_ids: tuple[str, ...]

    @property
    def data_part(self) -> dict[str, object]:
        return {"type": "data-chart", "data": _chart_data()}

    def __str__(self) -> str:
        return json.dumps(
            {"data": _chart_data(), "node_ids": list(self.node_ids)},
            ensure_ascii=False,
        )


def _chart_tool() -> StructuredTool:
    def render_chart(
        member_id: str,
        kind: _ChartKind,
        window: _ChartWindow,
        as_of: date | None = None,
    ) -> _ChartResult:
        assert kind == "sleep_week"
        assert window == "7-days"
        return _ChartResult(node_ids=(member_id, "observation:sleep:2026-06-03"))

    return StructuredTool.from_function(
        func=render_chart,
        name="render_chart",
        description="Build a chart from graph data.",
    )


def _chart_data() -> JsonValue:
    return {
        "kind": "sleep_week",
        "window": "7-days",
        "axes": {
            "x": {"label": "Night", "values": ["2026-06-03"]},
            "y": {
                "label": "Sleep",
                "unit": "hours",
                "minimum": 0,
                "maximum": 9,
                "ticks": [0, 3, 6, 9],
            },
        },
        "series": [
            {
                "observed_at": "2026-06-03",
                "hours": 7.5,
                "observation_node_id": "observation:sleep:2026-06-03",
            }
        ],
        "observation_node_ids": ["observation:sleep:2026-06-03"],
    }


def _goals_tool() -> StructuredTool:
    def get_member_goals(
        member_id: str,
        as_of: date | None = None,
    ) -> MemberGoalsResult:
        return MemberGoalsResult(goals=(), node_ids=(member_id, "goal:strength"))

    return StructuredTool.from_function(
        func=get_member_goals,
        name="get_member_goals",
        description="Read `Member -[:pursues]-> Goal` records.",
    )


@dataclass(frozen=True)
class _RetrievalResult:
    node_ids: tuple[str, ...]


def _profile_tool() -> StructuredTool:
    def get_member_profile(
        member_id: str,
        as_of: date | None = None,
    ) -> _RetrievalResult:
        return _RetrievalResult(node_ids=(member_id,))

    return StructuredTool.from_function(
        func=get_member_profile,
        name="get_member_profile",
        description="Read the Member record and its profile scalars.",
    )


def _source_payload(
    data_parts: tuple[CopilotDataPart, ...],
) -> list[object]:
    source_part = next(part for part in data_parts if part.type == "data-sources")
    assert isinstance(source_part.data, dict)
    sources = source_part.data.get("sources")
    assert isinstance(sources, list)
    return cast("list[object]", sources)


def _no_tone_facts(
    member_id: str,
    *,
    as_of: date | None = None,
) -> tuple[CopilotToneFact, ...]:
    return ()
