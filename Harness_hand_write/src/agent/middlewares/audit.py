"""结构化审计中间件：记录工具调用与模型调用的 who/what/tool/hitl/cost/latency。"""

# 让类型注解可以写成 str | None 等形式，且支持前向引用
from __future__ import annotations

# time：用于 perf_counter 高精度计时，算 latency_ms
import time
# Awaitable / Callable：标注「可调用对象」和「异步可等待对象」的类型
from collections.abc import Awaitable, Callable
# Any：不确定具体类型时使用
from typing import Any

# AgentMiddleware：中间件基类；AgentState：默认状态 schema
from langchain.agents.middleware import AgentMiddleware, AgentState
# 模型调用 / 工具调用的请求与响应类型
from langchain.agents.middleware.types import (
    ModelRequest,   # 调用大模型前的请求对象
    ModelResponse,  # 大模型返回后的响应对象
    ToolCallRequest,  # 调用某个工具前的请求对象
)
# ToolMessage：工具执行结果消息（可能带 status=error）
from langchain_core.messages import ToolMessage
# Command：工具也可能返回图控制命令（而不是普通 ToolMessage）
from langgraph.types import Command

# 真正把审计事件写成 JSONL 的函数
from agent.observability.audit_log import emit_audit_event

# 配置了 interrupt_on 的高风险写工具：
# 能执行到本中间件的 wrap_tool_call，通常说明 HITL 已 approve/edit 放行。
_HITL_TOOLS = frozenset(  # frozenset：不可变集合，适合当常量白名单
    {
        "update_customer_tags",       # 更新客户标签（写 Store + 可能同步企微）
        "update_customer_profile",    # 更新客户画像（写 Store）
        "send_wecom_kf_message",      # 发送企微客服消息
        "create_wecom_schedule",      # 创建企微日程
    }
)


def _tool_call_dict(request: ToolCallRequest) -> dict[str, Any]:
    """把 request.tool_call 统一转成 dict，方便取 name/args/id。"""
    # 不同版本里 tool_call 可能是 dict，也可能是带属性的对象
    tc = getattr(request, "tool_call", None)
    # 已经是字典：直接返回
    if isinstance(tc, dict):
        return tc
    # 根本没有 tool_call：返回空字典，避免后面 .get 报错
    if tc is None:
        return {}
    # 对象形式：用 getattr 拼出等价字典
    return {
        "name": getattr(tc, "name", None),  # 工具名
        "args": getattr(tc, "args", None),  # 工具参数
        "id": getattr(tc, "id", None),      # 本次 tool_call 的 id
    }


def _tool_name(request: ToolCallRequest) -> str:
    """从请求里取出工具名字符串；没有则返回空串。"""
    # or ""：name 为 None 时变成空串；再 str() 保证类型是 str
    return str(_tool_call_dict(request).get("name") or "")


def _tool_args(request: ToolCallRequest) -> Any:
    """从请求里取出工具参数（可能是 dict / 其它结构）。"""
    return _tool_call_dict(request).get("args")


def _context_value(context: Any, name: str) -> str | None:
    """从 runtime.context（dict 或对象）里安全读取非空字符串字段。"""
    # 没有 context：读不到任何身份信息
    if context is None:
        return None
    # dict 形态：用 .get
    if isinstance(context, dict):
        value = context.get(name)
    else:
        # 对象形态（如 ProcurementContext）：用属性
        value = getattr(context, name, None)
    # 字段不存在
    if value is None:
        return None
    # 转字符串并去掉首尾空白
    text = str(value).strip()
    # 空串视为无效，返回 None；非空则返回 text
    return text or None


def _from_config(config: Any, *keys: str) -> str | None:
    """从 RunnableConfig / configurable 里按候选 key 顺序取值。"""
    # config 必须是 dict 才继续
    if not isinstance(config, dict):
        return None
    # LangGraph 习惯把业务字段放在 configurable 子字典
    configurable = config.get("configurable") or {}
    # 依次尝试每个 key
    for key in keys:
        # 优先 configurable，再退回顶层 config
        value = configurable.get(key) or config.get(key)
        # 非空字符串才算有效
        if value is not None and str(value).strip():
            return str(value).strip()
    # 所有 key 都没有
    return None


