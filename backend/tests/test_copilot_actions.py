from dataclasses import dataclass, field
from datetime import date
from typing import cast

import pytest
from app.copilot.testing import (
    CoachAction,
    CopilotToneFact,
    CopilotTurn,
    FakeCopilotLLM,
    SendMemberMessage,
    UpdateBriefTask,
    open_postgres_checkpointer,
    replay_copilot_history,
    resume_copilot_action,
    run_copilot_turn,
)
from app.graph import CoachActionWriteResult, CoachTaskView, MorningBrief
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "test-member-actions"


def test_send_member_message_pauses_with_the_exact_data_action() -> None:
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())

    turn = run_copilot_turn(
        MEMBER_ID,
        "Draft a congratulations message",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "send-1",
                    "send_member_message",
                    {
                        "message": "Great work on yesterday's session!",
                        "coach_task_id": "task-1",
                    },
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
    )

    assert writer.calls == []
    assert turn.text == "Review this proposed coach action."
    assert _action_payload(turn) == {
        "action_id": "send-1",
        "status": "pending",
        "action": {
            "kind": "send-member-message",
            "message": "Great work on yesterday's session!",
            "coach_task_id": "task-1",
        },
    }
    replayed = replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)[1]
    assert replayed.id == turn.message_id
    assert replayed.text == turn.text
    assert replayed.data_parts == turn.data_parts


def test_confirm_uses_the_edited_message_once_and_replaces_the_pending_card() -> None:
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())
    run_copilot_turn(
        MEMBER_ID,
        "Draft a message",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "send-edited",
                    "send_member_message",
                    {"message": "Original draft", "coach_task_id": "task-1"},
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
    )

    turn = resume_copilot_action(
        MEMBER_ID,
        "send-edited",
        {
            "decision": "confirm",
            "action": {
                "kind": "send-member-message",
                "message": "Edited by the coach",
                "coach_task_id": "task-1",
            },
        },
        checkpointer=checkpointer,
        retrieval_tools=(),
        action_writer=writer,
    )

    assert writer.calls == [
        SendMemberMessage(
            action_id="send-edited",
            kind="send-member-message",
            message="Edited by the coach",
            coach_task_id="task-1",
        )
    ]
    assert turn.text == "Message sent."
    assert _action_payload(turn)["status"] == "confirmed"
    history = replay_copilot_history(MEMBER_ID, checkpointer=checkpointer)
    assert len(history) == 2
    assert history[1].data_parts == turn.data_parts


def test_discard_resumes_the_interrupt_without_calling_the_writer() -> None:
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())
    run_copilot_turn(
        MEMBER_ID,
        "Complete the brief task",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "task-discard",
                    "update_brief_task",
                    {"coach_task_id": "task-1", "status": "completed"},
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
    )

    turn = resume_copilot_action(
        MEMBER_ID,
        "task-discard",
        {"decision": "discard"},
        checkpointer=checkpointer,
        retrieval_tools=(),
        action_writer=writer,
    )

    assert writer.calls == []
    assert turn.text == "Action discarded."
    assert _action_payload(turn)["status"] == "discarded"


def test_pending_action_blocks_a_new_member_thread_turn() -> None:
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())
    llm = FakeCopilotLLM(
        (
            _action_tool_call(
                "send-blocking",
                "send_member_message",
                {"message": "Pending draft"},
            ),
        )
    )
    run_copilot_turn(
        MEMBER_ID,
        "Draft a message",
        checkpointer=checkpointer,
        llm=llm,
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
    )

    with pytest.raises(ValueError, match="Resolve the pending coach action"):
        run_copilot_turn(
            MEMBER_ID,
            "Start another turn",
            checkpointer=checkpointer,
            llm=llm,
            retrieval_tools=(),
            tone_fact_reader=_no_tone_facts,
            action_writer=writer,
        )


