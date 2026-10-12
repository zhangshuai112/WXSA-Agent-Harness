"""LangGraph Server entry point."""

from __future__ import annotations

import asyncio

from langchain_core.runnables import RunnableConfig

from agent.backends.sandbox_manager import (
    ensure_sandbox_for_user,
    initialize,
    pre_warm,
)
from agent.config import SANDBOX_PRE_WARM, USERID
from agent.main_agent import (
    PrecomputedContext,
    create_main_agent,
    precompute_agent_context,
)
from agent.observability.langfuse_tracing import attach_langfuse_tracing
from agent.utils.agent_logger import configure_logging, get_logger

configure_logging()
logger = get_logger("graph")

_precomputed: PrecomputedContext | None = None
_precompute_lock = asyncio.Lock()
_sandbox_pre_warmed = False
_sandbox_pre_warm_lock = asyncio.Lock()


async def _get_precomputed_context() -> PrecomputedContext:
    """Load reusable tools and subagent configuration once per process."""
    global _precomputed
    if _precomputed is not None:
        return _precomputed

    async with _precompute_lock:
        if _precomputed is None:
            _precomputed = await precompute_agent_context()
    return _precomputed


async def _ensure_sandbox_pre_warm() -> None:
    """Pre-create one idle OpenSandbox per process for faster first-user onboarding."""
    global _sandbox_pre_warmed
    if not SANDBOX_PRE_WARM or _sandbox_pre_warmed:
        return

    async with _sandbox_pre_warm_lock:
        if not SANDBOX_PRE_WARM or _sandbox_pre_warmed:
            return
        logger.info("Starting sandbox pre-warm (SANDBOX_PRE_WARM=true)...")
        await pre_warm()
        _sandbox_pre_warmed = True


async def graph(config: RunnableConfig):
    """Build the main graph for the user identified by the run config.

    Pass ``configurable.user_id`` for each run. ``USERID`` from ``.env`` is
    used only as a local-development fallback.
    """
    configurable = config.setdefault("configurable", {})
    user_id = configurable.get("user_id") or USERID
    if not user_id:
        raise ValueError(
            "Missing user_id. Set configurable.user_id in the run config "
            "or USERID in .env."
        )
    configurable["user_id"] = str(user_id)

    await initialize()
    precomputed, _ = await asyncio.gather(
        _get_precomputed_context(),
        _ensure_sandbox_pre_warm(),
    )
    sandbox_backend = await ensure_sandbox_for_user(str(user_id))

    agent_graph = await create_main_agent(
        config,
        sandbox_backend=sandbox_backend,
        precomputed=precomputed,
    )
    # Langfuse：每次 factory 调用挂新 CallbackHandler，供 langgraph server 自动追踪
    return attach_langfuse_tracing(agent_graph, config)
