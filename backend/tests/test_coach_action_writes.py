from datetime import UTC, date, datetime

from app.graph import (
    SendMemberMessageWrite,
    UpdateBriefTaskWrite,
    confirm_coach_action,
    get_chat_messages,
    get_morning_brief,
    ingest_kg2,
)

MEMBER_ID = "mbr_01HX9JORDAN"
COACH_ID = "coach_01HXSAM"
ACTION_TIMESTAMP = datetime(2026, 6, 4, 16, 30, tzinfo=UTC)


def test_confirmed_member_message_is_stamped_and_survives_reseed() -> None:
    ingest_kg2()
    task_id = _celebrate_task_id()

    result = confirm_coach_action(
        MEMBER_ID,
        "seam-send-message",
        SendMemberMessageWrite(
            message="Great work on the pain-free squat session!",
            coach_task_id=task_id,
        ),
        timestamp=ACTION_TIMESTAMP,
    )

    assert result.status == "confirmed"
    assert result.source == "coach-action"
    assert result.actor == COACH_ID
    assert result.timestamp == ACTION_TIMESTAMP.isoformat()
    assert _sent_message_count() == 1

    ingest_kg2()

    assert _sent_message_count() == 1


def test_confirmed_brief_task_update_is_stamped_and_survives_reseed() -> None:
    ingest_kg2()
    brief = _morning_brief()
    task = next(task for task in brief.coach_tasks if task.type == "celebrate")

    try:
        result = confirm_coach_action(
            MEMBER_ID,
            "seam-update-task",
            UpdateBriefTaskWrite(
                coach_task_id=task.node_id,
                status="completed",
                text="Congratulated Jordan on the pain-free squat session.",
            ),
            timestamp=ACTION_TIMESTAMP,
        )

        assert result.status == "confirmed"
        assert result.source == "coach-action"
        assert result.actor == COACH_ID
        assert result.timestamp == ACTION_TIMESTAMP.isoformat()
        assert result.morning_brief is not None
        updated = next(
            item
            for item in result.morning_brief.coach_tasks
            if item.node_id == task.node_id
        )
        assert updated.status == "completed"
        assert updated.text == "Congratulated Jordan on the pain-free squat session."

        ingest_kg2()

        reseeded = next(
            item
            for item in _morning_brief().coach_tasks
            if item.node_id == task.node_id
        )
        assert reseeded.status == "completed"
        assert reseeded.text == "Congratulated Jordan on the pain-free squat session."
    finally:
        confirm_coach_action(
            MEMBER_ID,
            "seam-restore-task",
            UpdateBriefTaskWrite(
                coach_task_id=task.node_id,
                status=task.status,
                text=task.text,
            ),
            timestamp=ACTION_TIMESTAMP,
        )


def _celebrate_task_id() -> str:
    return next(
        task.node_id
        for task in _morning_brief().coach_tasks
        if task.type == "celebrate"
    )


def _morning_brief():
    morning_brief = get_morning_brief(MEMBER_ID, as_of=date(2026, 6, 4))
    assert morning_brief is not None
    return morning_brief


def _sent_message_count() -> int:
    return sum(
        message.text == "Great work on the pain-free squat session!"
        and message.timestamp == ACTION_TIMESTAMP.isoformat()
        and message.sender == "coach"
        for message in get_chat_messages(MEMBER_ID)
    )
