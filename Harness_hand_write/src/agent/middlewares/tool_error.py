"""
工具错误处理中间件。

wrap_tool_call 捕获所有工具调用异常，转换为 ToolMessage（status="error"），
避免单个工具失败导致整个 Agent 运行崩溃。
"""
# 推迟解析类型注解，允许使用较新的联合类型语法。
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agent.utils.agent_logger import get_logger

logger = get_logger("tool_error")


# 从不同版本或实现的请求对象中安全提取工具调用 ID。
def _tool_call_id(request: ToolCallRequest) -> str | None:
    # 若请求未提供 tool_call 属性，返回 None 而不是抛出 AttributeError。
    tc = getattr(request, "tool_call", None)
    # 字典形式的调用信息通过键读取 ID。
    if isinstance(tc, dict):
        # 返回字典中的 ID；键不存在时结果为 None。
        return tc.get("id")
    # 对象形式的调用信息通过属性读取 ID；属性不存在时结果为 None。
    return getattr(tc, "id", None)


# 从不同版本或实现的请求对象中安全提取工具名称。
def _tool_name(request: ToolCallRequest) -> str | None:
    # 若请求未提供 tool_call 属性，返回 None 而不是抛出 AttributeError。
    tc = getattr(request, "tool_call", None)
    # 字典形式的调用信息通过键读取名称。
    if isinstance(tc, dict):
        # 返回字典中的名称；键不存在时结果为 None。
        return tc.get("name")
    # 对象形式的调用信息通过属性读取名称；属性不存在时结果为 None。
    return getattr(tc, "name", None)


# 将异常和请求信息整理为可序列化的错误载荷。
def _build_error_payload(e: Exception, request: ToolCallRequest) -> dict[str, str]:
    # 创建错误载荷，限制错误文本长度以避免消息过大。
    data: dict[str, str] = {
        # 保存异常文本的前 500 个字符。
        "error": str(e)[:500],
        # 保存异常类名，方便调用方按错误类型处理。
        "error_type": type(e).__name__,
        # 显式标注本次工具调用失败。
        "status": "error",
    }
    # 尝试取得工具名称，以便将错误关联到具体工具。
    name = _tool_name(request)
    # 仅在工具名称有效时才将其加入载荷。
    if name:
        # 写入工具名称字段。
        data["name"] = name
    # 返回构建完成的字典。
    return data


class ToolErrorMiddleware(AgentMiddleware):
    """捕获工具调用异常 → ToolMessage，Agent 可自我纠正而不崩溃。"""

    # 声明本中间件遵循 LangChain 的标准 Agent 状态结构。
    state_schema = AgentState

    # 包装同步工具调用，将任何异常转换为可供 Agent 消费的错误消息。
    def wrap_tool_call(
        # self 表示当前中间件实例。
        self,
        # request 描述当前待执行的工具调用。
        request: ToolCallRequest,
        # handler 是框架提供的实际同步工具执行函数。
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    # 返回正常工具结果、图命令，或封装后的错误消息。
    ) -> ToolMessage | Command:
        # 捕获实际处理器可能抛出的任何异常。
        try:
            # 正常情况下直接执行并原样返回处理器结果。
            return handler(request)
        # 工具运行失败时进入降级逻辑。
        except Exception as e:
            # 记录工具名称、异常类型和截断后的错误内容。
            logger.warning(
                # 日志模板中的占位符由后续参数填充。
                "工具调用异常: tool=%s, error=%s: %s",
                # 填入工具名称。
                _tool_name(request),
                # 填入异常类名。
                type(e).__name__,
                # 填入最多 200 个字符的异常文本。
                str(e)[:200],
            )
            # 返回错误状态的工具消息，而不是让异常终止整个 Agent。
            return ToolMessage(
                # 将错误载荷编码为 JSON，同时保留中文字符。
                content=json.dumps(_build_error_payload(e, request), ensure_ascii=False),
                # 关联原始调用 ID，确保框架能匹配本次调用和结果。
                tool_call_id=_tool_call_id(request),
                # 标记该工具消息表示失败。
                status="error",
            )

    # 包装异步工具调用，行为与同步版本一致。
    async def awrap_tool_call(
        # self 表示当前中间件实例。
        self,
        # request 描述当前待执行的工具调用。
        request: ToolCallRequest,
        # handler 是框架提供的实际异步工具执行函数。
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    # 最终等待异步处理器并返回正常或错误结果。
    ) -> ToolMessage | Command:
        # 捕获等待处理器期间抛出的任何异常。
        try:
            # 等待实际异步处理器完成，并原样返回结果。
            return await handler(request)
        # 工具运行失败时进入降级逻辑。
        except Exception as e:
            # 记录工具名称、异常类型和截断后的错误内容。
            logger.warning(
                # 日志模板中的占位符由后续参数填充。
                "工具调用异常: tool=%s, error=%s: %s",
                # 填入工具名称。
                _tool_name(request),
                # 填入异常类名。
                type(e).__name__,
                # 填入最多 200 个字符的异常文本。
                str(e)[:200],
            )
            # 返回错误状态的工具消息，而不是让异常终止整个 Agent。
            return ToolMessage(
                # 将错误载荷编码为 JSON，同时保留中文字符。
                content=json.dumps(_build_error_payload(e, request), ensure_ascii=False),
                # 关联原始调用 ID，确保框架能匹配本次调用和结果。
                tool_call_id=_tool_call_id(request),
                # 标记该工具消息表示失败。
                status="error",
            )
