from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
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
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from app.copilot.actions import (
    COACH_ACTION_TOOL_NAMES,
    COACH_ACTION_TOOLS,
    CoachAction,
    CoachActionWriter,
    SendMemberMessage,
    SessionPlanReader,
    SessionPlanVerdictEvaluator,
    WriteSessionPlan,
    coach_action_decision,
    coach_action_from_payload,
    coach_action_from_tool_call,
    coach_action_payload,
    prepare_coach_action,
    write_coach_action,
)
from app.copilot.context import CopilotToneFact, get_copilot_tone_facts
from app.copilot.llm import CopilotLLM, build_copilot_llm
from app.copilot.tools import RETRIEVAL_TOOLS, morning_brief_data
from app.graph import MorningBrief

type QuickPromptId = Literal[
    "show-brief",
    "adherence-trend",
    "sleep-week",
    "changes",
]
type HistoryRole = Literal["user", "assistant"]
type AgentRoute = Literal["tools", "action", "limit", "__end__"]

MAX_TOOL_ROUNDS = 5
_DATA_PARTS_KEY = "copilot_data_parts"
_DATA_PART_ORDER = {
    "data-chart": 0,
    "data-sources": 1,
    "data-brief": 2,
    "data-action": 3,
}
_FAILURE_MESSAGE = "I could not answer that question. Please try again."
_ROUND_LIMIT_MESSAGE = (
    "I could not complete that answer within five retrieval tool rounds. "
    "Please narrow the question and try again."
)
_SYSTEM_PROMPT = """You are the coach copilot for one member.
Answer only from retrieval tool results in this thread. Use a retrieval tool before
making a member-specific claim. The tools are already scoped to the current member.
Call all retrieval tools you need together in the first tool round. After successful
results, answer directly unless a result is empty or the user asked for facts that still
lack a current-turn source. For a chart request, call render_chart and select only its
kind and window. Never invent a value, chart point, or node id. Treat Journey stage and
Churn risk as tone guidance, not answer evidence. A coach action is only a proposal
until the coach confirms it. After at most five retrieval tool rounds, answer in no more
than 100 words."""


class _CopilotState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_rounds: int
    pending_action: dict[str, JsonValue] | None


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


type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)


@dataclass(frozen=True)
class CopilotDataPart:
    type: str
    data: JsonValue


@dataclass(frozen=True)
class CopilotTurn:
    message_id: str
    text: str
    data_parts: tuple[CopilotDataPart, ...]


type CopilotConflictKind = Literal[
    "pending-action",
    "no-pending-action",
    "action-id-mismatch",
    "invalid-resolution",
]


@dataclass(frozen=True)
class CopilotConflict:
    kind: CopilotConflictKind
    detail: str


type CopilotTurnResult = CopilotTurn | CopilotConflict


@dataclass(frozen=True)
class CopilotHistoryMessage:
    id: str
    role: HistoryRole
    text: str
    data_parts: tuple[CopilotDataPart, ...]


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
    action_writer: CoachActionWriter = write_coach_action,
    session_plan_reader: SessionPlanReader | None = None,
    verdict_evaluator: SessionPlanVerdictEvaluator | None = None,
) -> CopilotTurnResult:
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
        member_id,
        action_writer,
        session_plan_reader,
        verdict_evaluator,
    )
    if graph.get_state(_thread_config(member_id)).interrupts:
        return CopilotConflict(
            kind="pending-action",
            detail="Resolve the pending coach action before starting a new turn.",
        )
    state = cast(
        "_CopilotState",
        graph.invoke(
            {
                "messages": [HumanMessage(content=user_text, id=user_message_id)],
                "tool_rounds": 0,
                "pending_action": None,
            },
            _thread_config(member_id),
        ),
    )
    answer = _final_answer(state["messages"])
    return CopilotTurn(
        message_id=answer.id or assistant_message_id,
        text=_message_text(answer),
        data_parts=_data_parts(answer),
    )


