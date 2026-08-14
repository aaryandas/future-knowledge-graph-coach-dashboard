from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Literal, Protocol, cast
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.copilot.context import CopilotToneFact, get_copilot_tone_facts
from app.copilot.llm import CopilotLLM, build_copilot_llm
from app.copilot.tools import RETRIEVAL_TOOLS

type QuickPromptId = Literal[
    "show-brief",
    "adherence-trend",
    "sleep-week",
    "changes",
]
type HistoryRole = Literal["user", "assistant"]
type AgentRoute = Literal["tools", "limit", "__end__"]

MAX_TOOL_ROUNDS = 5
_FAILURE_MESSAGE = "I could not answer that question. Please try again."
_ROUND_LIMIT_MESSAGE = (
    "I could not complete that answer within five retrieval tool rounds. "
    "Please narrow the question and try again."
)
_SYSTEM_PROMPT = """You are the coach copilot for one member.
Answer only from retrieval tool results in this thread. Use a retrieval tool before
making a member-specific claim. The tools are already scoped to the current member.
Never invent a value or node id. Treat Journey stage and Churn risk as tone guidance,
not answer evidence. After at most five retrieval tool rounds, answer concisely."""


class _CopilotState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_rounds: int


class CopilotToneFactReader(Protocol):
    def __call__(
        self,
        member_id: str,
        *,
        as_of: date | None = None,
    ) -> tuple[CopilotToneFact, ...]: ...


@dataclass(frozen=True)
class CopilotSource:
    tool: str
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class CopilotTurn:
    message_id: str
    text: str
    sources: tuple[CopilotSource, ...]


@dataclass(frozen=True)
class CopilotHistoryMessage:
    id: str
    role: HistoryRole
    text: str
    sources: tuple[CopilotSource, ...]


@dataclass(frozen=True)
class QuickPrompt:
    id: QuickPromptId
    label: str
    message: str


QUICK_PROMPTS: tuple[QuickPrompt, ...] = (
    QuickPrompt(id="show-brief", label="Brief", message="Show me the brief"),
    QuickPrompt(
        id="adherence-trend",
        label="Adherence",
        message="How's adherence trending?",
    ),
    QuickPrompt(id="sleep-week", label="Sleep", message="Sleep this week"),
    QuickPrompt(
        id="changes",
        label="4 weeks",
        message="What changed since last week?",
    ),
)


def run_copilot_turn(
    member_id: str,
    message: str,
    *,
    checkpointer: BaseCheckpointSaver[Any],
    llm: CopilotLLM | None = None,
    message_id: str | None = None,
    as_of: date | None = None,
    retrieval_tools: Sequence[BaseTool] = RETRIEVAL_TOOLS,
    tone_fact_reader: CopilotToneFactReader = get_copilot_tone_facts,
) -> CopilotTurn:
    """Run one checkpointed copilot turn for the member's single thread."""
    user_text = message.strip()
    if not user_text:
        raise ValueError("A copilot message cannot be empty.")

    user_message_id = message_id or f"user-{uuid4()}"
    assistant_message_id = f"assistant-{uuid4()}"
    member_tools = _member_tools(retrieval_tools, member_id, as_of)
    tone_facts = tone_fact_reader(member_id, as_of=as_of)
    graph = _build_graph(
        llm or build_copilot_llm(),
        member_tools,
        tone_facts,
        assistant_message_id,
        checkpointer,
    )
    state = cast(
        "_CopilotState",
        graph.invoke(
            {
                "messages": [HumanMessage(content=user_text, id=user_message_id)],
                "tool_rounds": 0,
            },
            _thread_config(member_id),
        ),
    )
    turn_messages = _current_turn_messages(state["messages"])
    answer = _final_answer(turn_messages)
    return CopilotTurn(
        message_id=answer.id or assistant_message_id,
        text=_message_text(answer),
        sources=_sources(turn_messages),
    )


