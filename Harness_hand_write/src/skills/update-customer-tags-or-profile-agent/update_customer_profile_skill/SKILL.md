---
name: update-customer-profile-skill
description: 根据上下文中的客服与员工近期聊天历史、客户标签、现有画像和基本信息生成完整客户画像，经员工使用 HumanInTheLoopMiddleware 审核通过后调用 update_customer_profile 全量覆盖写入 store；成功返回 True，异常返回失败原因。
---

# 更新客户画像

本 skill 用于根据当前上下文生成新的客户画像，并在员工人工审核通过后将完整画像写入 store。画像更新采用全量覆盖策略：审核通过后传给 `update_customer_profile` 的 `profile` 必须是完整画像对象，不能只提交本次变化的字段。

## 所需上下文

必须从当前上下文读取以下数据：

- 客户的 `external_id`；
- 负责跟进客户的员工 `follow_user_id`；
- 员工与客户近期聊天历史；
- 企业微信客服与客户近期聊天历史；
- 客户当前标签；
- 客户现有画像；
- 客户基本信息；
- 用于人工审核通知的员工 `user_id`。

聊天历史和客户数据已经在上下文中时，不要重复调用获取工具。若缺少 `external_id`、`follow_user_id`、审核员工 `user_id`、关键聊天历史、客户基本信息或现有画像，无法安全生成完整画像时，直接返回具体失败原因，不得编造数据。

## 画像生成规则

根据客服与客户、员工与客户的近期聊天历史，结合客户标签、现有画像和基本信息，生成客户当前的完整画像。

生成时遵守以下规则：

1. 只使用上下文中有依据的信息，不虚构客户需求、预算、购买意向、联系方式、职业、地区、订单状态或其他属性。
2. 保留现有画像中仍然有效的信息；对聊天记录明确反映出的新信息进行更新。
3. 无法确认的字段保留原值、使用空值，或明确标记为未知，不能用猜测值覆盖已有事实。
4. 画像内容应便于后续客服和员工理解客户需求、偏好、阶段、关注点和服务策略。
5. 不把内部推理过程、模型置信度或“待审核”文字写入画像字段。
6. 生成的是完整画像草稿，不是增量 patch。字段结构应与项目中 `update_customer_profile` 工具接受的 `profile` 结构一致。

建议在内部保存如下审核记录：

```json
{
  "status": "pending_review",
  "external_id": "客户 external_id",
  "follow_user_id": "负责员工 user_id",
  "draft_profile": {},
  "final_profile": {},
  "review_action": "",
  "review_comment": ""
}
```

## 通知员工

生成完整画像草稿后，必须调用 `notify_wecom_user` 通知指定员工审核。通知内容至少包括：

- 客户标识或客户称呼；
- “本次为全量覆盖更新”的明确提示；
- 当前完整画像草稿；
- 前端审核入口或审核动作提示。

通知示例：

```python
notify_wecom_user.invoke({
    "user_id": employee_user_id,
    "content": (
        "客户画像待审核。本次审核通过后将全量覆盖当前画像，请确认以下完整画像：\n"
        + format_profile(draft_profile)
    ),
    "msgtype": "text",
})
```

通知失败时不得进入更新流程，返回：

```text
通知员工失败：<异常信息>
```

## HumanInTheLoopMiddleware 审核

必须使用 `HumanInTheLoopMiddleware` 在真正调用 `update_customer_profile` 前暂停流程。推荐直接拦截具有写入副作用的更新工具：

```python
from deepagents import create_deep_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

hitl = HumanInTheLoopMiddleware(
    interrupt_on={
        "update_customer_profile": {
            "allowed_decisions": ["approve", "edit", "reject", "respond"],
            "description": "请审核即将全量覆盖写入 store 的客户完整画像。",
        }
    }
)

agent = create_deep_agent(
    model=model,
    tools=[notify_wecom_user, update_customer_profile],
    middleware=[hitl],
    checkpointer=checkpointer,
)
```