def resume_copilot_action(
    member_id: str,
    action_id: str,
    resolution: dict[str, object],
    *,
    checkpointer: BaseCheckpointSaver[Any],
    retrieval_tools: Sequence[BaseTool] = RETRIEVAL_TOOLS,
    action_writer: CoachActionWriter = write_coach_action,
) -> CopilotTurnResult:
    """Resume the member thread at its pending coach action interrupt."""
    graph = _build_graph(
        None,
        _member_tools(retrieval_tools, member_id, None),
        (),
        f"action-{action_id}",
        checkpointer,
        member_id,
        action_writer,
        None,
        None,
    )
    snapshot = graph.get_state(_thread_config(member_id))
    if not snapshot.interrupts:
        return CopilotConflict(
            kind="no-pending-action",
            detail="The member thread has no pending coach action.",
        )
    if len(snapshot.interrupts) != 1:
        raise RuntimeError(
            "A member thread cannot have multiple coach action interrupts."
        )
    interrupt_value = snapshot.interrupts[0].value
    if (
        not isinstance(interrupt_value, dict)
        or interrupt_value.get("type") != "data-action"
        or not isinstance((data := interrupt_value.get("data")), dict)
    ):
        raise RuntimeError(
            "A coach action interrupt must contain a data-action payload."
        )
    if data.get("action_id") != action_id:
        return CopilotConflict(
            kind="action-id-mismatch",
            detail="The pending coach action does not match this action id.",
        )
    pending_action = coach_action_from_payload(data)
    if pending_action is None:
        raise RuntimeError("A coach action interrupt requires a pending action.")
    resume_value = {"action_id": action_id, **resolution}
    if coach_action_decision(pending_action, resume_value) is None:
        return CopilotConflict(
            kind="invalid-resolution",
            detail="The coach action resolution is invalid.",
        )
    state = cast(
        "_CopilotState",
        graph.invoke(
            Command(resume=resume_value),
            _thread_config(member_id),
        ),
    )
    answer = _final_answer(state["messages"])
    return CopilotTurn(
        message_id=answer.id or f"action-{action_id}",
        text=_message_text(answer),
        data_parts=_data_parts(answer),
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
) -> CopilotTurnResult:
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
    member_id: str,
    action_writer: CoachActionWriter,
    session_plan_reader: SessionPlanReader | None,
    verdict_evaluator: SessionPlanVerdictEvaluator | None,
) -> Any:
    tool_by_name = {tool.name: tool for tool in member_tools}

    def fallback(state: _CopilotState) -> dict[str, list[AIMessage]]:
        return {
            "messages": [
                _fallback_message(
                    assistant_message_id,
                    _sources(state["messages"]),
                    _current_tool_data_parts(state["messages"]),
                )
            ]
        }

    def call_model(state: _CopilotState) -> dict[str, list[AIMessage]]:
        if llm is None:
            return fallback(state)
        messages: tuple[BaseMessage, ...] = (
            SystemMessage(content=_system_prompt(tone_facts)),
            *_model_context(state["messages"]),
        )
        try:
            response = llm.invoke(
                messages,
                member_tools,
                require_tool_call=not _has_current_turn_retrieval(state["messages"]),
            )
        except Exception:  # noqa: BLE001 - every LLM adapter failure degrades here.
            return fallback(state)
        if not isinstance(response, AIMessage) or response.invalid_tool_calls:
            return fallback(state)
        if not response.tool_calls and not _message_text(response):
            return fallback(state)
        if not response.tool_calls:
            if not _has_current_turn_retrieval(state["messages"]):
                return fallback(state)
            return {
                "messages": [
                    _answer_message(
                        response,
                        assistant_message_id,
                        _sources(state["messages"]),
                        _current_tool_data_parts(state["messages"]),
                    )
                ]
            }
        action_calls = [
            tool_call
            for tool_call in response.tool_calls
            if tool_call["name"] in COACH_ACTION_TOOL_NAMES
        ]
        if action_calls and (
            len(response.tool_calls) != 1
            or coach_action_from_tool_call(
                action_calls[0].get("id") or "",
                action_calls[0]["name"],
                action_calls[0].get("args", {}),
            )
            is None
        ):
            return fallback(state)
        response_id = response.id or f"tool-call-{uuid4()}"
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
            additional_kwargs: dict[str, object] = {"node_ids": list(node_ids)}
            data_part = getattr(result, "data_part", None)
            if _is_data_part_payload(data_part):
                additional_kwargs[_DATA_PARTS_KEY] = [data_part]
            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    name=name,
                    tool_call_id=tool_call["id"],
                    additional_kwargs=additional_kwargs,
                )
            )
        return {
            "messages": tool_messages,
            "tool_rounds": state["tool_rounds"] + 1,
        }

    def propose_action(state: _CopilotState) -> dict[str, object]:
        response = cast("AIMessage", state["messages"][-1])
        tool_call = response.tool_calls[0]
        request = coach_action_from_tool_call(
            tool_call.get("id") or "",
            tool_call["name"],
            tool_call.get("args", {}),
        )
        if request is None:
            raise RuntimeError("A routed coach action must be valid.")
        proposal = (
            prepare_coach_action(member_id, request)
            if session_plan_reader is None or verdict_evaluator is None
            else prepare_coach_action(
                member_id,
                request,
                session_plan_reader=session_plan_reader,
                verdict_evaluator=verdict_evaluator,
            )
        )
        action = proposal.action
        if proposal.status != "pending":
            return {
                "messages": [
                    ToolMessage(
                        content="The coach action cannot be confirmed.",
                        name=tool_call["name"],
                        tool_call_id=action.action_id,
                        additional_kwargs={"coach_action": True},
                    ),
                    _coach_action_message(
                        action,
                        proposal.status,
                        _sources(state["messages"]),
                    ),
                ],
                "pending_action": None,
            }
        return {
            "messages": [
                ToolMessage(
                    content="Awaiting coach confirmation.",
                    name=tool_call["name"],
                    tool_call_id=action.action_id,
                    additional_kwargs={"coach_action": True},
                ),
                _coach_action_message(
                    action,
                    "pending",
                    _sources(state["messages"]),
                ),
            ],
            "pending_action": cast(
                "dict[str, JsonValue]",
                _json_value(coach_action_payload(action, "pending")),
            ),
        }

    def route_after_proposal(state: _CopilotState) -> Literal["gate", "__end__"]:
        return "gate" if state["pending_action"] is not None else "__end__"

    def gate_action(state: _CopilotState) -> dict[str, object]:
        pending_action_payload = state["pending_action"]
        pending_action = coach_action_from_payload(pending_action_payload)
        if pending_action is None:
            raise RuntimeError("A coach action interrupt requires a pending action.")
        resumed = interrupt(
            {
                "type": "data-action",
                "data": pending_action_payload,
            }
        )
        decision = coach_action_decision(pending_action, resumed)
        if decision is None:
            raise RuntimeError("A validated coach action resolution must be valid.")
        sources = _sources(state["messages"])
        if decision.decision == "discard":
            return {
                "messages": [
                    _coach_action_message(
                        decision.action,
                        "discarded",
                        sources,
                    )
                ],
                "pending_action": None,
            }
        result = action_writer(member_id, decision.action)
        if result.status == "target-not-found":
            return {
                "messages": [
                    _coach_action_message(
                        decision.action,
                        "failed",
                        sources,
                        actor=result.actor,
                        timestamp=result.timestamp,
                    )
                ],
                "pending_action": None,
            }
        return {
            "messages": [
                _coach_action_message(
                    decision.action,
                    "confirmed",
                    sources,
                    morning_brief=result.morning_brief,
                    actor=result.actor,
                    timestamp=result.timestamp,
                )
            ],
            "pending_action": None,
        }

    def route_after_model(state: _CopilotState) -> AgentRoute:
        response = state["messages"][-1]
        if not isinstance(response, AIMessage) or not response.tool_calls:
            return "__end__"
        if response.tool_calls[0]["name"] in COACH_ACTION_TOOL_NAMES:
            return "action"
        if state["tool_rounds"] >= MAX_TOOL_ROUNDS:
            return "limit"
        return "tools"

    def stop_at_limit(state: _CopilotState) -> dict[str, list[AIMessage]]:
        return {
            "messages": [
                _answer_message(
                    AIMessage(content=_ROUND_LIMIT_MESSAGE),
                    assistant_message_id,
                    _sources(state["messages"]),
                    _current_tool_data_parts(state["messages"]),
                )
            ]
        }

    # ty cannot recognize LangGraph's supported TypedDict state schema.
    builder = StateGraph(_CopilotState)  # ty: ignore[invalid-argument-type]
    builder.add_node("agent", call_model)
    builder.add_node("tools", call_tools)
    builder.add_node("propose_action", propose_action)
    builder.add_node("gate_action", gate_action)
    builder.add_node("limit", stop_at_limit)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_model,
        {
            "tools": "tools",
            "action": "propose_action",
            "limit": "limit",
            "__end__": END,
        },
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges(
        "propose_action",
        route_after_proposal,
        {"gate": "gate_action", "__end__": END},
    )
    builder.add_edge("gate_action", END)
    builder.add_edge("limit", END)
    return builder.compile(checkpointer=checkpointer)


