"""主模型调用失败时切换到备用 LLM。

deepagents / create_agent 要求传入 BaseChatModel，不能直接使用
Runnable.with_fallbacks()。本中间件在 wrap_model_call 层捕获异常，
用 request.override(model=fallback) 重试，主/子 Agent 均可挂载。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel

from agent.config import resolve_fallback_model
from agent.utils.agent_logger import get_logger

logger = get_logger("llm_fallback")

# 不应触发备用模型的异常（取消 / 中断类）
_NON_FALLBACK_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
)


def _should_fallback(exc: BaseException) -> bool:
    if isinstance(exc, _NON_FALLBACK_EXCEPTIONS):
        return False
    # asyncio.CancelledError 在 3.9+ 是 BaseException
    try:
        import asyncio

        if isinstance(exc, asyncio.CancelledError):
            return False
    except ImportError:
        pass
    # LangGraph HITL / 图中断不应被当成模型故障
    exc_type = type(exc)
    if exc_type.__name__ in {"GraphInterrupt", "GraphBubbleUp", "Interrupt"}:
        return False
    return isinstance(exc, Exception)


class LlmFallbackMiddleware(AgentMiddleware):
    """主 LLM 失败时改用备用 LLM 再调一次。"""

    def __init__(self, fallback_model: BaseChatModel | None = None) -> None:
        super().__init__()
        self._fallback_model = fallback_model

    def _fallback_for(self, request: ModelRequest) -> BaseChatModel:
        if self._fallback_model is not None:
            return self._fallback_model
        return resolve_fallback_model(request.model)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        try:
            return handler(request)
        except BaseException as exc:
            if not _should_fallback(exc):
                raise
            fallback = self._fallback_for(request)
            primary_id = getattr(request.model, "model_name", None) or getattr(
                request.model, "model", type(request.model).__name__
            )
            fallback_id = getattr(fallback, "model_name", None) or getattr(
                fallback, "model", type(fallback).__name__
            )
            logger.warning(
                "主模型调用失败，切换备用模型 primary=%s fallback=%s error=%s: %s",
                primary_id,
                fallback_id,
                type(exc).__name__,
                exc,
            )
            return handler(request.override(model=fallback))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        try:
            return await handler(request)
        except BaseException as exc:
            if not _should_fallback(exc):
                raise
            fallback = self._fallback_for(request)
            primary_id = getattr(request.model, "model_name", None) or getattr(
                request.model, "model", type(request.model).__name__
            )
            fallback_id = getattr(fallback, "model_name", None) or getattr(
                fallback, "model", type(fallback).__name__
            )
            logger.warning(
                "主模型调用失败，切换备用模型 primary=%s fallback=%s error=%s: %s",
                primary_id,
                fallback_id,
                type(exc).__name__,
                exc,
            )
            return await handler(request.override(model=fallback))
