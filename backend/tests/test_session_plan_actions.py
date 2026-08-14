from datetime import datetime

from app.copilot.testing import (
    AddSessionPlanRow,
    RemoveSessionPlanRow,
    SessionPlanRow,
    WriteSessionPlan,
    get_session_plan,
    ingest_kg2,
    write_coach_action,
)

MEMBER_ID = "mbr_01HX9JORDAN"
COACH_ID = "coach_01HXSAM"
SESSION_ID = f"{MEMBER_ID}:workout:2026-05-29"
EXERCISE_ID = "00036a08-7c22-42e4-8fe5-323b53e31667"


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
