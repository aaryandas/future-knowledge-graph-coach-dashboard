import os
from collections.abc import Iterable, Iterator, Sequence
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.generation._model import Plan
from app.generation.llm import LLMProviderError

_DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_MAX_NOTE_CHARACTERS = 400
_SYSTEM_PROMPT = """You write short coaching notes for a completed workout plan.
The plan, doses, and safety verdicts are final. Your note is presentation-only.
You may add caution or recommend a more conservative execution.
Never remove, reduce, contradict, or tell the coach to ignore a safety restriction.
Never change the exercises or doses. Mention only exercises in the completed plan.
Write at most two short sentences. Return plain text only.
If there is no useful note, return no text."""


class AnnotationLLM(Protocol):
    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[str]: ...


class _OpenRouterAnnotationLLM:
    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat_model = chat_model

    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[str]:
        try:
            for chunk in self._chat_model.stream(list(messages)):
                if text := chunk.text:
                    yield text
        except Exception as error:
            raise LLMProviderError from error


class FakeAnnotationLLM:
    def __init__(self, parts: Iterable[str | LLMProviderError]) -> None:
        self._parts = tuple(parts)
        self._calls: list[tuple[BaseMessage, ...]] = []

    @property
    def calls(self) -> tuple[tuple[BaseMessage, ...], ...]:
        return tuple(self._calls)

    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[str]:
        self._calls.append(tuple(messages))
        for part in self._parts:
            if isinstance(part, LLMProviderError):
                raise part
            yield part


def annotate(
    plan: Plan,
    coach_message: str,
    *,
    llm: AnnotationLLM | None = None,
) -> Iterator[str]:
    """Stream optional coaching note parts without exposing provider failures."""
    annotation_llm = llm or build_annotation_llm()
    if annotation_llm is None:
        return

    messages: Sequence[BaseMessage] = (
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_annotation_context(plan, coach_message)),
    )
    buffered_parts: list[str] = []
    try:
        buffered_parts.extend(annotation_llm.stream(messages))
    except LLMProviderError:
        return

    yield from _bounded_parts(buffered_parts)


def build_annotation_llm(
    chat_model: BaseChatModel | None = None,
) -> AnnotationLLM | None:
    if chat_model is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return None

        chat_model = ChatOpenAI(
            api_key=api_key,
            base_url=_OPENROUTER_BASE_URL,
            model=os.getenv("OPENROUTER_MODEL") or _DEFAULT_MODEL,
            temperature=0,
            max_retries=0,
        )
    return _OpenRouterAnnotationLLM(chat_model)


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


def _bounded_parts(parts: list[str]) -> Iterator[str]:
    if not parts:
        return

    parts[0] = parts[0].lstrip()
    parts[-1] = parts[-1].rstrip()
    remaining = _MAX_NOTE_CHARACTERS
    for part in parts:
        bounded = part[:remaining]
        if bounded:
            yield bounded
            remaining -= len(bounded)
        if remaining == 0:
            return
