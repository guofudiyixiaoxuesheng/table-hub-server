"""创建并调用聊天大模型客户端。"""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import settings

ChatMessageInput = BaseMessage | dict[str, Any]


class ChatModelNotConfiguredError(RuntimeError):
    """未配置可用聊天模型。"""


def _normalized_provider() -> str:
    return settings.LLM_PROVIDER.strip().lower()


def _get_chat_model(
    *, temperature: float, max_tokens: int, model_name: str | None = None
) -> ChatOpenAI:
    provider = _normalized_provider()
    if provider == "qwen":
        if not settings.QWEN_API_KEY:
            raise ChatModelNotConfiguredError(
                "LLM_PROVIDER=qwen 时需要配置 QWEN_API_KEY"
            )
        return ChatOpenAI(
            model=model_name or settings.QWEN_MODEL,
            api_key=settings.QWEN_API_KEY,
            base_url=settings.QWEN_BASE_URL.rstrip("/"),
            temperature=temperature,
            max_completion_tokens=max_tokens,
            extra_body={"enable_thinking": False},
        )
    if provider == "deepseek":
        if not settings.DEEPSEEK_API_KEY:
            raise ChatModelNotConfiguredError(
                "LLM_PROVIDER=deepseek 时需要配置 DEEPSEEK_API_KEY"
            )
        return ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL.rstrip("/"),
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
    raise ChatModelNotConfiguredError(
        "LLM_PROVIDER 仅支持 qwen / deepseek，请检查 .env 配置"
    )


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


def _validate_structured_result[StructuredOutputT: BaseModel](
    schema: type[StructuredOutputT],
    result: Any,
) -> StructuredOutputT:
    """兼容兼容模式模型偶发返回的 ``[{...}]`` 单对象数组。"""

    if isinstance(result, schema):
        return result
    if isinstance(result, BaseMessage):
        result = result.content
    if isinstance(result, str):
        content = result.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
    if isinstance(result, list) and len(result) == 1:
        result = result[0]
    return schema.model_validate(result)


async def _invoke_structured_model[StructuredOutputT: BaseModel](
    model: ChatOpenAI,
    schema: type[StructuredOutputT],
    messages: list[BaseMessage],
) -> StructuredOutputT:
    """直接取得模型 JSON，避免兼容接口的 Pydantic 解析器在拿到原文前提前失败。"""

    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    result = await model.ainvoke(
        [
            *messages,
            SystemMessage(
                content=(
                    "Return exactly one JSON object. Do not wrap it in an array or Markdown. "
                    f"It must conform to this JSON Schema: {schema_json}"
                )
            ),
        ],
        response_format={"type": "json_object"},
    )
    return _validate_structured_result(schema, result)


async def chat_completion(
    messages: list[ChatMessageInput],
    *,
    temperature: float = 0,
    max_tokens: int = 512,
    response_format: dict[str, str] | None = None,
) -> str:
    """调用 OpenAI-compatible 聊天模型。

    使用 LangChain Message 类型封装；具体供应商由 LLM_PROVIDER 控制。
    """

    model = _get_chat_model(temperature=temperature, max_tokens=max_tokens)
    kwargs: dict[str, object] = {}
    if response_format:
        kwargs["response_format"] = response_format
    result = await model.ainvoke(
        [_to_base_message(item) for item in messages], **kwargs
    )
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
    base_messages = [
        SystemMessage(content="Return valid JSON that matches the requested schema."),
        *[_to_base_message(item) for item in messages],
    ]
    return await _invoke_structured_model(model, schema, base_messages)


async def structured_vision_completion[StructuredOutputT: BaseModel](
    schema: type[StructuredOutputT],
    messages: list[ChatMessageInput],
    *,
    temperature: float = 0,
    max_tokens: int = 800,
) -> StructuredOutputT:
    """使用支持图文输入的千问模型，返回结构化图片分析结果。"""

    if _normalized_provider() != "qwen":
        raise ChatModelNotConfiguredError("图片理解当前仅支持 LLM_PROVIDER=qwen")
    model = _get_chat_model(
        temperature=temperature,
        max_tokens=max_tokens,
        model_name=settings.QWEN_VISION_MODEL,
    )
    return await _invoke_structured_model(
        model,
        schema,
        [
            SystemMessage(
                content="Return valid JSON that matches the requested schema."
            ),
            *[_to_base_message(item) for item in messages],
        ],
    )
