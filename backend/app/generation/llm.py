import os
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from openai import OpenAIError

_DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_INTENT_SCHEMA = {
    "title": "coach_message_intent",
    "description": "Raw mentions extracted from one coach workout message.",
    "type": "object",
    "properties": {
        "focus": {
            "anyOf": [
                {
                    "type": "string",
                    "enum": [
                        "full-body",
                        "upper-body",
                        "lower-body",
                        "core",
                        "conditioning",
                        "mobility",
                    ],
                },
                {"type": "null"},
            ],
            "description": "Workout focus, or null when the coach did not state one.",
        },
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verbatim target muscle or body-region mentions.",
        },
        "exclusions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verbatim exercise mentions that the coach excludes.",
        },
        "injuries": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verbatim injury, pain, or condition mentions.",
        },
        "equipment": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Verbatim mentions of explicitly available equipment.",
        },
    },
    "required": ["focus", "targets", "exclusions", "injuries", "equipment"],
    "additionalProperties": False,
}


class LLMProviderError(Exception):
    pass


class IntentLLM(Protocol):
    def invoke(self, messages: Sequence[BaseMessage]) -> object: ...


class AnnotationLLM(Protocol):
    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[str]: ...


class _OpenRouterLLM:
    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat_model = chat_model
        self._structured_llm = chat_model.with_structured_output(
            _INTENT_SCHEMA,
            method="json_schema",
        )

    def invoke(self, messages: Sequence[BaseMessage]) -> object:
        try:
            return self._structured_llm.invoke(list(messages))
        except Exception as error:
            raise LLMProviderError from error

    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[str]:
        try:
            for chunk in self._chat_model.stream(list(messages)):
                if text := chunk.text:
                    yield text
        except (ConnectionError, OpenAIError, TimeoutError) as error:
            raise LLMProviderError from error


class FakeLLM:
    def __init__(
        self,
        responses: Iterable[Mapping[str, object] | LLMProviderError],
    ) -> None:
        self._responses = deque(responses)
        self._calls: list[tuple[BaseMessage, ...]] = []

    @property
    def calls(self) -> tuple[tuple[BaseMessage, ...], ...]:
        return tuple(self._calls)

    def invoke(self, messages: Sequence[BaseMessage]) -> object:
        self._calls.append(tuple(messages))
        if not self._responses:
            raise LLMProviderError("Fake LLM response queue is empty.")

        response = self._responses.popleft()
        if isinstance(response, LLMProviderError):
            raise response
        return response


def build_intent_llm(chat_model: BaseChatModel | None = None) -> IntentLLM | None:
    return _build_openrouter_llm(chat_model)


def build_annotation_llm(
    chat_model: BaseChatModel | None = None,
) -> AnnotationLLM | None:
    return _build_openrouter_llm(chat_model)


def _build_openrouter_llm(chat_model: BaseChatModel | None) -> _OpenRouterLLM | None:
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
    return _OpenRouterLLM(chat_model)
