import os
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

_DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLMProviderError(Exception):
    pass


class CopilotLLM(Protocol):
    def invoke(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> object: ...


@dataclass(frozen=True)
class CopilotLLMCall:
    messages: tuple[BaseMessage, ...]
    tool_names: tuple[str, ...]


class _OpenRouterCopilotLLM:
    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat_model = chat_model

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> object:
        try:
            return self._chat_model.bind_tools(list(tools)).invoke(list(messages))
        except Exception as error:
            raise LLMProviderError from error


class FakeCopilotLLM:
    def __init__(self, responses: Iterable[AIMessage | Exception | object]) -> None:
        self._responses = deque(responses)
        self._calls: list[CopilotLLMCall] = []

    @property
    def calls(self) -> tuple[CopilotLLMCall, ...]:
        return tuple(self._calls)

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> object:
        self._calls.append(
            CopilotLLMCall(
                messages=tuple(messages),
                tool_names=tuple(tool.name for tool in tools),
            )
        )
        if not self._responses:
            raise LLMProviderError("Fake copilot LLM response queue is empty.")

        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def build_copilot_llm(chat_model: BaseChatModel | None = None) -> CopilotLLM | None:
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
    return _OpenRouterCopilotLLM(chat_model)