def run_quick_prompt(
    member_id: str,
    quick_prompt_id: QuickPromptId,
    *,
    checkpointer: BaseCheckpointSaver[Any],
    llm: CopilotLLM | None = None,
    message_id: str | None = None,
    as_of: date | None = None,
    retrieval_tools: Sequence[BaseTool] = RETRIEVAL_TOOLS,
    tone_fact_reader: CopilotToneFactReader = get_copilot_tone_facts,
) -> CopilotTurn:
    prompt = next(prompt for prompt in QUICK_PROMPTS if prompt.id == quick_prompt_id)
    return run_copilot_turn(
        member_id,
        prompt.message,
        checkpointer=checkpointer,
        llm=llm,
        message_id=message_id,
        as_of=as_of,
        retrieval_tools=retrieval_tools,
        tone_fact_reader=tone_fact_reader,
    )


def replay_copilot_history(
    member_id: str,
    *,
    checkpointer: BaseCheckpointSaver[Any],
) -> tuple[CopilotHistoryMessage, ...]:
    checkpoint = checkpointer.get(_thread_config(member_id))
    if checkpoint is None:
        return ()
    channel_values = checkpoint.get("channel_values")
    if not isinstance(channel_values, dict):
        return ()
    messages = channel_values.get("messages")
    if not isinstance(messages, list):
        return ()
    return _history_messages(messages)


def _build_graph(
    llm: CopilotLLM | None,
    member_tools: tuple[BaseTool, ...],
    tone_facts: tuple[CopilotToneFact, ...],
    assistant_message_id: str,
    checkpointer: BaseCheckpointSaver[Any],
) -> Any:
    tool_by_name = {tool.name: tool for tool in member_tools}

    def call_model(state: _CopilotState) -> dict[str, list[AIMessage]]:
        if llm is None:
            return {
                "messages": [
                    AIMessage(content=_FAILURE_MESSAGE, id=assistant_message_id)
                ]
            }
        messages: tuple[BaseMessage, ...] = (
            SystemMessage(content=_system_prompt(tone_facts)),
            *state["messages"],
        )
        try:
            response = llm.invoke(messages, member_tools)
        except Exception:  # noqa: BLE001 - every LLM adapter failure degrades here.
            return {
                "messages": [
                    AIMessage(content=_FAILURE_MESSAGE, id=assistant_message_id)
                ]
            }
        if not isinstance(response, AIMessage) or response.invalid_tool_calls:
            return {
                "messages": [
                    AIMessage(content=_FAILURE_MESSAGE, id=assistant_message_id)
                ]
            }
        if not response.tool_calls and not _message_text(response):
            return {
                "messages": [
                    AIMessage(content=_FAILURE_MESSAGE, id=assistant_message_id)
                ]
            }
        response_id = response.id or (
            f"tool-call-{uuid4()}" if response.tool_calls else assistant_message_id
        )
        return {"messages": [response.model_copy(update={"id": response_id})]}

    def call_tools(state: _CopilotState) -> dict[str, object]:
        response = cast("AIMessage", state["messages"][-1])
        tool_messages: list[ToolMessage] = []
        for tool_call in response.tool_calls:
            name = tool_call["name"]
            retrieval_tool = tool_by_name.get(name)
            if retrieval_tool is None:
                tool_messages.append(
                    ToolMessage(
                        content=f"Unknown retrieval tool: {name}",
                        name=name,
                        tool_call_id=tool_call["id"],
                        status="error",
                        additional_kwargs={"node_ids": []},
                    )
                )
                continue
            result = retrieval_tool.invoke(tool_call.get("args", {}))
            node_ids = getattr(result, "node_ids", ())
            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    name=name,
                    tool_call_id=tool_call["id"],
                    additional_kwargs={"node_ids": list(node_ids)},
                )
            )
        return {
            "messages": tool_messages,
            "tool_rounds": state["tool_rounds"] + 1,
        }

    def route_after_model(state: _CopilotState) -> AgentRoute:
        response = state["messages"][-1]
        if not isinstance(response, AIMessage) or not response.tool_calls:
            return "__end__"
        if state["tool_rounds"] >= MAX_TOOL_ROUNDS:
            return "limit"
        return "tools"

    def stop_at_limit(state: _CopilotState) -> dict[str, list[AIMessage]]:
        del state
        return {
            "messages": [
                AIMessage(content=_ROUND_LIMIT_MESSAGE, id=assistant_message_id)
            ]
        }

    # ty cannot recognize LangGraph's supported TypedDict state schema.
    builder = StateGraph(_CopilotState)  # ty: ignore[invalid-argument-type]
    builder.add_node("agent", call_model)
    builder.add_node("tools", call_tools)
    builder.add_node("limit", stop_at_limit)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_model,
        {"tools": "tools", "limit": "limit", "__end__": END},
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("limit", END)
    return builder.compile(checkpointer=checkpointer)


