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
_MAX_CAUTION_TEXT_CHARACTERS = 200
_TIGHTENING_KINDS: frozenset[str] = frozenset(
    {"reduce-load", "reduce-range", "stop-on-pain", "add-rest"}
)
_SYSTEM_PROMPT = """You add optional cautions to a completed workout plan.
Return only the structured caution form. Each caution must reference one plan_item_id
from the completed plan and choose one tightening_kind from the schema.
Write a short caution_text for display. The completed exercise selection and doses are final.
Return an empty cautions list when no caution is useful."""


@dataclass(frozen=True)
class Caution:
    plan_item_id: str
    tightening_kind: TighteningKind
    caution_text: str


@dataclass(frozen=True)
class Annotation:
    cautions: tuple[Caution, ...]


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
    try:
        payload = _complete_payload(annotation_llm.stream(messages))
    except LLMProviderError:
        return

    annotation = _annotation_from_payload(payload, _plan_item_ids(plan))
    if annotation is None or not annotation.cautions:
        return

    record_trace_event(
        AgentTraceEvent(
            action="annotation",
            reason="Added a structurally validated tighten-only coaching note.",
            used=tuple(caution.plan_item_id for caution in annotation.cautions),
        )
    )
    for caution in annotation.cautions:
        yield caution.caution_text


def _complete_payload(parts: Iterator[object]) -> object:
    payload: object = None
    for payload in parts:
        pass
    return payload


def _annotation_from_payload(
    payload: object,
    plan_item_ids: frozenset[str],
) -> Annotation | None:
    if not isinstance(payload, Mapping) or set(payload) != {"cautions"}:
        return None

    caution_payloads = payload["cautions"]
    if not isinstance(caution_payloads, list) or len(caution_payloads) > _MAX_CAUTIONS:
        return None

    cautions: list[Caution] = []
    for caution_payload in caution_payloads:
        caution = _caution_from_payload(caution_payload, plan_item_ids)
        if caution is None:
            return None
        cautions.append(caution)
    return Annotation(cautions=tuple(cautions))


def _caution_from_payload(
    payload: object,
    plan_item_ids: frozenset[str],
) -> Caution | None:
    if not isinstance(payload, Mapping) or set(payload) != {
        "plan_item_id",
        "tightening_kind",
        "caution_text",
    }:
        return None

    plan_item_id = payload["plan_item_id"]
    tightening_kind = payload["tightening_kind"]
    caution_text = payload["caution_text"]
    if not isinstance(plan_item_id, str) or plan_item_id not in plan_item_ids:
        return None
    if not isinstance(tightening_kind, str) or tightening_kind not in _TIGHTENING_KINDS:
        return None
    if (
        not isinstance(caution_text, str)
        or not caution_text.strip()
        or len(caution_text) > _MAX_CAUTION_TEXT_CHARACTERS
    ):
        return None

    return Caution(
        plan_item_id=plan_item_id,
        tightening_kind=cast("TighteningKind", tightening_kind),
        caution_text=caution_text,
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


def _plan_item_ids(plan: Plan) -> frozenset[str]:
    return frozenset(
        entry.exercise_id
        for section in (plan.warm_up, plan.main, plan.cool_down)
        for entry in section.entries
    )


def _dose(entry) -> str:
    if entry.reps is not None:
        return f"{entry.sets} sets x {entry.reps} reps"
    return f"{entry.sets} sets x {entry.hold_minutes} minutes"
