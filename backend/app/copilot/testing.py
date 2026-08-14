"""Test adapters for the checkpointed copilot agent."""

from langchain_core.messages import AIMessage

from app.copilot.actions import (
    CoachAction,
    CoachActionDecision,
    CoachActionWriter,
    SendMemberMessage,
    UpdateBriefTask,
)
from app.copilot.agent import (
    _DATA_PARTS_KEY,
    MAX_TOOL_ROUNDS,
    CopilotConflict,
    CopilotConflictKind,
    CopilotDataPart,
    CopilotHistoryMessage,
    CopilotSource,
    CopilotTurn,
    CopilotTurnResult,
    QuickPrompt,
    QuickPromptId,
    replay_copilot_history,
    resume_copilot_action,
    run_copilot_turn,
    run_quick_prompt,
)
from app.copilot.context import (
    COPILOT_TONE_FACT_LABELS,
    CopilotToneFact,
    get_copilot_tone_facts,
)
from app.copilot.llm import FakeCopilotLLM
from app.copilot.persistence import open_postgres_checkpointer
from app.copilot.tools import (
    BarrierData,
    ChatMessageData,
    ChatMessagesResult,
    CoachTaskData,
    GoalData,
    MemberGoalsResult,
    MemberInjuriesResult,
    MemberInjuryData,
    MemberProfileData,
    MemberProfileResult,
    MorningBriefData,
    MorningBriefResult,
    ObservationData,
    ObservationMeasurement,
    ObservationsResult,
    WorkoutSessionData,
    WorkoutSessionsResult,
    get_chat_messages,
    get_member_goals,
    get_member_injuries,
    get_member_profile,
    get_morning_brief,
    get_observations,
    get_workout_sessions,
)


def copilot_response(
    text: str,
    *,
    data_parts: tuple[CopilotDataPart, ...] = (),
) -> AIMessage:
    return AIMessage(
        content=text,
        additional_kwargs={
            _DATA_PARTS_KEY: [
                {"type": part.type, "data": part.data} for part in data_parts
            ]
        },
    )


__all__ = [
    "COPILOT_TONE_FACT_LABELS",
    "MAX_TOOL_ROUNDS",
    "BarrierData",
    "ChatMessageData",
    "ChatMessagesResult",
    "CoachAction",
    "CoachActionDecision",
    "CoachActionWriter",
    "CoachTaskData",
    "CopilotConflict",
    "CopilotConflictKind",
    "CopilotDataPart",
    "CopilotHistoryMessage",
    "CopilotSource",
    "CopilotToneFact",
    "CopilotTurn",
    "CopilotTurnResult",
    "FakeCopilotLLM",
    "GoalData",
    "MemberGoalsResult",
    "MemberInjuriesResult",
    "MemberInjuryData",
    "MemberProfileData",
    "MemberProfileResult",
    "MorningBriefData",
    "MorningBriefResult",
    "ObservationData",
    "ObservationMeasurement",
    "ObservationsResult",
    "QuickPrompt",
    "QuickPromptId",
    "SendMemberMessage",
    "UpdateBriefTask",
    "WorkoutSessionData",
    "WorkoutSessionsResult",
    "copilot_response",
    "get_chat_messages",
    "get_copilot_tone_facts",
    "get_member_goals",
    "get_member_injuries",
    "get_member_profile",
    "get_morning_brief",
    "get_observations",
    "get_workout_sessions",
    "open_postgres_checkpointer",
    "replay_copilot_history",
    "resume_copilot_action",
    "run_copilot_turn",
    "run_quick_prompt",
]
