---
name: kf-chat-skill
description: 根据上下文中的微信客服聊天历史及客户基本信息、标签、画像和订单历史生成回复，经员工人工审核后通过企业微信客服发送；发送成功返回 True，异常返回失败原因。
---

# 微信客服与客户聊天

本 skill 用于生成企业微信客服回复、通知员工审核，并在人工审核通过后向客户发送消息。实际发送属于对外副作用，必须由 `HumanInTheLoopMiddleware` 在 `send_wecom_kf_message` 执行前拦截，未经审核不得发送。

## 所需上下文

直接使用当前上下文中已有的数据：

- 审核员工信息，至少包含企业微信 `user_id`；
- 客户 `external_id`（即客服发送接口 touser，旧称 customer_id）；
- 企业微信客服账号标识 `open_kfid`（由系统上下文注入，通常来自 `OPEN_KFID`）；
- 企业微信客服与客户的近期聊天历史；
- 客户标签；
- 客户画像；
- 客户订单历史。

不要重复查询上下文中已经存在的数据。如果缺少 `user_id`、`external_id`、`open_kfid`、近期聊天历史或生成回复所需的关键客户数据，应停止流程并返回具体失败原因，例如：`"缺少 open_kfid，无法发送企业微信客服消息"`。不要再寻找独立的 `customer_id`。

## 回复生成规则

根据客服与客户近期聊天历史判断客户最新问题、意图、情绪和待处理事项，并结合客户基本信息、标签、画像与订单历史生成一条可直接发送的中文回复。

生成时遵守以下约束：

1. 优先回应客户最新一条消息及其明确问题。
2. 只使用上下文中有依据的信息，不虚构价格、库存、订单状态、物流进度、政策、承诺或处理结果。
3. 可以利用标签、画像和订单历史调整内容，但不得向客户暴露内部标签名、画像字段、系统字段或内部判断过程。
4. 回复应简洁、自然、专业，不包含“AI 建议”“模型分析”“待审核”等内部文字。
5. 生成内容只是待审核草稿，在 middleware 放行前不得描述为已经发送。

## 通知员工

生成草稿后，先调用 `notify_wecom_user`：

```python
notify_wecom_user.invoke({
    "user_id": employee_user_id,
    "content": "客户回复建议待审核：\n" + draft_message,
    "msgtype": "text",
})
```

通知内容应包含客户标识或称呼、完整回复草稿，以及“请在前端审核”的提示。该工具只通知员工，不能用来向客户发送消息。

如果通知发生异常，禁止继续调用发送工具，返回格式为：

```text
通知员工失败：<异常信息>
```

## HumanInTheLoopMiddleware 配置

使用当前项目已安装版本提供的导入路径：

```python
from deepagents import create_deep_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

hitl = HumanInTheLoopMiddleware(
    interrupt_on={
        "send_wecom_kf_message": {
            "allowed_decisions": ["approve", "edit", "reject", "respond"],
            "description": "请审核即将通过企业微信客服发送给客户的消息。",
        }
    }
)

agent = create_deep_agent(
    model=model,
    tools=[notify_wecom_user, send_wecom_kf_message],
    middleware=[hitl],
    checkpointer=checkpointer,
)
```

也可以使用 `create_deep_agent(..., interrupt_on={...})`。当前 DeepAgents 版本会根据该参数自动创建同一个 `HumanInTheLoopMiddleware`。不要同时配置两种方式，否则可能产生重复中断。

必须配置持久化 checkpointer。前端保存 `thread_id`、checkpoint、interrupt、草稿、员工 `user_id`、`external_id` 和 `open_kfid`，恢复审核时继续使用同一个 `thread_id`。

## 前端审核动作

前端展示待发送草稿，并提供 HumanInTheLoopMiddleware 原生的四种决策：

### approve

将操作映射为 middleware 的 `approve` 决策：

```python
Command(resume={"decisions": [{"type": "approve"}]})
```

