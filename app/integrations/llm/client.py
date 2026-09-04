"""创建并调用聊天大模型客户端。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import settings

ChatMessageInput = BaseMessage | dict[str, str]


class ChatModelNotConfiguredError(RuntimeError):
    """未配置可用聊天模型。"""


def _get_chat_model(*, temperature: float, max_tokens: int) -> ChatOpenAI:
    if settings.QWEN_API_KEY:
        return ChatOpenAI(
            model=settings.QWEN_MODEL,
            api_key=settings.QWEN_API_KEY,
            base_url=settings.QWEN_BASE_URL.rstrip("/"),
            temperature=temperature,
            max_completion_tokens=max_tokens,
            extra_body={"enable_thinking": False},
        )
    if settings.DEEPSEEK_API_KEY:
        return ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL.rstrip("/"),
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
    raise ChatModelNotConfiguredError("未配置 QWEN_API_KEY 或 DEEPSEEK_API_KEY")


def _to_base_message(message: ChatMessageInput) -> BaseMessage:
    if isinstance(message, BaseMessage):
        return message

    role = message.get("role", "user")
    content = message.get("content", "")
    if role == "system":
        return SystemMessage(content=content)
    if role == "assistant":
        return AIMessage(content=content)
    return HumanMessage(content=content)


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content)


async def chat_completion(
    messages: list[ChatMessageInput],
    *,
    temperature: float = 0,
    max_tokens: int = 512,
    response_format: dict[str, str] | None = None,
) -> str:
    """调用 OpenAI-compatible 聊天模型。

    使用 LangChain Message 类型封装，优先 Qwen，其次 DeepSeek。
    """

    model = _get_chat_model(temperature=temperature, max_tokens=max_tokens)
    kwargs: dict[str, object] = {}
    if response_format:
        kwargs["response_format"] = response_format
    result = await model.ainvoke([_to_base_message(item) for item in messages], **kwargs)
    return _normalize_content(result.content)


async def stream_chat_completion(
    messages: list[ChatMessageInput],
    *,
    temperature: float = 0,
    max_tokens: int = 512,
) -> AsyncIterator[str]:
    """流式调用聊天模型，逐段产出文本 token/chunk。

    这个函数只负责模型层流式；上层可以把 chunk 转成 SSE、WebSocket 或
    LangGraph custom stream event。
    """

    model = _get_chat_model(temperature=temperature, max_tokens=max_tokens)
    async for chunk in model.astream([_to_base_message(item) for item in messages]):
        content = _normalize_content(chunk.content)
        if content:
            yield content


async def structured_chat_completion[StructuredOutputT: BaseModel](
    schema: type[StructuredOutputT],
    messages: list[ChatMessageInput],
    *,
    temperature: float = 0,
    max_tokens: int = 512,
) -> StructuredOutputT:
    """调用模型并按 Pydantic schema 返回结构化结果。"""

    model = _get_chat_model(temperature=temperature, max_tokens=max_tokens)
    structured_model = model.with_structured_output(schema)
    base_messages = [
        SystemMessage(content="Return valid JSON that matches the requested schema."),
        *[_to_base_message(item) for item in messages],
    ]
    result = await structured_model.ainvoke(base_messages)
    if isinstance(result, schema):
        return result
    return schema.model_validate(result)
