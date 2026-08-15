from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, cast

from app.copilot.testing import (
    CoachAction,
    CopilotConflict,
    CopilotToneFact,
    CopilotTurn,
    FakeCopilotLLM,
    GraphDecision,
    SendMemberMessage,
    SessionPlan,
    SessionPlanRow,
    UpdateBriefTask,
    Verdict,
    VerdictTraceEvent,
    WalkedNode,
    WalkedPath,
    WriteSessionPlan,
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
    assert isinstance(turn, CopilotTurn)
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
    assert isinstance(turn, CopilotTurn)
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
    assert isinstance(turn, CopilotTurn)
    assert turn.text == "Action discarded."
    assert _action_payload(turn)["status"] == "discarded"


def test_session_plan_edit_emits_exact_rows_after_the_safety_recheck() -> None:
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())
    reader = _RecordingSessionPlanReader(_session_plan())
    evaluator = _RecordingVerdictEvaluator(
        (
            _verdict("exercise-2", "clear"),
            _verdict("exercise-1", "caution"),
        )
    )

    turn = run_copilot_turn(
        MEMBER_ID,
        "Move the row and reduce its dose",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "session-edit",
                    "write_session_plan",
                    {
                        "session_id": "session-1",
                        "edits": [
                            {
                                "kind": "edit",
                                "row": {
                                    **_row_payload("row-1", "exercise-1"),
                                    "sets": 2,
                                },
                            },
                            {
                                "kind": "reorder",
                                "row_id": "row-2",
                                "position": 0,
                            },
                        ],
                    },
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
        session_plan_reader=reader,
        verdict_evaluator=evaluator,
    )

    assert reader.calls == [(MEMBER_ID, "session-1")]
    assert evaluator.calls == [(MEMBER_ID, ("exercise-2", "exercise-1"))]
    assert writer.calls == []
    assert isinstance(turn, CopilotTurn)
    payload = _action_payload(turn)
    assert payload["status"] == "pending"
    action = cast("dict[str, object]", payload["action"])
    assert action["old_rows"] == [
        _row_payload("row-1", "exercise-1"),
        _row_payload("row-2", "exercise-2"),
    ]
    assert action["new_rows"] == [
        _row_payload("row-2", "exercise-2"),
        {**_row_payload("row-1", "exercise-1"), "sets": 2},
    ]
    verdicts = cast("list[dict[str, object]]", action["verdicts"])
    assert [verdict["status"] for verdict in verdicts] == ["clear", "caution"]


def test_safety_excluded_session_plan_row_emits_a_blocked_verdict_without_a_write() -> (
    None
):
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())
    evaluator = _RecordingVerdictEvaluator(
        (
            _verdict("exercise-1", "exclude"),
            _verdict("exercise-2", "clear"),
        )
    )

    turn = run_copilot_turn(
        MEMBER_ID,
        "Keep this unsafe edit",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "session-blocked",
                    "write_session_plan",
                    {
                        "session_id": "session-1",
                        "edits": [
                            {
                                "kind": "edit",
                                "row": _row_payload("row-1", "exercise-1"),
                            }
                        ],
                    },
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
        session_plan_reader=_RecordingSessionPlanReader(_session_plan()),
        verdict_evaluator=evaluator,
    )

    assert writer.calls == []
    assert isinstance(turn, CopilotTurn)
    assert (
        turn.text == "The session plan contains an excluded row. Nothing was changed."
    )
    payload = _action_payload(turn)
    assert payload["status"] == "blocked"
    action = cast("dict[str, object]", payload["action"])
    verdicts = cast("list[dict[str, object]]", action["verdicts"])
    assert verdicts[0]["status"] == "exclude"


def test_session_plan_discard_writes_nothing() -> None:
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())
    run_copilot_turn(
        MEMBER_ID,
        "Remove the second row",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "session-discard",
                    "write_session_plan",
                    {
                        "session_id": "session-1",
                        "edits": [{"kind": "remove", "row_id": "row-2"}],
                    },
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
        session_plan_reader=_RecordingSessionPlanReader(_session_plan()),
        verdict_evaluator=_RecordingVerdictEvaluator(
            (_verdict("exercise-1", "clear"),)
        ),
    )

    turn = resume_copilot_action(
        MEMBER_ID,
        "session-discard",
        {"decision": "discard"},
        checkpointer=checkpointer,
        retrieval_tools=(),
        action_writer=writer,
    )

    assert writer.calls == []
    assert isinstance(turn, CopilotTurn)
    assert _action_payload(turn)["status"] == "discarded"


def test_session_plan_confirm_calls_one_writer_with_the_reviewed_rows() -> None:
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())
    run_copilot_turn(
        MEMBER_ID,
        "Add and remove rows",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "session-confirm",
                    "write_session_plan",
                    {
                        "session_id": "session-1",
                        "edits": [
                            {
                                "kind": "add",
                                "row": _row_payload("row-3", "exercise-3"),
                                "position": 2,
                            },
                            {"kind": "remove", "row_id": "row-2"},
                        ],
                    },
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
        session_plan_reader=_RecordingSessionPlanReader(_session_plan()),
        verdict_evaluator=_RecordingVerdictEvaluator(
            (
                _verdict("exercise-1", "clear"),
                _verdict("exercise-3", "clear"),
            )
        ),
    )

    turn = resume_copilot_action(
        MEMBER_ID,
        "session-confirm",
        {"decision": "confirm"},
        checkpointer=checkpointer,
        retrieval_tools=(),
        action_writer=writer,
    )

    assert len(writer.calls) == 1
    action = writer.calls[0]
    assert isinstance(action, WriteSessionPlan)
    assert action.new_rows == (
        _row("row-1", "exercise-1"),
        _row("row-3", "exercise-3"),
    )
    assert isinstance(turn, CopilotTurn)
    assert turn.text == "Session plan updated."


