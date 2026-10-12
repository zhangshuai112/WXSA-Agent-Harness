"""Agent 整轮运行限制：墙钟时间 + 工具调用次数（项目级外部保险丝）。

与 DeepAgents/LangChain 的 ModelCallLimit / ToolCallLimit middleware 互补：
那些限制 Agent 内部 loop；本模块限制「服务端/客户端观察到的一整轮任务」。

典型用法（sidebar 流式消费）::

    tracker = AgentRunLimitTracker(task_kind="tag_profile")
    async for chunk in watch_stream(stream, tracker):
        ...

HITL：检测到 interrupt 时调用 ``tracker.pause()``，恢复执行后 ``tracker.resume()``，
避免等人审批把墙钟时间耗尽。
"""

# 支持现代类型注解写法
from __future__ import annotations

# 读环境变量，配置是否启用、上限数值
import os
# monotonic：单调时钟，用于算经过时间（不受系统调时影响）
import time
# dataclass：用装饰器快速定义数据类
from dataclasses import dataclass
# 常用类型注解
from typing import Any, AsyncIterator, Iterable, Mapping, Optional


# 各业务任务类型的默认上限：(最大工具调用次数, 最大秒数)
# 面向本项目业务，而不是通用 coding agent
TASK_KIND_DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "default": (800, 600),         # 默认：800 次工具 / 10 分钟
    "customer_query": (80, 300),  # 查客户数据：少一点、短一点
    "tag_profile": (120, 600),     # 标签/画像
    "chat_suggest": (100, 600),    # 聊天/客服建议
    "schedule": (50, 600),        # 日程
    "skill_mgmt": (100, 900),     # 技能管理：可能更久
}

# 侧边栏菜单 id → 上面的 task_kind
MENU_ID_TO_TASK_KIND: dict[str, str] = {
    "profile_suggestion": "tag_profile",   # 画像建议菜单
    "tag_suggestion": "tag_profile",       # 标签建议菜单
    "chat_suggestion": "chat_suggest",     # 员工聊天建议
    "kf_chat_suggestion": "chat_suggest",  # 客服聊天建议
    "schedule_suggestion": "schedule",     # 日程建议
}


class AgentRunLimitExceeded(RuntimeError):
    """本轮 Agent 任务超过工具次数或运行时间上限时抛出的异常。"""

    def __init__(
        self,
        message: str,                 # 给人看的错误文案
        *,                            # 后面必须用关键字传参
        task_kind: str,               # 哪种任务超限
        tool_calls: int,              # 当前已统计的工具次数
        max_tool_calls: int,          # 允许的最大工具次数
        elapsed_seconds: float,       # 当前有效已运行秒数
        max_seconds: int,             # 允许的最大秒数
        reason: str,                  # "time" 或 "tool_calls"
    ) -> None:
        # 把 message 交给 RuntimeError 基类保存
        super().__init__(message)
        # 下面这些属性方便 API / 前端直接读结构化信息
        self.task_kind = task_kind
        self.tool_calls = tool_calls
        self.max_tool_calls = max_tool_calls
        self.elapsed_seconds = elapsed_seconds
        self.max_seconds = max_seconds
        self.reason = reason  # "time" | "tool_calls"

    def to_dict(self) -> dict[str, Any]:
        """转成可 JSON 序列化的字典，方便 SSE / HTTP 返回给前端。"""
        return {
            "error": str(self),                      # 异常文本
            "error_type": "AgentRunLimitExceeded",   # 固定类型名
            "reason": self.reason,                   # 超时还是工具超限
            "task_kind": self.task_kind,
            "tool_calls": self.tool_calls,
            "max_tool_calls": self.max_tool_calls,
            "elapsed_seconds": round(self.elapsed_seconds, 2),  # 保留两位小数
            "max_seconds": self.max_seconds,
        }