def _member_tools(
    retrieval_tools: Sequence[BaseTool],
    member_id: str,
    as_of: date | None,
) -> tuple[BaseTool, ...]:
    return tuple(
        _member_tool(retrieval_tool, member_id, as_of)
        for retrieval_tool in retrieval_tools
    )


def _member_tool(
    retrieval_tool: BaseTool,
    member_id: str,
    as_of: date | None,
) -> BaseTool:
    def retrieve() -> object:
        return retrieval_tool.invoke({"member_id": member_id, "as_of": as_of})

    return StructuredTool.from_function(
        func=retrieve,
        name=retrieval_tool.name,
        description=retrieval_tool.description,
        args_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )


def _system_prompt(tone_facts: tuple[CopilotToneFact, ...]) -> str:
    if not tone_facts:
        return _SYSTEM_PROMPT
    facts = "\n".join(f"{fact.label}: {fact.value}" for fact in tone_facts)
    return f"{_SYSTEM_PROMPT}\n\nTone facts:\n{facts}"


def _thread_config(member_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": member_id}}


def _current_turn_messages(messages: Sequence[AnyMessage]) -> tuple[AnyMessage, ...]:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return tuple(messages[index:])
    raise RuntimeError("The copilot turn has no user message.")


def _final_answer(messages: Sequence[AnyMessage]) -> AIMessage:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return message
    raise RuntimeError("The copilot turn has no final answer.")


def _sources(messages: Iterable[AnyMessage]) -> tuple[CopilotSource, ...]:
    sources: list[CopilotSource] = []
    for message in messages:
        if not isinstance(message, ToolMessage) or message.name is None:
            continue
        raw_node_ids = message.additional_kwargs.get("node_ids")
        node_ids = (
            tuple(node_id for node_id in raw_node_ids if isinstance(node_id, str))
            if isinstance(raw_node_ids, list)
            else ()
        )
        sources.append(CopilotSource(tool=message.name, node_ids=node_ids))
    return tuple(sources)


def _history_messages(messages: Sequence[object]) -> tuple[CopilotHistoryMessage, ...]:
    history: list[CopilotHistoryMessage] = []
    user_message: HumanMessage | None = None
    turn_messages: list[AnyMessage] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            user_message = message
            turn_messages = [message]
            continue
        if user_message is None or not isinstance(message, BaseMessage):
            continue
        turn_messages.append(cast("AnyMessage", message))
        if not isinstance(message, AIMessage) or message.tool_calls:
            continue
        history.extend(
            (
                CopilotHistoryMessage(
                    id=user_message.id or f"user-{uuid4()}",
                    role="user",
                    text=_message_text(user_message),
                    sources=(),
                ),
                CopilotHistoryMessage(
                    id=message.id or f"assistant-{uuid4()}",
                    role="assistant",
                    text=_message_text(message),
                    sources=_sources(turn_messages),
                ),
            )
        )
        user_message = None
        turn_messages = []
    return tuple(history)


def _message_text(message: BaseMessage) -> str:
    return str(message.text).strip()