如果项目使用 `create_deep_agent(..., interrupt_on={...})`，可以使用该配置，让 DeepAgents 自动创建中间件。不要对同一个工具重复配置两套 `HumanInTheLoopMiddleware`。

当前环境中 `HumanInTheLoopMiddleware` 通常从 `langchain.agents.middleware` 导入；以实际安装版本提供的导入路径为准。

前端必须保存 `thread_id`、checkpoint、interrupt、客户标识、员工标识和完整画像草稿。员工选择后使用同一个 thread/checkpoint，通过 `Command(resume=...)` 恢复流程，不得重新创建线程。

## 四种审核动作

### approve

前端发送 middleware 的 `approve` 决策：

```python
Command(resume={"decisions": [{"type": "approve"}]})
```

中间件放行原始 `update_customer_profile` 调用。调用参数必须包含完整 `profile`，成功写入后返回 `True`。

### reject

前端发送 `reject` 决策：

```python
Command(resume={
    "decisions": [{
        "type": "reject",
        "message": "员工拒绝本次客户画像更新，请停止流程。"
    }]
})
```

更新工具不得执行。人工拒绝属于正常终止，返回：

```text
员工拒绝更新客户画像
```

### edit

前端使用 middleware 的 `edit` 决策，将员工修改后的完整画像写回工具参数：

```python
Command(resume={
    "decisions": [{
        "type": "edit",
        "edited_action": {
            "name": "update_customer_profile",
            "args": {
                "external_id": external_id,
                "follow_user_id": follow_user_id,
                "profile": edited_complete_profile
            }
        }
    }]
})
```

服务端恢复执行前必须校验：

- 工具名仍为 `update_customer_profile`；
- `external_id` 和 `follow_user_id` 与原审核请求一致；
- `profile` 是完整对象而不是局部字段 patch；
- 员工修改后的画像不是空对象，且符合项目定义的画像结构。

员工修改后通过时，更新工具执行成功才返回 `True`。

### respond

前端使用 `respond` 决策时，不执行 `update_customer_profile`，直接把人工回答作为该工具的调用结果：

```python
Command(resume={
    "decisions": [{
        "type": "respond",
        "message": "<人工提供的工具调用结果>"
    }]
})
```

`respond` 是合法的审核完成结果，但不表示客户画像已经写入 Store。

## 审核通过后的更新

只有 middleware 返回 `approve` 或合法的 `edit` 决策后，才允许调用：

```python
update_customer_profile.invoke({
    "external_id": external_id,
    "follow_user_id": follow_user_id,
    "profile": complete_profile,
})
```

`profile` 会通过 `upsert` 写入 store，但本 skill 的语义是全量覆盖：调用前应确保其中包含需要保留的完整画像字段。不要把本次生成结果当作增量更新，也不要在工具调用前后自动合并未审核字段。

## 返回格式

成功完成以下全部条件时，只返回 Python 布尔值：

```python
True
```

成功条件：

1. 已根据上下文生成完整画像；
2. 已通过 `notify_wecom_user` 通知员工；
3. 员工已同意或修改后通过；
4. `update_customer_profile` 已成功执行并写入 store。

以下情况返回失败原因字符串：

```text
<失败阶段>失败：<具体原因>
```

包括上下文缺失、画像生成异常、员工通知异常、员工拒绝、审核参数非法、store 更新异常或其他运行时异常。不要吞掉异常，也不要在更新未确认成功时返回 `True`。

人工拒绝是正常业务终止，但按照本 skill 的约定仍返回失败原因，例如：`员工拒绝更新客户画像`。只有 store 更新成功后才返回 `True`。

## 工具边界

- 必须调用 `notify_wecom_user` 申请人工审核。
- 必须调用 `update_customer_profile` 执行最终写入。
- 必须通过 `HumanInTheLoopMiddleware` 拦截更新工具。
- 不得在审核前写入 store。
- 不得把局部字段更新冒充为完整画像更新。
- 不得把未经审核的画像描述为已更新。
