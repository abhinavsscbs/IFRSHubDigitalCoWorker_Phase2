"""LangChain-compatible OpenAI Responses client used by every generation task."""
from functools import lru_cache
from typing import Any

from openai import OpenAI, AsyncOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .config import (
    OPENAI_API_KEY, OPENAI_TIMEOUT, OPENAI_MAX_RETRIES,
    LLM_MAX_TOKENS, LLM_MODELS, LLM_REASONING_EFFORT,
)


def require_api_key() -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("Set OPENAI_API_KEY in the project .env or server environment.")
    return OPENAI_API_KEY


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    return OpenAI(api_key=require_api_key(), timeout=OPENAI_TIMEOUT, max_retries=OPENAI_MAX_RETRIES)


@lru_cache(maxsize=1)
def get_async_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=require_api_key(), timeout=OPENAI_TIMEOUT, max_retries=OPENAI_MAX_RETRIES)


def response_options(task: str) -> dict:
    if task not in LLM_MODELS:
        raise ValueError(f"Unknown LLM task: {task}")
    return {
        "model": LLM_MODELS[task],
        "max_output_tokens": int(LLM_MAX_TOKENS[task]),
        "reasoning": {"effort": LLM_REASONING_EFFORT[task]},
        "store": False,
    }


def response_text(response) -> str:
    if response.status != "completed":
        raise RuntimeError(f"OpenAI response {response.status}: {response.incomplete_details or response.error}")
    if not response.output_text:
        raise RuntimeError("OpenAI returned no text (the response may have been refused).")
    return response.output_text


class OpenAIResponsesChatModel(BaseChatModel):
    task: str = "full"

    @property
    def _llm_type(self) -> str:
        return "openai_responses"

    @property
    def _identifying_params(self) -> dict:
        return {"task": self.task, **response_options(self.task)}

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        if stop:
            raise ValueError("Responses API does not support stop sequences.")
        roles = {"system": "system", "human": "user", "ai": "assistant"}
        inputs = []
        for message in messages:
            if message.type not in roles or not isinstance(message.content, str):
                raise ValueError("This RAG client accepts text system, human and AI messages only.")
            inputs.append({"role": roles[message.type], "content": message.content})
        response = get_openai_client().responses.create(input=inputs, **response_options(self.task))
        text = response_text(response)
        usage = response.usage
        message = AIMessage(content=text, response_metadata={"model": response.model, "response_id": response.id},
                            usage_metadata={"input_tokens": usage.input_tokens,
                                            "output_tokens": usage.output_tokens,
                                            "total_tokens": usage.total_tokens} if usage else None)
        return ChatResult(generations=[ChatGeneration(message=message)])


@lru_cache(maxsize=4)
def get_llm(key: str) -> OpenAIResponsesChatModel:
    response_options(key)  # Reject unknown task names instead of silently routing.
    return OpenAIResponsesChatModel(task=key)
