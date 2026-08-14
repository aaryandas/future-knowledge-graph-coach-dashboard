"""Test adapters for the checkpointed copilot agent."""

from langchain_core.messages import AIMessage

from app.copilot.agent import (
    _DATA_PARTS_KEY,
    MAX_TOOL_ROUNDS,
    CopilotDataPart,
    CopilotHistoryMessage,
    CopilotSource,
    CopilotTurn,
    JsonValue,
    QuickPrompt,
    QuickPromptId,
    replay_copilot_history,
    run_copilot_turn,
    run_quick_prompt,
)
from app.copilot.charts import (
    CHART_KINDS,
    CHART_WINDOWS,
    AdherenceTrendChart,
    AdherenceTrendPoint,
    CategoryAxis,
    ChartAxes,
    FourWeekComparisonChart,
    FourWeekComparisonPoint,
    MessagePatternChart,
    MessagePatternPoint,
    NumericAxis,
    RenderChartResult,
    SleepWeekChart,
    SleepWeekPoint,
    render_chart,
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
    "CHART_KINDS",
    "CHART_WINDOWS",
    "COPILOT_TONE_FACT_LABELS",
    "MAX_TOOL_ROUNDS",
    "AdherenceTrendChart",
    "AdherenceTrendPoint",
    "BarrierData",
    "CategoryAxis",
    "ChartAxes",
    "ChatMessageData",
    "ChatMessagesResult",
    "CoachTaskData",
    "CopilotDataPart",
    "CopilotHistoryMessage",
    "CopilotSource",
    "CopilotToneFact",
    "CopilotTurn",
    "FakeCopilotLLM",
    "FourWeekComparisonChart",
    "FourWeekComparisonPoint",
    "GoalData",
    "JsonValue",
    "MemberGoalsResult",
    "MemberInjuriesResult",
    "MemberInjuryData",
    "MemberProfileData",
    "MemberProfileResult",
    "MessagePatternChart",
    "MessagePatternPoint",
    "MorningBriefData",
    "MorningBriefResult",
    "NumericAxis",
    "ObservationData",
    "ObservationMeasurement",
    "ObservationsResult",
    "QuickPrompt",
    "QuickPromptId",
    "RenderChartResult",
    "SleepWeekChart",
    "SleepWeekPoint",
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
    "render_chart",
    "replay_copilot_history",
    "run_copilot_turn",
    "run_quick_prompt",
]
