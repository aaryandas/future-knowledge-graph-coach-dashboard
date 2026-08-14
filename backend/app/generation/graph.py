from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.generation._catalog import (
    read_catalog_exercises,
    read_generation_member_context,
)
from app.generation._model import (
    Candidate,
    CatalogExercise,
    GenerationFailure,
    GenerationMemberContext,
    Plan,
    ResolvedIntent,
    ResolvedMention,
)
from app.generation._packing import PackingFailure, pack
from app.generation._resolution import resolve_intent
from app.generation._trace import TraceEvent, VerdictTraceEvent
from app.generation.intent import Intent, InterpretationFailure, interpret
from app.generation.llm import IntentLLM
from app.safety import AgentDecision, GraphDecision, Verdict, evaluate_safety

type CatalogReader = Callable[[], tuple[CatalogExercise, ...]]
type MemberContextReader = Callable[[str], GenerationMemberContext | None]
type VerdictEvaluator = Callable[[str, tuple[str, ...]], tuple[Verdict, ...]]
type GenerationRoute = Literal["resolve", "pack", "__end__"]


class _GenerationState(TypedDict, total=False):
    member_id: str
    coach_message: str
    window: int
    intent: Intent | None
    resolved_intent: ResolvedIntent | None
    catalog: tuple[CatalogExercise, ...]
    verdicts: tuple[Verdict, ...]
    candidates: tuple[Candidate, ...]
    plan: Plan | None
    trace: tuple[TraceEvent, ...]
    failure: GenerationFailure | None


@dataclass(frozen=True)
class GenerationTurn:
    message_id: str
    plan: Plan | None
    trace: tuple[TraceEvent, ...]
    resolved_intent: ResolvedIntent | None
    failure: GenerationFailure | None
    text: str


def run_generation_session(
    member_id: str,
    coach_message: str,
    window: int,
    thread_id: str,
    *,
    checkpointer: BaseCheckpointSaver[Any],
    llm: IntentLLM | None = None,
    message_id: str | None = None,
    catalog_reader: CatalogReader = read_catalog_exercises,
    member_context_reader: MemberContextReader = read_generation_member_context,
    verdict_evaluator: VerdictEvaluator = evaluate_safety,
) -> GenerationTurn:
    """Run one checkpointed generation turn using the useChat thread id."""
    if not coach_message.strip():
        raise ValueError("A generation message cannot be empty.")
    if not thread_id.strip():
        raise ValueError("A generation thread id cannot be empty.")

    graph = _build_graph(
        checkpointer=checkpointer,
        llm=llm,
        catalog_reader=catalog_reader,
        member_context_reader=member_context_reader,
        verdict_evaluator=verdict_evaluator,
    )
    state = cast(
        _GenerationState,
        graph.invoke(
            {
                "member_id": member_id,
                "coach_message": coach_message.strip(),
                "window": window,
                "intent": None,
                "resolved_intent": None,
                "catalog": (),
                "verdicts": (),
                "candidates": (),
                "plan": None,
                "trace": (),
                "failure": None,
            },
            _thread_config(thread_id),
        ),
    )
    failure = state.get("failure")
    return GenerationTurn(
        message_id=f"{message_id or thread_id}-assistant",
        plan=state.get("plan"),
        trace=state.get("trace", ()),
        resolved_intent=state.get("resolved_intent"),
        failure=failure,
        text=failure.message if failure is not None else "Session ready.",
    )