def _member_tools(
    retrieval_tools: Sequence[BaseTool],
    member_id: str,
    as_of: date | None,
) -> tuple[BaseTool, ...]:
    return (
        *(
            _member_tool(retrieval_tool, member_id, as_of)
            for retrieval_tool in retrieval_tools
        ),
        *COACH_ACTION_TOOLS,
    )


def _member_tool(
    retrieval_tool: BaseTool,
    member_id: str,
    as_of: date | None,
) -> BaseTool:
    def retrieve(**arguments: object) -> object:
        return retrieval_tool.invoke(
            {**arguments, "member_id": member_id, "as_of": as_of}
        )

    input_schema = retrieval_tool.get_input_jsonschema()
    raw_properties = input_schema.get("properties")
    properties = (
        {
            key: value
            for key, value in raw_properties.items()
            if key not in {"member_id", "as_of"}
        }
        if isinstance(raw_properties, dict)
        else {}
    )
    raw_required = input_schema.get("required")
    required = (
        [
            key
            for key in raw_required
            if isinstance(key, str) and key not in {"member_id", "as_of"}
        ]
        if isinstance(raw_required, list)
        else []
    )
    definitions = input_schema.get("$defs")
    args_schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    if isinstance(definitions, dict):
        args_schema["$defs"] = definitions

    return StructuredTool.from_function(
        func=retrieve,
        name=retrieval_tool.name,
        description=retrieval_tool.description,
        args_schema=args_schema,
    )


