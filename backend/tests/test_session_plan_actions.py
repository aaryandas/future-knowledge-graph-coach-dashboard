from dataclasses import asdict
from datetime import datetime

from app.copilot.testing import (
    AddSessionPlanRow,
    CopilotTurn,
    FakeCopilotLLM,
    RemoveSessionPlanRow,
    SessionPlanRow,
    WriteSessionPlan,
    get_session_plan,
    ingest_kg2,
    resume_copilot_action,
    run_copilot_turn,
    write_coach_action,
)
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

MEMBER_ID = "mbr_01HX9JORDAN"
COACH_ID = "coach_01HXSAM"
SESSION_ID = f"{MEMBER_ID}:workout:2026-05-29"
EXERCISE_ID = "00036a08-7c22-42e4-8fe5-323b53e31667"
EDIT_SESSION_ID = f"{MEMBER_ID}:workout:2026-05-27"
STATIC_JUMP_ID = "01ff62bc-e887-49e4-9cc8-bcd367b34cfd"


def test_confirmed_session_plan_is_stamped_and_survives_seed_reconciliation() -> None:
    ingest_kg2()
    original = get_session_plan(MEMBER_ID, SESSION_ID)
    assert original is not None
    row = SessionPlanRow(
        row_id=f"{SESSION_ID}:row:coach-action",
        exercise_id=EXERCISE_ID,
        section="main",
        sets=2,
        reps=8,
        hold_minutes=None,
        rest_minutes=1.0,
        per_side=False,
        supports_weight=True,
        minutes=4.0,
    )
    action = WriteSessionPlan(
        action_id="seam-write-session-plan",
        kind="write-session-plan",
        session_id=SESSION_ID,
        edits=(AddSessionPlanRow(kind="add", row=row, position=0),),
        old_rows=original.rows,
        new_rows=(row,),
        verdicts=(),
    )

    try:
        result = write_coach_action(MEMBER_ID, action)

        assert result.status == "confirmed"
        assert result.source == "coach-action"
        assert result.actor == COACH_ID
        assert datetime.fromisoformat(result.timestamp).utcoffset() is not None
        stored = get_session_plan(MEMBER_ID, SESSION_ID)
        assert stored is not None
        assert stored.rows == (row,)
        assert stored.source == "coach-action"
        assert stored.actor == COACH_ID
        assert stored.timestamp == result.timestamp

        ingest_kg2()

        reseeded = get_session_plan(MEMBER_ID, SESSION_ID)
        assert reseeded == stored
    finally:
        write_coach_action(
            MEMBER_ID,
            WriteSessionPlan(
                action_id="seam-restore-session-plan",
                kind="write-session-plan",
                session_id=SESSION_ID,
                edits=(RemoveSessionPlanRow(kind="remove", row_id=row.row_id),),
                old_rows=(row,),
                new_rows=original.rows,
                verdicts=(),
            ),
        )


def test_discarded_session_plan_proposal_leaves_kg2_unchanged() -> None:
    ingest_kg2()
    before = get_session_plan(MEMBER_ID, SESSION_ID)
    assert before is not None
    checkpointer = InMemorySaver()
    row = SessionPlanRow(
        row_id=f"{SESSION_ID}:row:discarded",
        exercise_id=EXERCISE_ID,
        section="main",
        sets=2,
        reps=8,
        hold_minutes=None,
        rest_minutes=1.0,
        per_side=False,
        supports_weight=True,
        minutes=4.0,
    )
    proposed = run_copilot_turn(
        MEMBER_ID,
        "Add this row to the session plan",
        checkpointer=checkpointer,
        llm=FakeCopilotLLM(
            (
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_session_plan",
                            "args": {
                                "session_id": SESSION_ID,
                                "edits": [
                                    {
                                        "kind": "add",
                                        "row": asdict(row),
                                        "position": 0,
                                    }
                                ],
                            },
                            "id": "seam-discard-session-plan",
                            "type": "tool_call",
                        }
                    ],
                ),
            )
        ),
        retrieval_tools=(),
    )

    assert isinstance(proposed, CopilotTurn)
    proposal_part = next(
        part for part in proposed.data_parts if part.type == "data-action"
    )
    assert isinstance(proposal_part.data, dict)
    assert proposal_part.data["status"] == "pending"

    discarded = resume_copilot_action(
        MEMBER_ID,
        "seam-discard-session-plan",
        {"decision": "discard"},
        checkpointer=checkpointer,
        retrieval_tools=(),
    )

    assert isinstance(discarded, CopilotTurn)
    discard_part = next(
        part for part in discarded.data_parts if part.type == "data-action"
    )
    assert isinstance(discard_part.data, dict)
    assert discard_part.data["status"] == "discarded"
    assert get_session_plan(MEMBER_ID, SESSION_ID) == before


def test_real_excluded_session_plan_edit_is_blocked_and_leaves_kg2_unchanged() -> None:
    ingest_kg2()
    before = get_session_plan(MEMBER_ID, EDIT_SESSION_ID)
    assert before is not None
    assert len(before.rows) == 1
    original_row = before.rows[0]

    proposed = run_copilot_turn(
        MEMBER_ID,
        "Replace this row with Static Jump",
        checkpointer=InMemorySaver(),
        llm=FakeCopilotLLM(
            (
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_session_plan",
                            "args": {
                                "session_id": EDIT_SESSION_ID,
                                "edits": [
                                    {
                                        "kind": "edit",
                                        "row": {
                                            **asdict(original_row),
                                            "exercise_id": STATIC_JUMP_ID,
                                        },
                                    }
                                ],
                            },
                            "id": "seam-block-excluded-session-plan",
                            "type": "tool_call",
                        }
                    ],
                ),
            )
        ),
        retrieval_tools=(),
    )

    assert isinstance(proposed, CopilotTurn)
    proposal_part = next(
        part for part in proposed.data_parts if part.type == "data-action"
    )
    assert isinstance(proposal_part.data, dict)
    assert proposal_part.data["status"] == "blocked"
    action = proposal_part.data["action"]
    assert isinstance(action, dict)
    verdicts = action["verdicts"]
    assert isinstance(verdicts, list)
    assert len(verdicts) == 1
    verdict = verdicts[0]
    assert isinstance(verdict, dict)
    assert verdict["exercise_id"] == STATIC_JUMP_ID
    assert verdict["status"] == "exclude"
    assert get_session_plan(MEMBER_ID, EDIT_SESSION_ID) == before