middleware 放行原始 `send_wecom_kf_message` 调用，然后才实际发送消息。

### reject

将操作映射为 `reject`，并明确说明员工拒绝发送：

```python
Command(resume={
    "decisions": [{
        "type": "reject",
        "message": "员工拒绝发送本条客服消息，请停止本次流程。"
    }]
})
```

发送工具不得执行。返回 `"员工拒绝发送"`，这是正常人工终止，不得描述为接口异常。

### edit

将操作映射为 middleware 的 `edit` 决策。保留工具名和客户标识，只把 `content` 替换成员工修改后的完整非空文本：

```python
Command(resume={
    "decisions": [{
        "type": "edit",
        "edited_action": {
            "name": "send_wecom_kf_message",
            "args": {
                "external_id": external_id,
                "open_kfid": open_kfid,
                "content": edited_message
            }
        }
    }]
})
```

不得允许前端通过编辑审核修改工具名、`external_id` 或 `open_kfid`。服务端恢复执行前应校验这些字段，只允许修改 `content`。

### respond

使用人工回答作为 `send_wecom_kf_message` 的工具调用结果，实际发送工具不执行：

```python
Command(resume={
    "decisions": [{
        "type": "respond",
        "message": "<人工提供的工具调用结果>"
    }]
})
```

`respond` 是合法的审核完成结果，但不代表消息已经发送给客户。

## 审核通过后发送

审核为“同意”或“员工修改后通过”时，middleware 才允许执行：

```python
send_wecom_kf_message.invoke({
    "external_id": external_id,
    "open_kfid": open_kfid,
    "content": approved_message,
})
```

不要在恢复中断前主动调用该工具，也不要因模型再次输出相同内容而绕过审核。每一次新的发送工具调用都必须经过中间件审批。

### 发送窗口硬限制（工具内强制校验）

`send_wecom_kf_message` 在调用企微前会根据 Store 客服历史做硬校验，不依赖 prompt：

1. 必须存在客户主动消息（`origin=3`）；否则拒绝发送。
2. 仅在客户最近一次主动消息后的 **48 小时内**可回复；超时返回 `KF_WINDOW_EXPIRED`。
3. 同一窗口内客服最多发送 **5** 条；达到上限返回 `KF_QUOTA_EXCEEDED`。

窗口/配额失败时工具返回 `success=False` 与 `error`/`error_code`，**不会**调用企微接口。人工审核通过也不能绕过这两条限制。

## 返回格式

消息经人工审核并由 `send_wecom_kf_message` 成功发送后，工具返回形如：

```python
{"success": True, "wecom": {...}, "quota": {...}}
```

对上层 skill 结果，可据此返回：

```python
True
```

若工具返回 `success=False`，或调用抛错，返回可读失败原因，例如：

```text
发送企业微信客服消息失败：距客户上次主动消息已超过 48 小时...
发送企业微信客服消息失败：当前 48 小时窗口内客服已发送 5 条，已达上限...
```

不要把异常或 `success=False` 吞掉后返回 `True`。工具返回的企业微信 `errcode` 非 0、HTTP 请求失败、超时、参数缺失、窗口过期、配额用尽和上下文缺失都属于执行失败，必须返回具体原因。

人工拒绝属于正常终止，返回 `"员工拒绝发送"`。`respond` 使用人工回答作为工具结果，但不能据此宣称客户消息已发送。只有企业微信客服消息已经成功发送，才允许返回 `True`。

## 安全边界

- `notify_wecom_user` 只用于通知审核员工。
- `send_wecom_kf_message` 是唯一允许的客户发送工具。
- 未经人工同意或编辑后通过，不得向客户发送消息。
- 不得在错误重试时绕过 middleware；每次实际发送都需要新的有效审核决定。
- 48 小时窗口与 5 条上限由工具硬校验，审核通过也不能突破。
- 默认只发送一次。发送结果不确定时不要盲目重试，以免客户收到重复消息。
