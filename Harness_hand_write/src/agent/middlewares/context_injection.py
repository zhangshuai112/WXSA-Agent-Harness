"""
运行时上下文注入中间件。

从 runtime.context（ProcurementContext）中提取 user_id / external_id /
follow_user_id / open_kfid，在每次模型调用前拼进 system_message。
不写入 state.messages，避免被对话摘要中间件压缩丢失。

约定：external_id 即客服发送接口的客户 ID（touser），不必再单独传 customer_id。

使用方式:
    from agent.middlewares.context_injection import ContextInjectionMiddleware
    middleware = ContextInjectionMiddleware()
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Optional

from deepagents.middleware._utils import append_to_system_message
from dotenv import load_dotenv
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse

from agent.utils.agent_logger import get_logger

logger = get_logger("context_injection")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def _context_value(context: Any, name: str) -> Optional[str]:
    """Read a non-empty value from an object or dictionary context."""
    if context is None:
        return None
    if isinstance(context, dict):
        value = context.get(name)
    else:
        value = getattr(context, name, None)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _env_value(*names: str) -> Optional[str]:
    """Return the first non-empty environment value."""
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _build_identity_notice(runtime: Any) -> Optional[str]:
    """Build identity text from runtime.context (or env fallbacks)."""
    ctx = getattr(runtime, "context", None)
    user_id = _context_value(ctx, "user_id") or _env_value("DEMO_USER_ID")
    username = _context_value(ctx, "username") or user_id
    external_id = _context_value(ctx, "external_id") or _env_value(
        "EXTERNAL_ID",
        "DEMO_USER_EXTERNAL_ID",
        "WXTERNAL_ID",
    )
    follow_user_id = _context_value(ctx, "follow_user_id") or _env_value(
        "FOLLOW_USER_ID"
    )
    open_kfid = _context_value(ctx, "open_kfid") or _env_value(
        "OPEN_KFID",
        "DEFAULT_OPEN_KFID",
    )

    if not any((user_id, external_id, follow_user_id, open_kfid)):
        logger.warning("ContextInjectionMiddleware: 没有可注入的用户或客户上下文")
        return None

    logger.debug(
        "ContextInjectionMiddleware: 注入 system 上下文 user_id=%s, "
        "external_id=%s, follow_user_id=%s, open_kfid=%s",
        user_id or "<missing>",
        external_id or "<missing>",
        follow_user_id or "<missing>",
        open_kfid or "<missing>",
    )

    context_lines = ["【系统上下文】"]
    if user_id:
        context_lines.extend(
            [
                f"当前用户 user_id: {user_id}",
                f"当前用户 username: {username}",
            ]
        )
    if external_id:
        context_lines.extend(
            [
                f"当前客户 external_id: {external_id}",
                "说明：external_id 即企业微信客服发送接口的客户 ID（touser），"
                "调用 send_wecom_kf_message 时直接使用，不要另找 customer_id。",
            ]
        )
    if follow_user_id:
        context_lines.append(
            f"当前跟进客户的销售员工 follow_user_id: {follow_user_id}"
        )
    if open_kfid:
        context_lines.append(f"当前企业微信客服账号 open_kfid: {open_kfid}")

    context_lines.extend(
        [
            "",
            "调用客户数据工具或子智能体时，必须使用上述 external_id 和 "
            "follow_user_id，不得自行猜测或替换。",
            "客服发送任务必须使用上述 open_kfid；缺少 open_kfid 时不得猜测。",
        ]
    )
    return "\n".join(context_lines)


class ContextInjectionMiddleware(AgentMiddleware):
    """将用户和客户身份信息注入每次模型调用的 system_message。"""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        notice = _build_identity_notice(request.runtime)
        if not notice:
            return handler(request)
        new_system = append_to_system_message(request.system_message, notice)
        return handler(request.override(system_message=new_system))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        notice = _build_identity_notice(request.runtime)
        if not notice:
            return await handler(request)
        new_system = append_to_system_message(request.system_message, notice)
        return await handler(request.override(system_message=new_system))
