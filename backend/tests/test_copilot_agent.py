from datetime import date

from app.copilot import (
    MAX_TOOL_ROUNDS,
    CopilotToneFact,
    FakeCopilotLLM,
    MemberGoalsResult,
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
            AIMessage(content="That goal is still the highest priority."),
        )
    )

    first_turn = run_copilot_turn(
        MEMBER_ID,
        "What is the priority goal?",
        checkpointer=checkpointer,
        llm=llm,
        message_id="user-1",
        retrieval_tools=(_goals_tool(),),
        tone_fact_reader=_no_tone_facts,
    )
    second_turn = run_copilot_turn(
        MEMBER_ID,
        "Is that still the top one?",
        checkpointer=checkpointer,
        llm=llm,
        message_id="user-2",
        retrieval_tools=(_goals_tool(),),
        tone_fact_reader=_no_tone_facts,
    )

    assert first_turn.sources[0].tool == "get_member_goals"
    assert first_turn.sources[0].node_ids == (MEMBER_ID, "goal:strength")
    assert second_turn.sources == ()
    assert [
        str(message.text)
        for message in llm.calls[2].messages
        if isinstance(message, HumanMessage)
    ] == ["What is the priority goal?", "Is that still the top one?"]
    history = replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)
    assert [(message.role, message.text) for message in history] == [
        ("user", "What is the priority goal?"),
        ("assistant", "Jordan's priority goal is strength."),
        ("user", "Is that still the top one?"),
        ("assistant", "That goal is still the highest priority."),
    ]
    assert history[1].sources == first_turn.sources
    assert history[3].sources == ()


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

    assert len(llm.calls) == MAX_TOOL_ROUNDS + 1
    assert len(turn.sources) == MAX_TOOL_ROUNDS
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

        assert turn.text == "I could not answer that question. Please try again."
        assert turn.sources == ()
        assert replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)[1].text == (
            turn.text
        )


def test_quick_prompt_is_a_canned_message_through_the_same_loop() -> None:
    llm = FakeCopilotLLM((AIMessage(content="Adherence is trending down."),))

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


def test_copilot_thread_persists_on_the_postgres_checkpointer() -> None:
    llm = FakeCopilotLLM((AIMessage(content="A persisted answer."),))
    with open_postgres_checkpointer() as checkpointer:
        checkpointer.delete_thread(MEMBER_ID)
        try:
            run_copilot_turn(
                MEMBER_ID,
                "Persist this answer",
                checkpointer=checkpointer,
                llm=llm,
                message_id="postgres-user-1",
                retrieval_tools=(_goals_tool(),),
                tone_fact_reader=_no_tone_facts,
            )

            history = replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)

            assert [message.id for message in history] == [
                "postgres-user-1",
                history[1].id,
            ]
            assert history[1].text == "A persisted answer."
        finally:
            checkpointer.delete_thread(MEMBER_ID)


def _tool_call(call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_member_goals",
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


def _no_tone_facts(
    member_id: str,
    *,
    as_of: date | None = None,
) -> tuple[CopilotToneFact, ...]:
    return ()