def _system_prompt(tone_facts: tuple[CopilotToneFact, ...]) -> str:
    if not tone_facts:
        return _SYSTEM_PROMPT
    facts = "\n".join(f"{fact.label}: {fact.value}" for fact in tone_facts)
    return f"{_SYSTEM_PROMPT}\n\nTone facts:\n{facts}"


def _model_context(messages: Sequence[AnyMessage]) -> tuple[BaseMessage, ...]:
    current_turn_start = next(
        index
        for index in range(len(messages) - 1, -1, -1)
        if isinstance(messages[index], HumanMessage)
    )
    history: list[BaseMessage] = []
    for message in messages[:current_turn_start]:
        if isinstance(message, HumanMessage):
            history.append(message)
        elif isinstance(message, AIMessage) and not message.tool_calls:
            history.append(AIMessage(content=_message_text(message), id=message.id))
    return (*history, *messages[current_turn_start:])


def _thread_config(member_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": member_id}}


def _final_answer(messages: Sequence[AnyMessage]) -> AIMessage:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return message
    raise RuntimeError("The copilot turn has no final answer.")


def _sources(messages: Sequence[AnyMessage]) -> tuple[CopilotSource, ...]:
    sources: list[CopilotSource] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if (
            not isinstance(message, ToolMessage)
            or message.name is None
            or message.status == "error"
        ):
            continue
        raw_node_ids = message.additional_kwargs.get("node_ids")
        if not isinstance(raw_node_ids, list):
            continue
        node_ids = tuple(
            node_id for node_id in raw_node_ids if isinstance(node_id, str)
        )
        sources.append(CopilotSource(tool=message.name, node_ids=node_ids))
    return tuple(reversed(sources))


def _has_current_turn_retrieval(messages: Sequence[AnyMessage]) -> bool:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return False
        if isinstance(message, ToolMessage) and message.status != "error":
            return True
    raise RuntimeError("The copilot turn has no user message.")


def _fallback_message(
    message_id: str,
    sources: tuple[CopilotSource, ...],
    tool_data_parts: tuple[CopilotDataPart, ...],
) -> AIMessage:
    return _answer_message(
        AIMessage(content=_FAILURE_MESSAGE),
        message_id,
        sources,
        tool_data_parts,
    )


def _coach_action_message(
    action: CoachAction,
    status: Literal["pending", "confirmed", "discarded", "failed", "blocked"],
    sources: tuple[CopilotSource, ...],
    *,
    morning_brief: MorningBrief | None = None,
    actor: str | None = None,
    timestamp: str | None = None,
) -> AIMessage:
    if status == "pending":
        text = "Review this proposed coach action."
    elif status == "blocked":
        text = "The session plan contains an excluded row. Nothing was changed."
    elif status == "discarded":
        text = "Action discarded."
    elif status == "failed":
        text = "The action target no longer exists. Nothing was changed."
    elif isinstance(action, SendMemberMessage):
        text = "Message sent."
    elif isinstance(action, WriteSessionPlan):
        text = "Session plan updated."
    else:
        text = "Morning brief updated."
    parts = [_sources_part(sources)]
    if morning_brief is not None:
        parts.append(
            CopilotDataPart(
                type="data-brief",
                data=_json_value(asdict(morning_brief_data(morning_brief))),
            )
        )
    action_payload = coach_action_payload(action, status)
    if timestamp is not None:
        action_payload["actor"] = actor
        action_payload["timestamp"] = timestamp
    parts.append(
        CopilotDataPart(
            type="data-action",
            data=_json_value(action_payload),
        )
    )
    data_parts = _ordered_data_parts(tuple(parts))
    return AIMessage(
        content=text,
        id=f"action-{action.action_id}",
        additional_kwargs={
            _DATA_PARTS_KEY: [_data_part_payload(part) for part in data_parts]
        },
    )


def _answer_message(
    response: AIMessage,
    message_id: str,
    sources: tuple[CopilotSource, ...],
    tool_data_parts: tuple[CopilotDataPart, ...] = (),
) -> AIMessage:
    data_parts = _ordered_data_parts(
        (
            _sources_part(sources),
            *tool_data_parts,
            *(
                part
                for part in _data_parts(response)
                if part.type not in {"data-chart", "data-sources"}
            ),
        )
    )
    additional_kwargs = {
        **response.additional_kwargs,
        _DATA_PARTS_KEY: [_data_part_payload(part) for part in data_parts],
    }
    return response.model_copy(
        update={
            "id": response.id or message_id,
            "additional_kwargs": additional_kwargs,
        }
    )


def _sources_part(sources: tuple[CopilotSource, ...]) -> CopilotDataPart:
    data: JsonValue = {
        "sources": [
            {"tool": source.tool, "node_ids": list(source.node_ids)}
            for source in sources
        ]
    }
    return CopilotDataPart(type="data-sources", data=data)


def _ordered_data_parts(
    parts: tuple[CopilotDataPart, ...],
) -> tuple[CopilotDataPart, ...]:
    return tuple(sorted(parts, key=lambda part: _DATA_PART_ORDER.get(part.type, 4)))


def _data_part_payload(part: CopilotDataPart) -> dict[str, JsonValue]:
    return {"type": part.type, "data": part.data}


def _data_parts(message: BaseMessage) -> tuple[CopilotDataPart, ...]:
    raw_parts = message.additional_kwargs.get(_DATA_PARTS_KEY)
    if not isinstance(raw_parts, list):
        return ()
    data_parts: list[CopilotDataPart] = []
    for raw_part in raw_parts:
        if not isinstance(raw_part, dict):
            continue
        part_type = raw_part.get("type")
        data = raw_part.get("data")
        if (
            not isinstance(part_type, str)
            or not part_type.startswith("data-")
            or not _is_json_value(data)
        ):
            continue
        data_parts.append(CopilotDataPart(type=part_type, data=cast("JsonValue", data)))
    return tuple(data_parts)


def _current_tool_data_parts(
    messages: Sequence[AnyMessage],
) -> tuple[CopilotDataPart, ...]:
    parts: list[CopilotDataPart] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage):
            parts.extend(reversed(_data_parts(message)))
    return tuple(reversed(parts))


