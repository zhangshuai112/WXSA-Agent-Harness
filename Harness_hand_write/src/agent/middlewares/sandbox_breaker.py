"""
沙箱熔断中间件。

before_model 检查最近消息中的沙箱相关错误，连续失败 ≥ 阈值时
跳转到 end 并注入通知消息，防止无限恢复循环。

与 SandboxHealthMiddleware 配合：
- SandboxHealthMiddleware：主动 ping → 自动恢复
- SandboxCircuitBreakerMiddleware：恢复失败次数超限 → 熔断
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.runtime import Runtime

from agent.utils.agent_logger import get_logger

logger = get_logger("sandbox_breaker")

# 连续沙箱错误次数严格大于该值时，才会停止本轮 Agent 执行。
THRESHOLD = 3

# 写入 AI 消息的标记，用来识别“本轮已经熔断”的历史记录。
CIRCUIT_BREAKER_MARKER = "SandboxCircuitBreaker"

# 用于从工具错误文本中识别“这是否属于沙箱故障”的关键词集合。
_SANDBOX_ERROR_KEYWORDS = [
    "SandboxBackendProxy",
    "sandbox",
    "SandboxError",
    "ConnectionError",
    "ConnectionRefusedError",
    "TimeoutError",
    "execute",
    "沙箱",
    "不可达",
    "连接",
    "超时",
]


def _looks_like_sandbox_error(text: str) -> bool:
    # 统一转为小写，使英文关键词匹配不受原始大小写影响。
    text_lower = text.lower()
    # 只要任一关键词出现在错误文本中，就按沙箱故障处理。
    return any(kw.lower() in text_lower for kw in _SANDBOX_ERROR_KEYWORDS)


def _count_consecutive_sandbox_errors(
    messages: Sequence[BaseMessage],
) -> int:
    """从消息列表末尾向前统计连续沙箱错误的 ToolMessage 数量。"""
    # 只关心消息尾部连续发生的失败，因此从最新消息开始反向扫描。
    count = 0
    for msg in reversed(messages):
        ##reversed反向遍历
        # 工具调用消息携带了实际执行沙箱命令时的结果或错误。
        if isinstance(msg, ToolMessage):
            # content 可能是字符串，也可能是 LangChain 的内容块列表。
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                # 将内容块合并成一个字符串，供关键词检测使用。
                content = " ".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in content
                )
            # 仅当工具状态为 error 且文本符合沙箱错误特征时才计数。
            status = getattr(msg, "status", None)
            if status == "error" and _looks_like_sandbox_error(str(content)):
                count += 1
                # 继续查看前一条消息，确认错误是否连续发生。
                continue
            # 非沙箱错误、成功工具调用都会中断“连续错误”链。
            break
        elif isinstance(msg, AIMessage):
            # 熔断器自己写入的消息表示已经处理过该轮失败。
            content = getattr(msg, "content", "")
            text = content if isinstance(content, str) else str(content)
            if CIRCUIT_BREAKER_MARKER in text:
                # 避免下一轮再次因为同一条熔断通知而重复触发。
                return 0
        elif getattr(msg, "type", "") in {"human", "system"}:
            # 用户或系统消息标志着新的对话输入，不再跨轮累计错误。
            break
    # 返回末尾连续且可识别的沙箱错误数量。
    return count


class SandboxCircuitBreakerMiddleware(AgentMiddleware):
    """连续沙箱错误超过阈值 → 熔断，跳转到 end。"""

    state_schema = AgentState

    def __init__(self, threshold: int = THRESHOLD) -> None:
        # 先执行父类初始化，以保留 LangChain 中间件的基础行为。
        super().__init__()
        # 允许调用方针对不同场景调整熔断阈值。
        self.threshold = threshold

    @hook_config(can_jump_to=["end"])
    def before_model(
        self, state: AgentState, runtime: Runtime,
    ) -> dict[str, Any] | None:
        # 从 Agent 状态取得完整对话和工具调用历史。
        messages = state.get("messages", [])
        if not messages:
            # 没有任何历史时不需要执行熔断判断。
            return None

        # 计算消息尾部连续出现的沙箱工具错误数。
        count = _count_consecutive_sandbox_errors(messages)
        if count <= self.threshold:
            # 尚未超过阈值，让模型继续执行并由健康检查中间件尝试恢复。
            return None

        # 超过阈值后记录运维日志，便于定位反复失败的会话。
        logger.warning(
            "沙箱熔断: 连续 %d 次沙箱错误超过阈值 %d", count, self.threshold,
        )
        # 给用户可见的 AI 消息增加标记，同时说明本轮被终止的原因。
        content = (
            f"{CIRCUIT_BREAKER_MARKER}: 连续 {count} 次沙箱操作失败，已触发熔断保护。"
            "请检查沙箱服务状态后重试，或联系管理员。"
        )
        # LangGraph 读取 jump_to 后跳转到 end，停止继续请求模型或调用工具。
        return {"jump_to": "end", "messages": [AIMessage(content=content)]}

    @hook_config(can_jump_to=["end"])
    async def abefore_model(
        self, state: AgentState, runtime: Runtime,
    ) -> dict[str, Any] | None:
        # 此检查不含 I/O；异步钩子复用同步实现，保证两种运行方式一致。
        return self.before_model(state, runtime)
