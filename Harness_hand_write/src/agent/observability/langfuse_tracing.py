"""Langfuse 观测：为 LangGraph / DeepAgents 挂载 CallbackHandler。

环境变量（与官方 SDK 一致）：
- LANGFUSE_ENABLED：true/1/yes 时启用（默认 false）
- LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
- LANGFUSE_BASE_URL 或 LANGFUSE_HOST（例如 https://us.cloud.langfuse.com）
"""

from __future__ import annotations

import os
from typing import Any, Optional

from langchain_core.runnables import Runnable, RunnableConfig

from agent.utils.agent_logger import get_logger

logger = get_logger("langfuse")

_ENV_PREPARED = False


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_langfuse_enabled() -> bool:
    return _truthy(os.getenv("LANGFUSE_ENABLED"))


def prepare_langfuse_env() -> None:
    """将项目惯用的 LANGFUSE_BASE_URL 映射为 SDK 常用的 LANGFUSE_HOST。"""
    global _ENV_PREPARED
    if _ENV_PREPARED:
        return
    base = (os.getenv("LANGFUSE_BASE_URL") or "").strip().strip('"').strip("'")
    host = (os.getenv("LANGFUSE_HOST") or "").strip().strip('"').strip("'")
    if base and not host:
        os.environ["LANGFUSE_HOST"] = base
    if host and not os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_BASE_URL"] = host
    _ENV_PREPARED = True


def _has_credentials() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def create_langfuse_handler():
    """每次 run 新建 Handler，避免并发请求 trace 串在一起。"""
    if not is_langfuse_enabled():
        return None
    if not _has_credentials():
        logger.warning(
            "LANGFUSE_ENABLED=true 但缺少 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY，跳过追踪"
        )
        return None

    prepare_langfuse_env()
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        logger.exception("创建 Langfuse CallbackHandler 失败，跳过追踪")
        return None


def _session_id_from_config(config: RunnableConfig) -> str:
    configurable = config.get("configurable") or {}
    for key in ("thread_id", "session_id"):
        value = configurable.get(key) or config.get(key)
        if value:
            return str(value)
    return ""


def _user_id_from_config(config: RunnableConfig) -> str:
    configurable = config.get("configurable") or {}
    for key in ("user_id", "langfuse_user_id"):
        value = configurable.get(key)
        if value:
            return str(value)
    return ""


def build_langfuse_run_config(config: RunnableConfig) -> dict[str, Any]:
    """构造可 merge 进 graph.with_config 的 callbacks + metadata。"""
    handler = create_langfuse_handler()
    if handler is None:
        return {}

    metadata: dict[str, Any] = {
        "langfuse_tags": ["wecom-agent", "langgraph", "deepagents"],
    }
    user_id = _user_id_from_config(config)
    session_id = _session_id_from_config(config)
    if user_id:
        metadata["langfuse_user_id"] = user_id
    if session_id:
        metadata["langfuse_session_id"] = session_id

    return {
        "callbacks": [handler],
        "metadata": metadata,
    }


def attach_langfuse_tracing(graph: Runnable, config: RunnableConfig) -> Runnable:
    """把 Langfuse callback 挂到编译后的 graph 上（供 langgraph server 自动生效）。"""
    run_config = build_langfuse_run_config(config)
    if not run_config:
        return graph
    try:
        return graph.with_config(run_config)
    except Exception:
        logger.exception("graph.with_config(Langfuse) 失败，返回原 graph")
        return graph