def test_session_plan_confirm_rejects_rows_changed_after_the_safety_recheck() -> None:
    checkpointer = InMemorySaver()
    writer = _RecordingWriter(_confirmed_result())
    proposed = run_copilot_turn(
        MEMBER_ID,
        "Remove the second row",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                _action_tool_call(
                    "session-tampered",
                    "write_session_plan",
                    {
                        "session_id": "session-1",
                        "edits": [{"kind": "remove", "row_id": "row-2"}],
                    },
                ),
            )
        ),
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
        session_plan_reader=_RecordingSessionPlanReader(_session_plan()),
        verdict_evaluator=_RecordingVerdictEvaluator(
            (_verdict("exercise-1", "clear"),)
        ),
    )
    assert isinstance(proposed, CopilotTurn)
    action = deepcopy(cast("dict[str, object]", _action_payload(proposed)["action"]))
    new_rows = cast("list[dict[str, object]]", action["new_rows"])
    new_rows[0]["exercise_id"] = "exercise-not-reviewed"

    result = resume_copilot_action(
        MEMBER_ID,
        "session-tampered",
        {"decision": "confirm", "action": action},
        checkpointer=checkpointer,
        retrieval_tools=(),
        action_writer=writer,
    )

    assert result == CopilotConflict(
        kind="invalid-resolution",
        detail="The coach action resolution is invalid.",
    )
    assert writer.calls == []


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

    result = run_copilot_turn(
        MEMBER_ID,
        "Start another turn",
        checkpointer=checkpointer,
        llm=llm,
        retrieval_tools=(),
        tone_fact_reader=_no_tone_facts,
        action_writer=writer,
    )

    assert result == CopilotConflict(
        kind="pending-action",
        detail="Resolve the pending coach action before starting a new turn.",
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
    assert isinstance(turn, CopilotTurn)
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
        assert isinstance(proposed, CopilotTurn)
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

        assert isinstance(confirmed, CopilotTurn)
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


@dataclass
class _RecordingSessionPlanReader:
    result: SessionPlan | None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, member_id: str, session_id: str) -> SessionPlan | None:
        self.calls.append((member_id, session_id))
        return self.result


@dataclass
class _RecordingVerdictEvaluator:
    result: tuple[Verdict, ...]
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def __call__(
        self,
        member_id: str,
        exercise_ids: tuple[str, ...],
    ) -> tuple[Verdict, ...]:
        self.calls.append((member_id, exercise_ids))
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


def _session_plan() -> SessionPlan:
    return SessionPlan(
        session_id="session-1",
        rows=(
            _row("row-1", "exercise-1"),
            _row("row-2", "exercise-2"),
        ),
        source="data/member-context.json",
        actor=None,
        timestamp=None,
    )


def _row(row_id: str, exercise_id: str, *, sets: int = 3) -> SessionPlanRow:
    return SessionPlanRow(
        row_id=row_id,
        exercise_id=exercise_id,
        section="main",
        sets=sets,
        reps=8,
        hold_minutes=None,
        rest_minutes=1.0,
        per_side=False,
        supports_weight=True,
        minutes=5.0,
    )


def _row_payload(row_id: str, exercise_id: str) -> dict[str, object]:
    return {
        "row_id": row_id,
        "exercise_id": exercise_id,
        "section": "main",
        "sets": 3,
        "reps": 8,
        "hold_minutes": None,
        "rest_minutes": 1.0,
        "per_side": False,
        "supports_weight": True,
        "minutes": 5.0,
    }


def _verdict(
    exercise_id: str,
    status: str,
) -> Verdict:
    path = WalkedPath(
        nodes=(WalkedNode(node_id=exercise_id, kind="Exercise", name=None),),
        edges=(),
    )
    decision = GraphDecision(
        exercise_id=exercise_id,
        status=cast("Literal['exclude', 'caution', 'clear']", status),
        layer=None,
        member_injury_id=None,
        injury_status=None,
        injury_severity=None,
        reason="Test safety verdict",
        walked_path=path,
    )
    trace = VerdictTraceEvent(
        exercise_id=exercise_id,
        status=cast("Literal['exclude', 'caution', 'clear']", status),
        layer=None,
        reason=decision.reason,
        walked_path=path,
        used=(exercise_id,),
    )
    return Verdict(
        exercise_id=exercise_id,
        status=cast("Literal['exclude', 'caution', 'clear']", status),
        walked_path=path,
        decisions=(decision,),
        trace=(trace,),
    )


def _no_tone_facts(
    member_id: str,
    *,
    as_of: date | None = None,
) -> tuple[CopilotToneFact, ...]:
    return ()
