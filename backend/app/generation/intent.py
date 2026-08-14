from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.generation.llm import IntentLLM, LLMProviderError, build_intent_llm

type Focus = Literal[
    "full-body",
    "upper-body",
    "lower-body",
    "core",
    "conditioning",
    "mobility",
]
type InterpretationFailureReason = Literal[
    "llm-unavailable",
    "provider-error",
    "invalid-output",
]

_FOCUSES: frozenset[str] = frozenset(
    {
        "full-body",
        "upper-body",
        "lower-body",
        "core",
        "conditioning",
        "mobility",
    }
)
_SYSTEM_PROMPT = """You interpret one coach message for workout generation.
Return raw mention strings only. Never return graph concept ids or normalized terms.
Choose focus from the schema. Use null when the coach did not state a focus.
Targets are requested muscles or body regions. Exclusions are exercises to omit.
Injuries are current pain, injuries, or conditions. Equipment is explicitly available equipment.
For an equipment override, include only the equipment the coach says is available.
An adjustment is interpreted with the same fields as an initial coach message."""


@dataclass(frozen=True)
class Intent:
    focus: Focus | None
    targets: tuple[str, ...]
    exclusions: tuple[str, ...]
    injuries: tuple[str, ...]
    equipment: tuple[str, ...]


@dataclass(frozen=True)
class InterpretationFailure:
    reason: InterpretationFailureReason
    message: str
    attempts: int


def interpret(
    coach_message: str,
    *,
    llm: IntentLLM | None = None,
) -> Intent | InterpretationFailure:
    """Interpret a coach message once, with one retry before visible failure."""
    intent_llm = llm or build_intent_llm()
    if intent_llm is None:
        return InterpretationFailure(
            reason="llm-unavailable",
            message="Coach message interpretation is unavailable.",
            attempts=0,
        )

    messages: Sequence[BaseMessage] = (
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=coach_message),
    )
    failure_reason: InterpretationFailureReason = "invalid-output"

    for _attempt in range(2):
        try:
            payload = intent_llm.invoke(messages)
        except LLMProviderError:
            failure_reason = "provider-error"
            continue

        intent = _intent_from_payload(payload)
        if intent is not None:
            return intent
        failure_reason = "invalid-output"

    return InterpretationFailure(
        reason=failure_reason,
        message="I could not interpret that coach message. Please rephrase it.",
        attempts=2,
    )


def _intent_from_payload(payload: object) -> Intent | None:
    if not isinstance(payload, Mapping):
        return None

    focus = payload.get("focus")
    if focus is not None and (not isinstance(focus, str) or focus not in _FOCUSES):
        return None

    targets = _mentions(payload.get("targets"))
    exclusions = _mentions(payload.get("exclusions"))
    injuries = _mentions(payload.get("injuries"))
    equipment = _mentions(payload.get("equipment"))
    if targets is None or exclusions is None or injuries is None or equipment is None:
        return None

    return Intent(
        focus=cast("Focus | None", focus),
        targets=targets,
        exclusions=exclusions,
        injuries=injuries,
        equipment=equipment,
    )


def _mentions(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    if any(not isinstance(mention, str) or not mention.strip() for mention in value):
        return None
    return tuple(value)