def _identity_from_runtime(runtime: Any) -> tuple[str | None, str | None]:
    """从 runtime 提取 (user_id, thread_id)，供审计 who / thread_id 字段使用。"""
    # 没有 runtime：两边都未知
    if runtime is None:
        return None, None
    # 业务上下文（ProcurementContext 或 dict）
    ctx = getattr(runtime, "context", None)
    # 运行配置（含 configurable.thread_id / user_id）
    config = getattr(runtime, "config", None)
    # user_id：先 context，再 config
    user_id = _context_value(ctx, "user_id") or _from_config(config, "user_id")
    # thread_id：一般只在 config.configurable 里
    thread_id = _from_config(config, "thread_id")
    return user_id, thread_id


def _result_success(result: ToolMessage | Command | Any) -> bool:
    """根据工具返回值判断是否成功。"""
    # ToolMessage 可能带 status="error"（例如 ToolErrorMiddleware 转换后）
    if isinstance(result, ToolMessage):
        # status 不是 error 就当成功
        return getattr(result, "status", None) != "error"
    # Command 或其它类型：默认当作成功（未显式报错）
    return True


def _usage_tokens(response: ModelResponse) -> int | None:
    """从模型响应里尽量汇总 total_tokens；找不到则返回 None。"""
    total = 0      # 累加 token 数
    found = False  # 是否至少找到过一段 usage 信息
    # response.result 通常是一批消息；没有则当空列表
    for msg in getattr(response, "result", None) or []:
        # 新版常见：消息上的 usage_metadata
        usage = getattr(msg, "usage_metadata", None)
        if not usage:
            # 旧版常见：塞在 response_metadata 里
            meta = getattr(msg, "response_metadata", None) or {}
            usage = meta.get("token_usage") or meta.get("usage")
        # 这条消息没有用量信息：跳过
        if not usage:
            continue
        # 标记：确实找到过 usage
        found = True
        if isinstance(usage, dict):
            # 优先 total_tokens；否则用 input+output（兼容多种字段名）
            total += int(
                usage.get("total_tokens")
                or (
                    (usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
                    + (usage.get("output_tokens") or usage.get("completion_tokens") or 0)
                )
                or 0
            )
        else:
            # usage 是对象：读 total_tokens 属性
            total += int(getattr(usage, "total_tokens", 0) or 0)
    # 全程没找到 usage：返回 None（表示「未知」而不是 0）
    return total if found else None


class AuditMiddleware(AgentMiddleware):
    """在工具调用、模型调用外包一层，结束后写出结构化审计 JSONL。"""

    # 告诉框架本中间件使用的状态类型
    state_schema = AgentState

    def __init__(self, agent_name: str = "main") -> None:
        # 调用父类初始化
        super().__init__()
        # 记录是主 Agent 还是某个子 Agent 名字，写入审计字段 agent
        self.agent_name = agent_name
        # 主 Agent 本轮开始时间（perf_counter），用于结束时打印总耗时
        self._run_started_at: float | None = None

    def before_agent(self, state: AgentState, runtime: Any) -> None:
        if self.agent_name == "main":
            self._run_started_at = time.perf_counter()
        return None

    async def abefore_agent(self, state: AgentState, runtime: Any) -> None:
        if self.agent_name == "main":
            self._run_started_at = time.perf_counter()
        return None

    def wrap_tool_call(
        self,
        request: ToolCallRequest,  # 框架传入的工具调用请求
        handler: Callable[[ToolCallRequest], ToolMessage | Command],  # 真正执行工具的函数
    ) -> ToolMessage | Command:
        """同步包装：执行工具前后计时，并在 finally 里写审计。"""
        # 取出工具名
        tool = _tool_name(request)
        # 取出操作者与会话 id
        user_id, thread_id = _identity_from_runtime(getattr(request, "runtime", None))
        # 若是高风险写工具，标记为已过 HITL（能跑到这里通常已审核）
        hitl = "approved_or_edited" if tool in _HITL_TOOLS else None
        # 开始计时（单调时钟，不受系统改时影响）
        started = time.perf_counter()
        # 预置错误信息与成功标记，供 finally 使用
        error: str | None = None
        success: bool | None = None
        try:
            # 真正调用下游工具
            result = handler(request)
            # 根据返回值判断成败
            success = _result_success(result)
            # 把工具结果交还给框架
            return result
        except Exception as exc:
            # 记录异常文本
            error = str(exc)
            # 标记失败
            success = False
            # 继续向上抛，不吞异常
            raise
        finally:
            # 无论成功失败，都写一条审计（核心落点）
            emit_audit_event(
                action="tool_call",                 # 动作类型：工具调用
                agent=self.agent_name,              # 哪个 Agent
                user_id=user_id,                    # 谁
                thread_id=thread_id,                # 哪次会话
                tool=tool,                          # 工具名
                what=f"tool:{tool}" if tool else "tool_call",  # 可读描述
                hitl=hitl,                          # 是否 HITL 相关
                success=success,                    # 是否成功
                latency_ms=(time.perf_counter() - started) * 1000,  # 耗时毫秒
                error=error,                        # 失败原因（成功时为 None）
                args_summary=_tool_args(request),   # 参数摘要（写入前会脱敏/截断）
            )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """异步包装：逻辑与 wrap_tool_call 相同，只是 await handler。"""
        tool = _tool_name(request)
        user_id, thread_id = _identity_from_runtime(getattr(request, "runtime", None))
        hitl = "approved_or_edited" if tool in _HITL_TOOLS else None
        started = time.perf_counter()
        error: str | None = None
        success: bool | None = None
        try:
            # 异步执行工具
            result = await handler(request)
            success = _result_success(result)
            return result
        except Exception as exc:
            error = str(exc)
            success = False
            raise
        finally:
            # 同样写审计事件
            emit_audit_event(
                action="tool_call",
                agent=self.agent_name,
                user_id=user_id,
                thread_id=thread_id,
                tool=tool,
                what=f"tool:{tool}" if tool else "tool_call",
                hitl=hitl,
                success=success,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=error,
                args_summary=_tool_args(request),
            )

    def wrap_model_call(
        self,
        request: ModelRequest,  # 模型调用请求
        handler: Callable[[ModelRequest], ModelResponse],  # 真正调模型的函数
    ) -> ModelResponse:
        """同步包装模型调用：记录耗时与 token。"""
        # 身份信息
        user_id, thread_id = _identity_from_runtime(getattr(request, "runtime", None))
        # 开始计时
        started = time.perf_counter()
        # 默认先当作失败，成功后再改 True
        error: str | None = None
        success = False
        tokens: int | None = None
        try:
            # 真正调用大模型
            response = handler(request)
            # 能走到这里说明调用成功返回
            success = True
            # 尽量从响应里抠 token 用量
            tokens = _usage_tokens(response)
            return response
        except Exception as exc:
            # 记录错误，success 保持 False
            error = str(exc)
            raise
        finally:
            # 模型调用也写审计（没有 tool / hitl）
            emit_audit_event(
                action="model_call",
                agent=self.agent_name,
                user_id=user_id,
                thread_id=thread_id,
                what="model_call",
                success=success,
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens=tokens,
                error=error,
            )

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """异步包装模型调用：与 wrap_model_call 相同，使用 await。"""
        user_id, thread_id = _identity_from_runtime(getattr(request, "runtime", None))
        started = time.perf_counter()
        error: str | None = None
        success = False
        tokens: int | None = None
        try:
            response = await handler(request)
            success = True
            tokens = _usage_tokens(response)
            return response
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            emit_audit_event(
                action="model_call",
                agent=self.agent_name,
                user_id=user_id,
                thread_id=thread_id,
                what="model_call",
                success=success,
                latency_ms=(time.perf_counter() - started) * 1000,
                tokens=tokens,
                error=error,
            )

    def after_agent(self, state: AgentState, runtime: Any) -> None:
        """主 Agent 本轮图执行结束时，在终端打出明确结束提示。"""
        self._emit_run_finished(runtime)
        return None

    async def aafter_agent(self, state: AgentState, runtime: Any) -> None:
        self._emit_run_finished(runtime)
        return None

    def _emit_run_finished(self, runtime: Any) -> None:
        # 子 Agent 结束也会进 after_agent；结束提示只打主 Agent，避免误判整轮已完成。
        if self.agent_name != "main":
            return
        user_id, thread_id = _identity_from_runtime(runtime)
        latency_ms: float | None = None
        if self._run_started_at is not None:
            latency_ms = (time.perf_counter() - self._run_started_at) * 1000
            self._run_started_at = None
        if latency_ms is not None:
            elapsed = (
                f"{latency_ms / 1000:.2f}s"
                if latency_ms >= 1000
                else f"{latency_ms:.0f}ms"
            )
            timing = f", elapsed={elapsed}"
        else:
            timing = ""
        print(
            f"\n===== [企微运营 Harness] 本轮运行结束 "
            f"(agent=main, who={user_id or '-'}, thread={thread_id or '-'}{timing}) =====\n",
            flush=True,
        )
        emit_audit_event(
            action="run_finished",
            agent=self.agent_name,
            user_id=user_id,
            thread_id=thread_id,
            what="run_finished",
            success=True,
            latency_ms=latency_ms,
        )
