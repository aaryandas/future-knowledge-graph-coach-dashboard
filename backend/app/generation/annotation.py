from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.generation._model import Plan
from app.generation._trace import AgentTraceEvent
from app.generation.llm import (
    AnnotationLLM,
    LLMProviderError,
    build_annotation_llm,
)

type TighteningKind = Literal[
    "reduce-load",
    "reduce-range",
    "stop-on-pain",
    "add-rest",
]

_MAX_CAUTIONS = 2
_TIGHTENING_TEMPLATES: dict[TighteningKind, str] = {
    "reduce-load": "Reduce the load on {exercise}.",
    "reduce-range": "Reduce the range of motion for {exercise}.",
    "stop-on-pain": "Stop {exercise} if you feel pain.",
    "add-rest": "Add more rest after {exercise}.",
}
_TIGHTENING_KINDS = frozenset(_TIGHTENING_TEMPLATES)
_SYSTEM_PROMPT = """You add optional cautions to a completed workout plan.
Return only the structured caution form. Each caution must reference one plan_item_id
from the completed plan and choose one tightening_kind from the schema.
The completed exercise selection and doses are final.
Return an empty cautions list when no caution is useful."""


@dataclass(frozen=True)
class Caution:
    plan_item_id: str
    tightening_kind: TighteningKind
    caution_text: str


def annotate(
    plan: Plan,
    coach_message: str,
    *,
    llm: AnnotationLLM | None = None,
    record_trace_event: Callable[[AgentTraceEvent], None],
) -> Iterator[str]:
    """Stream one validated caution form and drop provider failures."""
    annotation_llm = llm or build_annotation_llm()
    if annotation_llm is None:
        return

    messages: Sequence[BaseMessage] = (
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_annotation_context(plan, coach_message)),
    )
    plan_items = _plan_items(plan)
    emitted: set[tuple[str, TighteningKind]] = set()
    try:
        for payload in annotation_llm.stream(messages):
            for caution in _cautions_from_payload(payload, plan_items):
                key = (caution.plan_item_id, caution.tightening_kind)
                if key in emitted:
                    continue
                emitted.add(key)
                record_trace_event(
                    AgentTraceEvent(
                        action="annotation",
                        reason=(
                            "Added a structurally validated tighten-only coaching note."
                        ),
                        used=(caution.plan_item_id,),
                    )
                )
                yield caution.caution_text
                if len(emitted) == _MAX_CAUTIONS:
                    return
    except LLMProviderError:
        return


def _cautions_from_payload(
    payload: object,
    plan_items: Mapping[str, str],
) -> tuple[Caution, ...]:
    if not isinstance(payload, Mapping) or set(payload) != {"cautions"}:
        return ()

    caution_payloads = payload["cautions"]
    if not isinstance(caution_payloads, list) or len(caution_payloads) > _MAX_CAUTIONS:
        return ()

    return tuple(
        caution
        for caution_payload in caution_payloads
        if (caution := _caution_from_payload(caution_payload, plan_items)) is not None
    )


def _caution_from_payload(
    payload: object,
    plan_items: Mapping[str, str],
) -> Caution | None:
    if not isinstance(payload, Mapping) or set(payload) != {
        "plan_item_id",
        "tightening_kind",
    }:
        return None

    plan_item_id = payload["plan_item_id"]
    tightening_kind = payload["tightening_kind"]
    if not isinstance(plan_item_id, str) or plan_item_id not in plan_items:
        return None
    if not isinstance(tightening_kind, str) or tightening_kind not in _TIGHTENING_KINDS:
        return None

    kind = cast("TighteningKind", tightening_kind)
    return Caution(
        plan_item_id=plan_item_id,
        tightening_kind=kind,
        caution_text=_TIGHTENING_TEMPLATES[kind].format(
            exercise=plan_items[plan_item_id]
        ),
    )


def _annotation_context(plan: Plan, coach_message: str) -> str:
    rows = "\n".join(
        (
            f"- plan_item_id={entry.exercise_id}; section={section.section}; "
            f"exercise={entry.name}; dose={_dose(entry)}; verdict={entry.verdict}; "
            f"caution={entry.caution_note or 'none'}"
        )
        for section in (plan.warm_up, plan.main, plan.cool_down)
        for entry in section.entries
    )
    return f"Coach message:\n{coach_message}\n\nCompleted plan:\n{rows}"


def _plan_items(plan: Plan) -> dict[str, str]:
    return {
        entry.exercise_id: entry.name
        for section in (plan.warm_up, plan.main, plan.cool_down)
        for entry in section.entries
    }


def _dose(entry) -> str:
    if entry.reps is not None:
        return f"{entry.sets} sets x {entry.reps} reps"
    return f"{entry.sets} sets x {entry.hold_minutes} minutes"