def _build_graph(
    *,
    checkpointer: BaseCheckpointSaver[Any],
    llm: IntentLLM | None,
    catalog_reader: CatalogReader,
    member_context_reader: MemberContextReader,
    verdict_evaluator: VerdictEvaluator,
) -> Any:
    def interpret_node(state: _GenerationState) -> dict[str, object]:
        result = interpret(state["coach_message"], llm=llm)
        if isinstance(result, InterpretationFailure):
            return {
                "failure": GenerationFailure(
                    reason=result.reason,
                    message=result.message,
                    attempts=result.attempts,
                )
            }
        return {"intent": result}

    def route_after_interpret(state: _GenerationState) -> GenerationRoute:
        return "__end__" if state.get("failure") is not None else "resolve"

    def resolve_node(state: _GenerationState) -> dict[str, object]:
        intent = state.get("intent")
        if intent is None:
            raise RuntimeError("The resolve node has no Intent")
        resolved, events = resolve_intent(intent)
        return {
            "resolved_intent": resolved,
            "trace": (*state.get("trace", ()), *events),
        }

    def verdicts_node(state: _GenerationState) -> dict[str, object]:
        catalog = catalog_reader()
        exercise_ids = tuple(exercise.exercise_id for exercise in catalog)
        verdicts = verdict_evaluator(state["member_id"], exercise_ids)
        return {
            "catalog": catalog,
            "verdicts": verdicts,
            "trace": (*state.get("trace", ()), *_verdict_events(verdicts)),
        }

    def rank_node(state: _GenerationState) -> dict[str, object]:
        member_context = member_context_reader(state["member_id"])
        if member_context is None:
            return {
                "failure": GenerationFailure(
                    reason="member-not-found",
                    message="Member not found.",
                )
            }
        resolved = state.get("resolved_intent")
        if resolved is None:
            raise RuntimeError("The rank node has no resolved Intent")
        return {
            "candidates": _rank_inputs(
                state.get("catalog", ()),
                state.get("verdicts", ()),
                resolved,
                member_context,
            )
        }

    def route_after_rank(state: _GenerationState) -> GenerationRoute:
        return "__end__" if state.get("failure") is not None else "pack"

    def pack_node(state: _GenerationState) -> dict[str, object]:
        intent = state.get("intent")
        if intent is None:
            raise RuntimeError("The pack node has no Intent")
        result = pack(state.get("candidates", ()), intent, state["window"])
        if isinstance(result, PackingFailure):
            return {
                "failure": GenerationFailure(
                    reason=result.reason,
                    message=result.message,
                    section=result.section,
                ),
                "trace": (*state.get("trace", ()), *result.events),
            }
        plan, events = result
        return {
            "plan": plan,
            "trace": (*state.get("trace", ()), *events),
        }

    # ty cannot recognize LangGraph's supported TypedDict state schema.
    builder = StateGraph(_GenerationState)  # ty: ignore[invalid-argument-type]
    builder.add_node("interpret", interpret_node)
    builder.add_node("resolve", resolve_node)
    builder.add_node("verdicts", verdicts_node)
    builder.add_node("rank", rank_node)
    builder.add_node("pack", pack_node)
    builder.add_edge(START, "interpret")
    builder.add_conditional_edges(
        "interpret",
        route_after_interpret,
        {"resolve": "resolve", "__end__": END},
    )
    builder.add_edge("resolve", "verdicts")
    builder.add_edge("verdicts", "rank")
    builder.add_conditional_edges(
        "rank",
        route_after_rank,
        {"pack": "pack", "__end__": END},
    )
    builder.add_edge("pack", END)
    return builder.compile(checkpointer=checkpointer)


def _rank_inputs(
    catalog: tuple[CatalogExercise, ...],
    verdicts: tuple[Verdict, ...],
    resolved_intent: ResolvedIntent,
    member_context: GenerationMemberContext,
) -> tuple[Candidate, ...]:
    verdict_by_exercise_id = {verdict.exercise_id: verdict for verdict in verdicts}
    target_ids = _resolved_ids(resolved_intent.targets)
    exclusion_ids = _resolved_ids(resolved_intent.constraints.exclusions)
    equipment_override = resolved_intent.constraints.equipment_override
    available_equipment_ids = (
        frozenset(member_context.equipment_ids)
        if equipment_override is None
        else _resolved_ids(equipment_override)
    )
    disliked_exercise_ids = frozenset(member_context.disliked_exercise_ids)
    return tuple(
        Candidate(
            exercise_id=exercise.exercise_id,
            name=exercise.name,
            movement_patterns=exercise.movement_patterns,
            muscle_groups=exercise.muscle_groups,
            priority_tier=exercise.priority_tier,
            is_reps=exercise.is_reps,
            is_duration=exercise.is_duration,
            supports_weight=exercise.supports_weight,
            estimated_rep_duration=exercise.estimated_rep_duration,
            is_bilateral=exercise.is_bilateral,
            side=exercise.side,
            bilateral_pair_id=exercise.bilateral_pair_id,
            verdict=verdict_by_exercise_id[exercise.exercise_id],
            goal_match=bool(
                target_ids.intersection(
                    (*exercise.muscle_group_ids, *exercise.joint_ids)
                )
            ),
            disliked=exercise.exercise_id in disliked_exercise_ids,
            has_required_equipment=frozenset(exercise.equipment_ids).issubset(
                available_equipment_ids
            ),
            explicitly_excluded=exercise.exercise_id in exclusion_ids,
        )
        for exercise in catalog
    )


def _resolved_ids(mentions: tuple[ResolvedMention, ...]) -> frozenset[str]:
    return frozenset(
        mention.resolution.concept_id
        for mention in mentions
        if mention.enforced and mention.resolution.concept_id is not None
    )


def _verdict_events(verdicts: tuple[Verdict, ...]) -> tuple[VerdictTraceEvent, ...]:
    events: list[VerdictTraceEvent] = []
    for verdict in verdicts:
        for decision in verdict.decisions:
            if isinstance(decision, GraphDecision):
                walked_path = decision.walked_path
                layer = decision.layer
            elif isinstance(decision, AgentDecision):
                walked_path = verdict.walked_path
                layer = None
            else:
                raise TypeError("Verdict contains an unknown decision")
            events.append(
                VerdictTraceEvent(
                    exercise_id=verdict.exercise_id,
                    status=decision.status,
                    layer=layer,
                    reason=decision.reason,
                    walked_path=walked_path,
                    used=tuple(node.node_id for node in walked_path.nodes),
                    was_attributed_to=decision.kind,
                )
            )
    return tuple(events)


def _thread_config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}
