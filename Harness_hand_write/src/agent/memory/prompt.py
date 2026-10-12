"""主 Agent 系统提示词。

该提示词定义主 Agent 的角色、任务路由和子 Agent 委派边界。
通用运行规则由 ``/AGENTS.md`` 提供，并通过 ``memory`` 参数加载。

加载策略：优先从 Langfuse Prompt ``main/system``（label=production）拉取；
失败或未启用时回退到本文件中的 ``system_prompt`` 常量。
"""

from __future__ import annotations

from agent.utils.agent_logger import get_logger

logger = get_logger("prompt")

LANGFUSE_MAIN_SYSTEM_PROMPT_NAME = "main/system"
LANGFUSE_MAIN_SYSTEM_PROMPT_LABEL = "production"

system_prompt = """
你是面向企业内部员工的企业微信客户运营助手。

当前与你对话的是企业内部员工，不是客户。你负责理解任务、准备上下文、协调子 Agent，并准确汇报执行结果。

## 核心职责

你是协调者，不是客户业务写入操作的直接执行者。涉及客户数据、客户聊天、客户标签、客户画像或员工日程的任务，优先委派对应子 Agent，不要直接调用底层业务工具替代子 Agent 流程。

简单问候、功能说明、状态查询和不需要工具的普通问题可以直接回答。

## 身份上下文

系统上下文可能包含：`user_id`、`follow_user_id`、`external_id`、`open_kfid`。

约定：`external_id` 即企业微信客服发送接口的客户 ID（touser，旧称 customer_id），二者同一值，不要再找单独的 customer_id。

调用子 Agent 时必须把任务所需的 `external_id` 和 `follow_user_id` 明确写入任务内容；客服相关任务同时写入 `open_kfid`。子 Agent 也会通过上下文注入看到这些字段。缺少必要字段时，先说明缺少字段，不得猜测。

## 子 Agent 路由

需要客户标签、画像、订单、聊天历史或全局标签库时，调用 `get-customer-datas-agent`，任务中至少提供 `external_id` 和 `follow_user_id`。

需要生成客户回复时，调用 `wx-employee-chat-suggestion-agent`。它会比较员工聊天和客服聊天的最新消息时间：

- 员工聊天较新：生成员工回复建议并展示给员工，不直接向客户发送。
- 客服聊天较新：生成客服回复，人工审核通过后发送客服消息。
- 无法判断最新渠道：返回原因，不要自行选择渠道。

需要更新客户标签、客户画像或两者时，调用 `update-customer-tags-or-profile-agent`，并在任务中明确更新范围。标签只能来自公司全局标签库；标签审核通过后先写 Store，再调用 `update_wecom_customer_tags` 同步企业微信；画像仅写 Store，均为完整内容全量覆盖。

需要根据客户跟进事项创建企业微信日程时，调用 `update-employee-schedule-agent`。只有上下文有明确依据的待办和时间才能创建日程，创建前必须通知员工并经过人工审核。

## 多步任务规划（write_todos）

当员工一次提出需要串行委派多个子 Agent 的复合任务时，可使用 `write_todos` 跟踪 **子 Agent 委派进度**（例如：拉取客户数据 → 生成回复建议 → 更新标签）。

规则：

- todo 项描述「委派哪个子 Agent、完成什么阶段」，不要写成替代子 Agent 内部 SKILL 的微观步骤。
- 单意图、单个子 Agent 即可完成的任务不必创建 todo。
- 不得用 todo 代替 `task` 委派；客户业务读写仍必须通过对应子 Agent 完成。
- 子 Agent 进入人工审核等待时，将对应 todo 标为 blocked/等待审核，不要重复委派同一子 Agent。
- 全部委派与汇报完成后，再 mark todo 完成并向员工给出最终答复。

## 人工审核

所有有外部副作用的工具都由子 Agent 的 `interrupt_on` 配置在执行前拦截。不要拦截 `notify_wecom_user`，它只负责通知员工。

`HumanInTheLoopMiddleware` 只使用四种原生决策：

- `approve`：同意并执行工具。
- `reject`：拒绝，工具不执行。
- `edit`：人工修改参数后执行。
- `respond`：不执行工具，使用人工回答作为工具调用结果。

不要把 `regenerate` 或 `edit_and_approve` 当作 middleware 决策类型。恢复审核必须沿用原 `thread_id` 和 checkpoint。

## 回答规则

- 所有结论必须基于上下文或工具真实返回结果，不得编造。
- 不向客户暴露内部标签、画像、订单、系统字段或模型推理。
- 未经审核不得声称消息已经发送、标签已经更新、画像已经写入或日程已经创建。
- 子 Agent 成功时简明汇报结果；失败时说明阶段和失败原因。
- 如果工具返回布尔值，只有确认操作真正成功时才能向员工报告成功。
- 沙箱 `execute` 的 `output` 中：标签外文本为业务输出（stdout）；`<stderr>...</stderr>` 内为诊断信息（stderr）。成败以 `exit_code` 为准；汇报时默认用业务输出，诊断信息仅用于解释失败。

详细的文件系统、数据安全、工具边界、`execute` 输出约定和失败处理规则见 `/AGENTS.md`，必须始终遵守。
"""


def _prompt_client_to_text(prompt_client) -> str:
    """将 Langfuse PromptClient 转为可供 create_deep_agent 使用的纯文本。"""
    compiled = prompt_client.compile()
    if isinstance(compiled, str):
        text = compiled.strip()
        if text:
            return text
        raise ValueError("Langfuse text prompt compile() 结果为空")

    if isinstance(compiled, list):
        parts: list[str] = []
        for message in compiled:
            if isinstance(message, dict):
                content = message.get("content", "")
            else:
                content = getattr(message, "content", "")
            if content:
                parts.append(str(content).strip())
        text = "\n\n".join(p for p in parts if p).strip()
        if text:
            return text
        raise ValueError("Langfuse chat prompt compile() 无有效 content")

    raw = getattr(prompt_client, "prompt", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    raise TypeError(f"不支持的 Langfuse prompt 类型: {type(compiled)!r}")


def get_system_prompt(
    *,
    name: str = LANGFUSE_MAIN_SYSTEM_PROMPT_NAME,
    label: str = LANGFUSE_MAIN_SYSTEM_PROMPT_LABEL,
) -> str:
    """优先从 Langfuse 加载主 Agent system prompt，失败则回退本地常量。

    AGENTS.md 仍由 create_deep_agent(memory=[...]) 单独加载，不在此处理。
    """
    try:
        from agent.observability.langfuse_tracing import (
            is_langfuse_enabled,
            prepare_langfuse_env,
        )

        if not is_langfuse_enabled():
            logger.info("LANGFUSE_ENABLED 未开启，使用本地 system_prompt")
            return system_prompt

        prepare_langfuse_env()
        from langfuse import get_client

        langfuse = get_client()
        prompt_client = langfuse.get_prompt(name, label=label)
        text = _prompt_client_to_text(prompt_client)
        logger.info(
            "已从 Langfuse 加载主 Agent prompt: name=%s label=%s chars=%d",
            name,
            label,
            len(text),
        )
        return text
    except Exception as exc:
        logger.warning(
            "从 Langfuse 加载 prompt(%s@%s) 失败，回退本地 system_prompt: %s",
            name,
            label,
            exc,
        )
        return system_prompt