def _env_int(name: str) -> int | None:
    """读取环境变量并转成 int；空或不合法则返回 None。"""
    # 取环境变量，没有则当空串，再 strip
    raw = (os.getenv(name) or "").strip()
    # 没配置
    if not raw:
        return None
    try:
        # 能转成整数就返回
        return int(raw)
    except ValueError:
        # 配了但不是数字：忽略
        return None


def _truthy(value: Optional[str]) -> bool:
    """把常见真值字符串（1/true/yes/on）判定为 True。"""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def run_limits_enabled() -> bool:
    """是否启用本轮运行限制；未配置环境变量时默认启用。"""
    raw = os.getenv("AGENT_RUN_LIMITS_ENABLED")
    # 没配或空串：默认 True
    if raw is None or raw.strip() == "":
        return True
    # 配了则按真值字符串解析
    return _truthy(raw)


@dataclass(frozen=True)  # frozen=True：实例创建后字段不可改，当配置快照用
class AgentRunLimits:
    """单轮任务上限配置。"""

    max_tool_calls: int          # 最多允许多少次工具调用
    max_seconds: int             # 最多允许多少秒（有效运行时间）
    task_kind: str = "default"   # 任务类型名

    @classmethod
    def from_env(cls, task_kind: str = "default") -> "AgentRunLimits":
        """根据 task_kind + 环境变量组装一份上限配置。"""
        # 规范化 kind：空则 default
        kind = (task_kind or "default").strip() or "default"
        # 取出该 kind 的默认 (工具次数, 秒数)；未知 kind 用 default
        default_tools, default_seconds = TASK_KIND_DEFAULT_LIMITS.get(
            kind, TASK_KIND_DEFAULT_LIMITS["default"]
        )
        # 全局 env 可覆盖所有 task_kind；也可按 kind 单独覆盖：
        # AGENT_RUN_MAX_TOOL_CALLS / AGENT_RUN_MAX_SECONDS
        # AGENT_RUN_LIMIT_tag_profile=60,600
        max_tools = _env_int("AGENT_RUN_MAX_TOOL_CALLS")      # 全局工具上限（可选）
        max_seconds = _env_int("AGENT_RUN_MAX_SECONDS")       # 全局时间上限（可选）
        per_kind = (os.getenv(f"AGENT_RUN_LIMIT_{kind}") or "").strip()  # 按 kind 覆盖
        # 格式必须是 "次数,秒数"
        if per_kind and "," in per_kind:
            left, right = per_kind.split(",", 1)  # 只切第一处逗号
            try:
                max_tools = int(left.strip())     # 左边：工具次数
                max_seconds = int(right.strip())  # 右边：秒数
            except ValueError:
                # 格式错误：保持前面已解析的全局值 / 后面退回默认
                pass
        # 组装不可变配置对象：env 有值用 env，否则用表内默认
        return cls(
            max_tool_calls=max_tools if max_tools is not None else default_tools,
            max_seconds=max_seconds if max_seconds is not None else default_seconds,
            task_kind=kind,
        )


def infer_task_kind(
    *,
    menu_id: str | None = None,     # 侧边栏点的菜单
    message: str | None = None,     # 用户自然语言
    explicit: str | None = None,    # 调用方显式指定
) -> str:
    """从菜单或显式参数（再不行靠关键词）推断 task_kind。"""
    # 1. 显式指定优先
    if explicit and explicit.strip():
        return explicit.strip()
    # 2. 菜单 id 映射
    if menu_id and menu_id in MENU_ID_TO_TASK_KIND:
        return MENU_ID_TO_TASK_KIND[menu_id]
    # 3. 从消息文本猜
    text = (message or "").strip()
    if any(k in text for k in ("标签", "画像", "tag", "profile")):
        return "tag_profile"
    if any(k in text for k in ("日程", "schedule")):
        return "schedule"
    if any(k in text for k in ("客服", "聊天", "回复", "chat")):
        return "chat_suggest"
    if any(k in text for k in ("客户数据", "订单", "查询")):
        return "customer_query"
    if any(k in text for k in ("技能", "skill")):
        return "skill_mgmt"
    # 4. 都猜不到
    return "default"


