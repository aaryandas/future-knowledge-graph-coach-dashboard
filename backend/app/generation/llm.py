import os
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Protocol

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from openai import OpenAIError

_DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_LOW_LATENCY_PROVIDER_ROUTING = {"provider": {"sort": "latency"}}
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
_ANNOTATION_SCHEMA = {
    "title": "coaching_note_cautions",
    "description": "Optional tighten-only cautions for completed plan items.",
    "type": "object",
    "properties": {
        "cautions": {
            "type": "array",
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "plan_item_id": {
                        "type": "string",
                        "description": "An exercise id present in the completed plan.",
                    },
                    "tightening_kind": {
                        "type": "string",
                        "enum": [
                            "reduce-load",
                            "reduce-range",
                            "stop-on-pain",
                            "add-rest",
                        ],
                    },
                },
                "required": [
                    "plan_item_id",
                    "tightening_kind",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cautions"],
    "additionalProperties": False,
}


class LLMProviderError(Exception):
    pass


class IntentLLM(Protocol):
    def invoke(self, messages: Sequence[BaseMessage]) -> object: ...


class AnnotationLLM(Protocol):
    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[object]: ...


class _OpenRouterIntentLLM:
    def __init__(self, chat_model: BaseChatModel) -> None:
        self._structured_llm = chat_model.with_structured_output(
            _INTENT_SCHEMA,
            method="json_schema",
        )

    def invoke(self, messages: Sequence[BaseMessage]) -> object:
        try:
            return self._structured_llm.invoke(
                list(messages),
                extra_body=_LOW_LATENCY_PROVIDER_ROUTING,
            )
        except (
            ConnectionError,
            IndexError,
            OpenAIError,
            OutputParserException,
            TimeoutError,
        ) as error:
            raise LLMProviderError from error


class _OpenRouterAnnotationLLM:
    def __init__(self, chat_model: BaseChatModel) -> None:
        self._structured_llm = chat_model.with_structured_output(
            _ANNOTATION_SCHEMA,
            method="json_schema",
        )

    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[object]:
        try:
            yield from self._structured_llm.stream(list(messages))
        except (
            ConnectionError,
            IndexError,
            OpenAIError,
            OutputParserException,
            TimeoutError,
        ) as error:
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
    built_model = _build_openrouter_chat_model(chat_model)
    return _OpenRouterIntentLLM(built_model) if built_model is not None else None


def build_annotation_llm(
    chat_model: BaseChatModel | None = None,
) -> AnnotationLLM | None:
    built_model = _build_openrouter_chat_model(chat_model)
    return _OpenRouterAnnotationLLM(built_model) if built_model is not None else None


def _build_openrouter_chat_model(
    chat_model: BaseChatModel | None,
) -> BaseChatModel | None:
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
    return chat_model