def _is_data_part_payload(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    part_type = value.get("type")
    return (
        isinstance(part_type, str)
        and part_type.startswith("data-")
        and _is_json_value(value.get("data"))
    )


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item) for key, item in value.items()
        )
    return False


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise TypeError("A copilot data part must contain JSON values.")


def _history_messages(messages: Sequence[object]) -> tuple[CopilotHistoryMessage, ...]:
    history: list[CopilotHistoryMessage] = []
    user_message: HumanMessage | None = None
    persisted_messages: list[AnyMessage] = []
    for message in messages:
        if isinstance(message, BaseMessage):
            persisted_messages.append(cast("AnyMessage", message))
        if isinstance(message, HumanMessage):
            user_message = message
            continue
        if user_message is None or not isinstance(message, BaseMessage):
            continue
        if not isinstance(message, AIMessage) or message.tool_calls:
            continue
        data_parts = _data_parts(message)
        if not data_parts:
            data_parts = (_sources_part(_sources(persisted_messages)),)
        history.extend(
            (
                CopilotHistoryMessage(
                    id=user_message.id or f"user-{uuid4()}",
                    role="user",
                    text=_message_text(user_message),
                    data_parts=(),
                ),
                CopilotHistoryMessage(
                    id=message.id or f"assistant-{uuid4()}",
                    role="assistant",
                    text=_message_text(message),
                    data_parts=data_parts,
                ),
            )
        )
        user_message = None
    return tuple(history)


def _message_text(message: BaseMessage) -> str:
    return str(message.text).strip()
