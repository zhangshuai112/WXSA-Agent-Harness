---
name: employee-chat-suggestion-skill
description: 根据上下文中的员工与客户近期聊天历史、客户基本信息、客户标签、客户画像和订单历史生成企业微信回复建议，并通过 HumanInTheLoopMiddleware 交由员工审核；审核通过返回 true，否则返回 false。
---

# 员工与客户聊天建议

本 skill 用于生成给企业微信客户的回复建议，并在展示给员工后等待人工审核。员工与客户的近期聊天历史、客户数据必须已经放在当前 agent 上下文中。

## 输入上下文

从上下文中读取以下信息：

- 员工信息：至少包含员工的企业微信 `user_id`。
- 客户基本信息：至少包含客户的 `external_id`、姓名或可用称呼。
- 员工与客户近期聊天历史：用于识别客户最后一句话、问题、意图、情绪和待办事项。
- 客户标签：用于判断客户阶段、偏好和服务重点。
- 客户画像：用于调整沟通方式和推荐内容。
- 客户订单历史：用于识别已购买商品、订单状态、售后或复购相关上下文。

如果缺少生成建议所必需的聊天历史、客户标识或客户数据，不得编造内容，也不得调用本 skill 的审核流程；直接返回 `false`。

## 生成聊天建议

生成一条自然、准确、可以直接发送给客户的中文回复。遵循以下规则：

1. 优先回应客户最近一条消息和明确问题，再补充必要信息。
2. 只使用上下文中有依据的信息，不虚构价格、库存、订单状态、承诺、政策、时间或处理结果。
3. 可以参考客户标签、画像和订单历史调整语气与内容，但不得把内部标签、画像字段、订单内部字段名暴露给客户。
4. 回复应简洁、专业、友好，符合员工与客户的正常沟通方式。
5. 生成的内容是草稿，不能描述为已经发送，也不能直接调用客户消息发送 API。

建议内部保存以下数据：

```json
{
  "status": "pending_review",
  "draft_message": "待员工审核的客户回复",
  "final_message": "",
  "review_action": "",
  "review_comment": "",
  "employee_id": "员工 user_id",
  "customer_id": "客户 external_id"
}
```

## 通知员工

生成草稿后，调用 `notify_wecom_user` 向指定员工发送审核通知。通知内容至少包括客户标识或客户称呼、完整回复草稿和请员工在前端选择审核动作的提示。

通知只能表示“有一条待审核建议”，不得表示客户已收到消息。不能把 `notify_wecom_user` 当作向客户发送消息的工具。如果通知调用失败，直接返回 `false`，不要继续等待审核。

## HumanInTheLoopMiddleware 审核

运行 agent 时必须使用 `HumanInTheLoopMiddleware` 拦截审核闸门工具。审核闸门只负责在员工通过后返回建议，不负责向客户发送消息。例如：

```python
from langchain_core.tools import tool
from deepagents import create_deep_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

@tool("approve_chat_suggestion")
def approve_chat_suggestion(employee_id: str, customer_id: str, message: str) -> bool:
    """返回员工审核后的聊天建议结果，不发送客户消息。"""
    return bool(employee_id and customer_id and message.strip())

agent = create_deep_agent(
    model=model,
    tools=[notify_wecom_user, approve_chat_suggestion],
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "approve_chat_suggestion": {
                    "allowed_decisions": ["approve", "reject", "edit", "respond"],
                    "description": "请员工审核企业微信客户回复建议。",
                },
            }
        )
    ],
)
```

如果当前安装版本从 `langchain.agents.middleware` 导出 `HumanInTheLoopMiddleware`，使用该版本实际提供的导入路径。以已安装版本的 API 为准，不要自行实现另一套中断机制。

前端展示 interrupt 时提供 HumanInTheLoopMiddleware 原生的四种决策：`approve`、`reject`、`edit`、`respond`。前端必须保存 LangGraph 的 thread/checkpoint 标识、草稿、员工标识、客户标识和审核状态。员工操作后使用同一个 thread/checkpoint 通过 `Command(resume=...)` 恢复执行，不能重新创建线程。

## 四种审核动作

- `approve`：同意当前调用，执行审核闸门工具并使用原草稿。
- `reject`：拒绝当前调用，审核闸门工具不执行，使用人工拒绝信息作为拒绝结果。
- `edit`：人工编辑工具参数后执行审核闸门工具；只允许修改完整消息正文，不得修改员工或客户标识。
- `respond`：审核闸门工具不执行，直接使用人工提供的回答作为该工具的调用结果。

编辑后的内容必须非空，且不能绕过审核闸门。不得在审核通过后自动调用发送客户消息的工具。

## 输出要求

本 skill 的最终输出只能是布尔值：

```text
true
```

表示员工已同意当前建议或修改后通过；或者：

```text
false
```

表示上下文缺失、通知失败、员工拒绝，或审核流程发生异常。

不要把草稿、审核详情或“已发送”文字作为最终返回值。`true` 只代表聊天建议已通过员工审核，不代表消息已经发送给客户。客户消息发送必须由其他明确授权的流程负责。

## 工具边界

- 必须使用上下文已有的聊天历史和客户数据，不重复查询已提供的数据。
- 必须调用 `notify_wecom_user` 申请员工审核。
- 必须通过 `HumanInTheLoopMiddleware` 实现审核中断和恢复。
- 不调用 `send_wecom_kf_message`，不调用员工个人对客户的发送接口。
- 不把未经审核的草稿描述成已发送消息。