def test_confirmed_task_update_emits_the_current_data_brief_before_data_action() -> (
    None
):
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result(morning_brief=_morning_brief()))
    run_copilot_turn(
        MEMBER_ID,
        "Complete the brief task",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "task-confirm",
                    "update_brief_task",
                    {"coach_task_id": "task-1", "status": "completed"},
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
    )

    turn = resume_copilot_action(
        MEMBER_ID,
        "task-confirm",
        {"decision": "confirm"},
        checkpointer=checkpointer,
        retrieval_tools=(),
        action_writer=writer,
    )

    assert writer.calls == [
        UpdateBriefTask(
            action_id="task-confirm",
            kind="update-brief-task",
            coach_task_id="task-1",
            status="completed",
        )
    ]
    assert [part.type for part in turn.data_parts] == [
        "data-sources",
        "data-brief",
        "data-action",
    ]
    brief = turn.data_parts[1].data
    assert isinstance(brief, dict)
    coach_tasks = brief.get("coach_tasks")
    assert isinstance(coach_tasks, list)
    first_task = coach_tasks[0]
    assert isinstance(first_task, dict)
    assert first_task.get("status") == "completed"


def test_pending_action_resumes_after_postgres_checkpointer_restart() -> None:
    writer = _RecordingWriter(_confirmed_result())
    with open_postgres_checkpointer() as checkpointer:
        checkpointer.delete_thread(MEMBER_ID)

    try:
        with open_postgres_checkpointer() as checkpointer:
            proposed = run_copilot_turn(
                MEMBER_ID,
                "Draft a durable message",
                checkpointer=checkpointer,
                llm=FakeCopilotLLM(
                    (
                        _action_tool_call(
                            "send-postgres",
                            "send_member_message",
                            {"message": "Persist this proposal"},
                        ),
                    )
                ),
                retrieval_tools=(),
                tone_fact_reader=_no_tone_facts,
                action_writer=writer,
            )
        assert _action_payload(proposed)["status"] == "pending"

        with open_postgres_checkpointer() as checkpointer:
            confirmed = resume_copilot_action(
                MEMBER_ID,
                "send-postgres",
                {"decision": "confirm"},
                checkpointer=checkpointer,
                retrieval_tools=(),
                action_writer=writer,
            )

        assert _action_payload(confirmed)["status"] == "confirmed"
        assert len(writer.calls) == 1
    finally:
        with open_postgres_checkpointer() as checkpointer:
            checkpointer.delete_thread(MEMBER_ID)


def _action_tool_call(
    action_id: str,
    name: str,
    arguments: dict[str, object],
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": arguments,
                "id": action_id,
                "type": "tool_call",
            }
        ],
    )


@dataclass
class _RecordingWriter:
    result: CoachActionWriteResult
    calls: list[CoachAction] = field(default_factory=list)

    def __call__(
        self,
        member_id: str,
        action: CoachAction,
    ) -> CoachActionWriteResult:
        assert member_id == MEMBER_ID
        self.calls.append(action)
        return self.result


def _confirmed_result(
    *,
    morning_brief: MorningBrief | None = None,
) -> CoachActionWriteResult:
    return CoachActionWriteResult(
        status="confirmed",
        source="coach-action",
        actor="coach-1",
        timestamp="2026-06-04T09:00:00+00:00",
        morning_brief=morning_brief,
    )


def _morning_brief() -> MorningBrief:
    return MorningBrief(
        generated_for="2026-06-04",
        churn_risk_level="elevated",
        churn_risk_reasons=("Adherence declined",),
        barriers=(),
        coach_tasks=(
            CoachTaskView(
                node_id="task-1",
                generated_for="2026-06-04",
                type="celebrate",
                text="Congratulate the member",
                status="completed",
                addressed_node_ids=(),
            ),
        ),
    )


def _action_payload(turn: CopilotTurn) -> dict[str, object]:
    action_part = next(part for part in turn.data_parts if part.type == "data-action")
    assert isinstance(action_part.data, dict)
    return cast("dict[str, object]", action_part.data)


def _no_tone_facts(
    member_id: str,
    *,
    as_of: date | None = None,
) -> tuple[CopilotToneFact, ...]:
    return ()
