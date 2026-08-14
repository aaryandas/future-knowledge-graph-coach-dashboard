from dataclasses import dataclass
from datetime import date
from typing import cast

from app.copilot.testing import (
    MAX_TOOL_ROUNDS,
    CopilotDataPart,
    CopilotToneFact,
    CopilotTurn,
    FakeCopilotLLM,
    MemberGoalsResult,
    copilot_response,
    open_postgres_checkpointer,
    replay_copilot_history,
    run_copilot_turn,
    run_quick_prompt,
)
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "test-member-copilot"


def test_copilot_tool_loop_persists_follow_ups_and_replays_sources() -> None:
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
        {"tool": "get_member_goals", "node_ids": [MEMBER_ID, "goal:strength"]},
        {"tool": "get_member_profile", "node_ids": [MEMBER_ID]},
    ]
    assert [
        str(message.text)
        for message in llm.calls[3].messages
        if isinstance(message, HumanMessage)
    ] == ["What is the priority goal?", "How does that fit Jordan?"]
    history = replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)
    assert [(message.role, message.text) for message in history] == [
        ("user", "What is the priority goal?"),
        ("assistant", "Jordan's priority goal is strength."),
        ("user", "How does that fit Jordan?"),
        ("assistant", "That goal fits Jordan's profile."),
    ]
    assert history[1].data_parts == first_turn.data_parts
    assert history[3].data_parts == second_turn.data_parts


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


def test_copilot_thread_and_data_parts_replay_after_restart() -> None:
    chart = CopilotDataPart(
        type="data-chart",
        data={"kind": "sleep-week", "series": [{"day": "Mon", "hours": 7.5}]},
    )
    llm = FakeCopilotLLM(
        (
            _tool_call("goals-postgres"),
            copilot_response("A persisted answer.", data_parts=(chart,)),
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
                retrieval_tools=(_goals_tool(),),
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


def _tool_call(call_id: str, *, name: str = "get_member_goals") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": {},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


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
