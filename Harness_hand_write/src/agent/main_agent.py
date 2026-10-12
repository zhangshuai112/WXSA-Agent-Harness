"""
主 Agent 入口模块。

使用 DeepAgents `create_deep_agent` 将所有组件串联为一个可运行的
销售智能助手。采用 Graph Factory 模式：启动时预计算可复用组件，
每次请求基于 per-user 沙箱轻量创建 agent graph，实现用户级沙箱隔离。

使用方式:
    from agent.main_agent import precompute_agent_context, create_main_agent

    # 启动时
    precomputed = await precompute_agent_context()

    # 每次请求
    agent_graph = await create_main_agent(
        config,
        sandbox_backend=user_sandbox,
        precomputed=precomputed,
    )
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

from deepagents import AsyncSubAgent, create_deep_agent
from deepagents.backends import CompositeBackend, StoreBackend, StateBackend, FilesystemBackend
from deepagents.backends.protocol import SandboxBackendProtocol
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    TodoListMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.runnables import RunnableConfig

from agent.config import (
    AGENTS_MD_FILENAME,
    DOWNLOAD_DIR,
    LOCAL_AGENTS_MD,
    MAIN_MODEL,
    STORE,
    SUMMARY_MODEL,
    ENABLE_WRITE_TODOS,
)
from agent.memory.prompt import get_system_prompt
# from agent.middleware_config import create_order_middleware
from agent.middlewares.audit import AuditMiddleware
from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.llm_fallback import LlmFallbackMiddleware
from agent.middlewares.sandbox_breaker import SandboxCircuitBreakerMiddleware
from agent.middlewares.sandbox_health import SandboxHealthMiddleware
from agent.middlewares.skills_sync import SkillsSyncMiddleware
from agent.middlewares.tool_error import ToolErrorMiddleware
from agent.middlewares.tools_summarization import build_summarization_middleware
from agent.subagents.loader import load_subagent_configs, resolve_subagent_tools

from agent.tools.paddleocr_multimodal_tool import paddleocr_tool
from agent.tools.store_tool import store_tools
from agent.tools.wx_tools import wx_tools
from agent.tools.assign_skill import create_assign_skill_tool
from agent.tools.download_sandbox_file import create_download_tool
from agent.tools.web_search import web_search
from agent.utils.agent_logger import get_logger
from paddlex.inference.serving.infra.storage import FileSystemStorage

logger = get_logger("main_agent")


@dataclass
class ProcurementContext:
    """
    运行时上下文，由调用方在 invoke 时传入。
    用于传递当前用户身份等基础信息。

    约定：external_id 即企业微信客服接口的 touser（旧称 customer_id），二者同一值。
    """
    user_id: str = ""
    username: str = ""
    external_id: str = ""
    follow_user_id: str = ""
    open_kfid: str = ""

# ============================================================
# PrecomputedContext — 启动时预计算的可复用组件
# ============================================================

@dataclass
class PrecomputedContext:
    """Phase 2/3/5 预计算结果的不可变容器。

    仅包含不依赖 sandbox_backend 的组件（工具、YAML 配置）。
    sandbox 依赖的工具（assign_skill、download_sandbox_file）和 backend 依赖的
    中间件在 create_main_agent() 中按请求动态创建。
    """
    all_tools: list = field(default_factory=list)
    paddleocr_tool: list = field(default_factory=list)
    store_tools: list = field(default_factory=list)
    wx_tools: list = field(default_factory=list)

    raw_subagent_configs: list = field(default_factory=list)


async def precompute_agent_context() -> PrecomputedContext:
    """Phase 2/3/5 预计算，启动时执行一次，所有请求复用。"""
    logger.info("=== 预计算 Agent 上下文===")

    # # Phase 2: MCP 工具加载
    # logger.info("Phase 2: 加载 MCP 工具...")
    # try:
    #     all_mcp_tools, analyst_mcp_tools, order_mcp_tools, chart_mcp_tools = (
    #         await load_mcp_tools()
    #     )
    # except Exception:
    #     logger.exception("MCP 工具加载失败")
    #     raise RuntimeError("MCP 工具加载失败，无法预计算")
    #

    # Phase : 子 Agent YAML 配置加载
    logger.info("Phase 5: 加载子 Agent YAML 配置...")
    raw_configs = await asyncio.to_thread(load_subagent_configs)
    if not raw_configs:
        logger.warning("  未找到任何子 Agent 配置")
    else:
        logger.info(f"  已加载 {len(raw_configs)} 个子 Agent 配置")

    logger.info("=== 预计算完成 ===")
    return PrecomputedContext(
        all_tools=[paddleocr_tool]+store_tools+wx_tools,
        paddleocr_tool=paddleocr_tool,
        store_tools=store_tools,
        wx_tools=wx_tools,
        raw_subagent_configs=raw_configs
    )


# ============================================================
# create_main_agent — 每次请求基于 per-user 沙箱创建 agent graph
# ============================================================

async def create_main_agent(
    config: RunnableConfig,
    *,
    sandbox_backend: SandboxBackendProtocol,
    precomputed: PrecomputedContext,
):
    """创建 智能助手的 per-request graph factory。

    每次请求调用，使用预计算的 MCP 工具/YAML 配置 + 外部传入的 per-user 沙箱，
    轻量创建 agent graph。SandboxBackendProxy 保证沙箱热替换不丢引用。

    Args:
        config: LangGraph RunnableConfig，含 thread_id + user_id。
        sandbox_backend: per-user 沙箱后端（SandboxBackendProxy）。
        precomputed: 启动时预计算的 MCP 工具/YAML 配置。
    """
    user_id = config["configurable"]["user_id"]
    logger.info(f"=== 为用户 {user_id} 创建 Agent Graph ===")

    # ---- Phase 1: CompositeBackend ----
    # deepagents 0.7+ 要求传入已初始化的 backend 实例（不再支持 factory）。
    backend = CompositeBackend(
        default=sandbox_backend,
        routes={
            "/memories/": StoreBackend(
                store=STORE,
                namespace=lambda rt: (
                    "agent_memories",
                    rt.context.user_id,
                ),
            ),
            "/user_prefernrce/" : FilesystemBackend(root_dir="/root/user_preference",virtual_mode=True),
        },
    )

    # ---- Phase 1.4: 上传 AGENTS.md 到沙箱 ----
    logger.info("Phase 1.4: 上传 AGENTS.md 到沙箱...")
    ag_md_content = await asyncio.to_thread(
        LOCAL_AGENTS_MD.read_text, encoding="utf-8"
    )
    await sandbox_backend.aupload_files(
        [("/AGENTS.md", ag_md_content.encode("utf-8"))]
    )

    # # ---- Phase 2/3/5: 使用预计算结果 ----
    # logger.info("Phase 2-5: 使用预计算的 MCP 工具 + 图表工具 + YAML 配置...")
    # generate_visualization = precomputed.generate_visualization
    # extra_mcp_tools = precomputed.extra_mcp_tools

    # ---- Phase 3.6: 创建 sandbox 依赖工具（per-request）----
    logger.info("Phase 3.6: 创建 sandbox 依赖工具...")
    assign_skill = create_assign_skill_tool(
        sandbox_backend,
    )
    download_sandbox_file = create_download_tool(sandbox_backend, DOWNLOAD_DIR)

    # ---- Phase 4: 构建工具池 ----
    logger.info("Phase 4: 构建工具池...")
    available_tools = (

        [paddleocr_tool]
        + store_tools
        + wx_tools
        + [web_search]
        + [assign_skill]
        + [download_sandbox_file]
    )
    logger.info(f"  工具池: {len(available_tools)} 个工具")

    # ---- Phase 5: 子 Agent 中间件 ----
    logger.info("Phase 5: 创建子 Agent 中间件...")
    # 工具异常 → ToolMessage(status=error)，避免单次工具失败拖垮整轮
    tool_error_middleware = ToolErrorMiddleware()
    # 主模型失败 → 备用 LLM（子 Agent 同样挂载）
    llm_fallback_middleware = LlmFallbackMiddleware()
    extra_middleware = {
        config["name"]: [
            # 最外层：捕获模型调用失败并切换备用 LLM
            llm_fallback_middleware,
            ContextInjectionMiddleware(),
            tool_error_middleware,
            AuditMiddleware(agent_name=config["name"]),
        ]
        for config in precomputed.raw_subagent_configs
        if config.get("name")
    }

    # ---- Phase 7: 子 Agent 工具解析 ----
    logger.info("Phase 7: 解析子 Agent 工具名称...")
    sync_subagent_configs = [
        c for c in precomputed.raw_subagent_configs
    ]
    sync_subagents = resolve_subagent_tools(
        sync_subagent_configs,
        available_tools,
        extra_middleware=extra_middleware,
    )

    subagents = sync_subagents
    logger.info(f"  已解析 {len(subagents)} 个子 Agent")

    # ---- Phase 8: 主 Agent 中间件栈 ----
    logger.info("Phase 8: 构建主 Agent 中间件栈...")
    # 列表靠前 = wrap_model_call 最外层，便于捕获内层模型调用异常并切备用
    main_middleware = [
        llm_fallback_middleware,
        # 1. 沙箱健康守护：每次 agent step 前 ping → 失败自动恢复
        SandboxHealthMiddleware(
            sandbox_backend=sandbox_backend,
            user_id=user_id,
            agents_md_content=ag_md_content.encode("utf-8"),
        ),
        # 2. 用户上下文注入
        ContextInjectionMiddleware(),
    ]
    if ENABLE_WRITE_TODOS:
        # 3. 多步协调：write_todos 跟踪子 Agent 委派进度（仅主 Agent）
        main_middleware.append(TodoListMiddleware())
        logger.info("  已启用 write_todos (TodoListMiddleware)")
    main_middleware.extend(
        [
            # 4. 技能同步（本地 → 沙箱）
            SkillsSyncMiddleware(sandbox_backend),
            # 5. 对话摘要 + compact_conversation 工具
            build_summarization_middleware(backend, SUMMARY_MODEL),
            # 6. 沙箱熔断：连续沙箱错误 ≥ 阈值 → jump_to=end
            SandboxCircuitBreakerMiddleware(),
            # 7. 工具异常捕获 → ToolMessage(error)，主 Agent 可继续纠错
            tool_error_middleware,
            # 8. 结构化审计：who/what/tool/hitl/tokens/latency
            AuditMiddleware(agent_name="main"),
            # 9. 调用限制
            ModelCallLimitMiddleware(run_limit=50),
            # 10. 工具调用限制
            ToolCallLimitMiddleware(run_limit=200),
        ]
    )

    # ---- Phase 9: create_deep_agent ----
    # system_prompt：优先 Langfuse main/system@production，失败回退 prompt.py
    # memory：仍加载沙箱内 /AGENTS.md，与 prompt 来源无关
    logger.info("Phase 9: 创建 Deep Agent...")
    resolved_system_prompt = await asyncio.to_thread(get_system_prompt)
    agent_graph = create_deep_agent(
        model=MAIN_MODEL,
        system_prompt=resolved_system_prompt,
        skills=["/skills/main/"],
        memory=[AGENTS_MD_FILENAME],
        tools=[web_search, assign_skill, download_sandbox_file,paddleocr_tool],
        subagents=subagents,
        middleware=main_middleware,
        backend=backend,
        context_schema=ProcurementContext,
    )

    logger.info(f"=== 用户 {user_id} Agent Graph 创建完成 ===")
    return agent_graph
