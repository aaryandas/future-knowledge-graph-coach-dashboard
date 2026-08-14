import re
from collections.abc import Iterator, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.generation._model import Plan
from app.generation._trace import AgentTraceEvent, TraceEvent
from app.generation.llm import (
    AnnotationLLM,
    LLMProviderError,
    build_annotation_llm,
)

_MAX_NOTE_CHARACTERS = 400
_MAX_NOTE_SENTENCES = 2
_CAUTION_START = re.compile(
    r"(?:keep|use|stop|avoid|pause|monitor|stay)\b",
    re.IGNORECASE,
)
_LOOSENING_DIRECTIVE = re.compile(
    r"\b(?:"
    r"add|change|disregard|dismiss|heavier|ignore|increase|override|remove|replace|"
    r"resume|skip|swap|unsafe|extra|maximum|maximal|"
    r"push\s+through|full\s+range|more\s+(?:load|reps|sets|time|weight)"
    r")\b",
    re.IGNORECASE,
)
_SYSTEM_PROMPT = """You write short coaching notes for a completed workout plan.
The plan, doses, and safety verdicts are final. Your note is presentation-only.
You may add caution or recommend a more conservative execution.
Never remove, reduce, contradict, or tell the coach to ignore a safety restriction.
Never change the exercises or doses. Mention only exercises in the completed plan.
Write at most two short sentences. Return plain text only.
If there is no useful note, return no text."""


def annotate(
    plan: Plan,
    coach_message: str,
    *,
    llm: AnnotationLLM | None = None,
    trace: list[TraceEvent],
) -> Iterator[str]:
    """Stream optional coaching note parts without exposing provider failures."""
    annotation_llm = llm or build_annotation_llm()
    if annotation_llm is None:
        return

    messages: Sequence[BaseMessage] = (
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_annotation_context(plan, coach_message)),
    )
    try:
        parts = _validated_parts(annotation_llm.stream(messages))
        first_part = next(parts, None)
    except LLMProviderError:
        return
    if first_part is None:
        return

    trace.append(
        AgentTraceEvent(
            action="annotation",
            reason="Added a verified tighten-only coaching note.",
            used=tuple(
                entry.exercise_id
                for section in (plan.warm_up, plan.main, plan.cool_down)
                for entry in section.entries
            ),
        )
    )
    yield first_part
    try:
        yield from parts
    except LLMProviderError:
        return


def _annotation_context(plan: Plan, coach_message: str) -> str:
    rows = "\n".join(
        (
            f"- {section.section}: {entry.name}; "
            f"dose={_dose(entry)}; verdict={entry.verdict}; "
            f"caution={entry.caution_note or 'none'}"
        )
        for section in (plan.warm_up, plan.main, plan.cool_down)
        for entry in section.entries
    )
    return f"Coach message:\n{coach_message}\n\nCompleted plan:\n{rows}"


def _dose(entry) -> str:
    if entry.reps is not None:
        return f"{entry.sets} sets x {entry.reps} reps"
    return f"{entry.sets} sets x {entry.hold_minutes} minutes"


def _validated_parts(parts: Iterator[str]) -> Iterator[str]:
    remaining = _MAX_NOTE_CHARACTERS
    accepted = 0
    for sentence in _sentences(parts):
        note = sentence.strip()
        if not _is_tightening(note):
            continue
        prefix = " " if accepted else ""
        bounded = f"{prefix}{note}"[:remaining]
        if not bounded:
            return
        yield bounded
        accepted += 1
        remaining -= len(bounded)
        if remaining == 0 or accepted == _MAX_NOTE_SENTENCES:
            return


def _sentences(parts: Iterator[str]) -> Iterator[str]:
    buffered = ""
    for part in parts:
        buffered += part
        while match := re.search(r"[.!?](?:\s|$)", buffered):
            end = match.end()
            yield buffered[:end]
            buffered = buffered[end:]
    if buffered.strip():
        yield buffered


def _is_tightening(note: str) -> bool:
    first_word = note.split(maxsplit=1)[0] if note else ""
    return bool(_CAUTION_START.fullmatch(first_word)) and not bool(
        _LOOSENING_DIRECTIVE.search(note)
    )