class AgentRunLimitTracker:
    """观察 LangGraph 事件流，限制本轮工具次数与有效运行时间。"""

    def __init__(
        self,
        task_kind: str = "default",              # 任务类型
        limits: AgentRunLimits | None = None,    # 可直接传入配置；否则 from_env
    ) -> None:
        # 保存上限配置
        self.limits = limits or AgentRunLimits.from_env(task_kind)
        # 规范化后的 task_kind（可能被 from_env 修过）
        self.task_kind = self.limits.task_kind
        # 已统计到的工具调用次数
        self.tool_calls = 0
        # 本轮开始的单调时间戳
        self._started_at = time.monotonic()
        # 是否正处于 HITL 暂停（等人审批）
        self._paused = False
        # 本次 pause 开始的时间；未 pause 时为 None
        self._pause_started_at: float | None = None
        # 历史上已经累计的暂停总秒数
        self._paused_seconds = 0.0
        # 是否启用限制（可被环境变量关掉）
        self.enabled = run_limits_enabled()

    # ---- HITL 友好计时 ----

    def pause(self) -> None:
        """进入人工审核等待：暂停墙钟累计。"""
        # 已经 paused：不要重复记起点
        if self._paused:
            return
        # 标记进入暂停
        self._paused = True
        # 记录暂停开始时刻
        self._pause_started_at = time.monotonic()

    def resume(self) -> None:
        """审核结束、任务继续：恢复墙钟累计。"""
        # 本来就没 pause：无操作
        if not self._paused:
            return
        # 把这一段 pause 时长累加进总暂停时间
        if self._pause_started_at is not None:
            self._paused_seconds += time.monotonic() - self._pause_started_at
        # 清空本次 pause 起点
        self._pause_started_at = None
        # 标记恢复运行
        self._paused = False

    @property
    def elapsed_seconds(self) -> float:
        """有效运行秒数 = 总经过时间 - 所有暂停时间（含当前仍在 pause 的一段）。"""
        now = time.monotonic()                 # 当前时刻
        paused = self._paused_seconds          # 已结束的暂停总和
        # 如果此刻仍在 pause，还要把「当前这段未结束的暂停」加上
        if self._paused and self._pause_started_at is not None:
            paused += now - self._pause_started_at
        # 不能为负
        return max(0.0, now - self._started_at - paused)

    # ---- 检查 ----

    def _raise(self, reason: str) -> None:
        """构造并抛出 AgentRunLimitExceeded。"""
        elapsed = self.elapsed_seconds
        if reason == "time":
            # 超时文案
            msg = (
                f"Agent 运行超时: task_kind={self.task_kind}, "
                f"elapsed={elapsed:.1f}s > max_seconds={self.limits.max_seconds}"
            )
        else:
            # 工具次数超限文案
            msg = (
                f"Agent 工具调用超限: task_kind={self.task_kind}, "
                f"tool_calls={self.tool_calls} > "
                f"max_tool_calls={self.limits.max_tool_calls}"
            )
        # 抛出带结构化字段的异常
        raise AgentRunLimitExceeded(
            msg,
            task_kind=self.task_kind,
            tool_calls=self.tool_calls,
            max_tool_calls=self.limits.max_tool_calls,
            elapsed_seconds=elapsed,
            max_seconds=self.limits.max_seconds,
            reason=reason,
        )

    def check_time(self) -> None:
        """若启用且未暂停，检查是否超时。"""
        # 关闭限制，或正在 HITL 等待：不检查时间
        if not self.enabled or self._paused:
            return
        # 有效运行时间超过上限：抛超时
        if self.elapsed_seconds > self.limits.max_seconds:
            self._raise("time")

    def check_tool_calls(self) -> None:
        """若启用，检查工具次数是否超限。"""
        if not self.enabled:
            return
        # 注意：这里用 > 而不是 >=，等于上限时仍允许（严格大于才炸）
        if self.tool_calls > self.limits.max_tool_calls:
            self._raise("tool_calls")

    def record_tool_call(self, n: int = 1) -> None:
        """直接累加工具调用次数（给 middleware / 单测用，不走事件解析）。"""
        if not self.enabled:
            return
        # 先检查时间，再累加，再检查次数
        self.check_time()
        self.tool_calls += max(0, n)  # n 为负时当 0
        self.check_tool_calls()

    # ---- 事件观察 ----

    def observe_event(self, event: Any) -> None:
        """消费一个 LangGraph / SDK 流事件：更新暂停状态、统计工具、做限制检查。"""
        # 总开关关闭：什么都不做
        if not self.enabled:
            return

        # 每来一个事件先看看有没有超时
        self.check_time()

        # 若事件看起来是 HITL interrupt：进入 pause，且本事件不记工具
        if self._looks_like_interrupt(event):
            self.pause()
            return

        # 当前处于 pause，但新事件不再是 interrupt：认为审核结束，resume
        if self._paused and not self._looks_like_interrupt(event):
            # _still_interrupt_payload 目前等价于再判断一次 interrupt
            if not self._still_interrupt_payload(event):
                self.resume()

        # 从事件里数「新开始的工具调用」个数
        tool_delta = self._count_tool_starts(event)
        if tool_delta:
            # 累加计数
            self.tool_calls += tool_delta
            # 检查是否超限
            self.check_tool_calls()

    def snapshot(self) -> dict[str, Any]:
        """导出当前计数快照，便于调试或返回给前端。"""
        return {
            "task_kind": self.task_kind,
            "tool_calls": self.tool_calls,
            "max_tool_calls": self.limits.max_tool_calls,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "max_seconds": self.limits.max_seconds,
            "paused": self._paused,
            "enabled": self.enabled,
        }

    # ---- 事件解析（兼容 SDK chunk / dict / tuple）----

    @staticmethod
    def _as_mapping(event: Any) -> Mapping[str, Any]:
        """把各种形态的流事件尽量归一成 {event/method, data} 字典。"""
        # 已经是 dict / Mapping
        if isinstance(event, Mapping):
            return event
        # 元组常见形态：("messages", payload) / ("updates", payload)
        if isinstance(event, tuple) and len(event) >= 2:
            return {"event": event[0], "data": event[1]}
        # SDK 对象：有 .event / .data 属性
        name = getattr(event, "event", None)
        data = getattr(event, "data", None)
        if name is not None:
            return {"event": name, "data": data}
        # 认不出来：空映射
        return {}

    def _looks_like_interrupt(self, event: Any) -> bool:
        """启发式判断：这个事件是不是人工中断 / HITL interrupt。"""
        payload = self._as_mapping(event)
        # 事件名或 method 里带 interrupt
        event_name = str(payload.get("event") or payload.get("method") or "").lower()
        if "interrupt" in event_name:
            return True
        data = payload.get("data")
        if isinstance(data, Mapping):
            # 常见字段：__interrupt__ / interrupts
            if data.get("__interrupt__") or data.get("interrupts"):
                return True
            # updates 里嵌套对象也可能带中断标记
            for value in data.values():
                if isinstance(value, Mapping) and (
                    "__interrupt__" in value or "interrupt" in value
                ):
                    return True
        return False

    def _still_interrupt_payload(self, event: Any) -> bool:
        """判断是否仍是 interrupt 载荷（当前实现直接复用 _looks_like_interrupt）。"""
        return self._looks_like_interrupt(event)

    def _count_tool_starts(self, event: Any) -> int:
        """从单条流事件中统计「新出现的工具调用」数量。"""
        payload = self._as_mapping(event)
        # method 或 event 名称（小写比较）
        method = str(payload.get("method") or payload.get("event") or "").lower()
        data = payload.get("data")

        # 文档所述：method in {tool_calls, tools} → 至少算 1，或按内容细数
        if method in {"tool_calls", "tools"}:
            return max(1, self._count_tool_calls_in_obj(data))

        # LangGraph SDK messages 模式：AIMessage 上可能带 tool_calls
        if method in {"messages", "messages/partial", "messages/complete"}:
            return self._count_tool_calls_in_messages(data)

        # updates / values 模式：节点输出里可能嵌套 messages / tool_calls
        if method in {"updates", "values"}:
            return self._count_tool_calls_in_obj(data)

        # 其它：对整个 payload 做一次递归扫描
        return self._count_tool_calls_in_obj(payload)

    def _count_tool_calls_in_messages(self, data: Any) -> int:
        """专门处理 messages 流里的 data 形态。"""
        # SDK 常见: (message_chunk, metadata)
        if isinstance(data, tuple) and data:
            return self._count_tool_calls_in_obj(data[0])
        # 或消息列表
        if isinstance(data, list):
            return sum(self._count_tool_calls_in_obj(item) for item in data)
        # 单条消息对象 / dict
        return self._count_tool_calls_in_obj(data)

    def _count_tool_calls_in_obj(self, obj: Any) -> int:
        """递归地在 dict / list / 消息对象里查找 tool_calls。"""
        # 空
        if obj is None:
            return 0
        # 字典：优先看 tool_calls 字段
        if isinstance(obj, Mapping):
            # OpenAI 风格：AI message dict 上的 tool_calls
            tool_calls = obj.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                # 只统计带 name 的完整 tool call（流式半截可能没有 name）
                return sum(
                    1
                    for tc in tool_calls
                    if isinstance(tc, Mapping) and tc.get("name")
                )
            # 有的实现放在 additional_kwargs.tool_calls
            additional = obj.get("additional_kwargs")
            if isinstance(additional, Mapping):
                nested = additional.get("tool_calls")
                if isinstance(nested, list) and nested:
                    return sum(
                        1
                        for tc in nested
                        if isinstance(tc, Mapping)
                        and (tc.get("function", {}) or {}).get("name")
                        or tc.get("name")
                    )
            # 再递归扫描其它嵌套字段
            total = 0
            for key, value in obj.items():
                if key in {"tool_calls", "tools"} and isinstance(value, list):
                    total += len(value) or 0
                elif isinstance(value, (Mapping, list, tuple)):
                    total += self._count_tool_calls_in_obj(value)
            return total
        # 列表 / 元组：对每个元素递归求和
        if isinstance(obj, (list, tuple)):
            return sum(self._count_tool_calls_in_obj(item) for item in obj)
        # LangChain message 对象：读 .tool_calls 属性
        tool_calls = getattr(obj, "tool_calls", None)
        if isinstance(tool_calls, list) and tool_calls:
            count = 0
            for tc in tool_calls:
                # dict 形态
                if isinstance(tc, Mapping) and tc.get("name"):
                    count += 1
                # 对象形态
                elif getattr(tc, "name", None):
                    count += 1
            return count
        # 都不是
        return 0


async def watch_stream(
    stream: AsyncIterator[Any],      # 原始异步事件流
    tracker: AgentRunLimitTracker,   # 限制追踪器
) -> AsyncIterator[Any]:
    """包装异步事件流：每条事件先 observe，超限则抛 AgentRunLimitExceeded。"""
    async for event in stream:       # 逐条拉取上游事件
        tracker.observe_event(event)  # 先检查/计数（可能抛异常）
        yield event                   # 再原样交给下游（sidebar）


def watch_stream_sync(
    stream: Iterable[Any],           # 原始同步可迭代流
    tracker: AgentRunLimitTracker,
) -> Iterable[Any]:
    """同步版事件流包装（逻辑同 watch_stream）。"""
    for event in stream:
        tracker.observe_event(event)
        yield event
