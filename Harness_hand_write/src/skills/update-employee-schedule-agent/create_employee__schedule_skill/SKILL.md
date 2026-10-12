---
name: create-employee-schedule-skill
description: 根据上下文中的员工与客户近期聊天历史、客户标签、客户画像和基本信息生成员工日程草案，通知员工进行人工审核，并在审核通过后调用 create_wecom_schedule 创建企业微信日程；成功返回 True，异常返回具体失败原因。
---

# 生成员工日程并推送

本 skill 负责为指定员工生成可执行的企业微信日程。日程草案只能使用当前上下文已经提供的资料，不得臆造客户需求、时间、地点或承诺。流程必须严格按“生成草案 -> 通知员工 -> 人工审核 -> 创建日程”执行。

## 必需上下文

从上下文读取以下信息，不要为了补齐信息而重复查询或虚构数据：

- 员工企业微信 `user_id`（也是审核通知和创建日程的目标员工）。
- 客户基本信息（至少客户标识或可用称呼）。
- 员工与客户的近期聊天历史，必要时使用上下文中的客服与客户聊天历史。
- 客户标签和客户画像。

若缺少员工 `user_id`、聊天历史、客户标识或无法据此确定待办事项，直接返回 `日程生成失败：上下文缺少<字段>`，不得进入通知和审核流程。

## 生成日程草案

根据最近的明确待办、客户意向、约定时间和跟进优先级生成一个或多个日程。仅采用有证据的时间；没有明确时间时，使用当前业务约定的默认时间或请求人工补充，不能猜测具体日期。每个日程至少包含：

```json
{
  "title": "简短、可执行的跟进标题",
  "start_time": "YYYY-MM-DD HH:MM:SS",
  "duration_minutes": 30,
  "reason": "来自聊天或客户资料的依据"
}
```

`title` 不得泄露内部标签字段，`start_time` 必须符合 `create_wecom_schedule` 的格式，`duration_minutes` 必须为正整数。内部保存审核状态，例如：

```json
{
  "status": "pending_review",
  "employee_id": "员工 user_id",
  "customer_id": "客户标识",
  "draft_schedules": [],
  "final_schedules": [],
  "review_action": "",
  "review_comment": ""
}
```

## 通知员工

草案生成后，必须调用 `notify_wecom_user`：

```python
notify_wecom_user.invoke({
    "user_id": employee_user_id,
    "content": "员工日程待审核\n" + format_schedule_draft(draft_schedules) +
            "\n请在前端选择：approve、reject、edit 或 respond。",
    "msgtype": "text",
})
```

通知内容应包含客户标识、完整草案、时间和审核入口提示。该工具只用于通知员工，不能当作客户消息发送工具。通知抛出异常或返回非真值时，立即返回 `日程通知失败：<异常信息>`，不得创建日程。

## HumanInTheLoopMiddleware 审核

必须使用项目实际可导入的 `HumanInTheLoopMiddleware`（通常为 `langchain.agents.middleware`）在创建日程工具执行前中断，并配置 `create_wecom_schedule` 的审核。使用同一个 LangGraph `thread_id` 和 checkpoint 恢复，不能为每个选择重新创建线程。

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware

hitl = HumanInTheLoopMiddleware(
    interrupt_on={
        "create_wecom_schedule": {
            "allowed_decisions": ["approve", "edit", "reject", "respond"],
            "description": "请审核即将创建的员工企业微信日程。",
        }
    }
)
```

前端必须展示 HumanInTheLoopMiddleware 原生的四种决策：`approve`、`reject`、`edit`、`respond`。前端保存 interrupt、thread/checkpoint、员工标识、客户标识和草案；用户操作后通过同一 checkpoint 发送 `Command(resume=...)`。

### 审核动作

- **approve**：同意当前调用，使用原草案参数执行 `create_wecom_schedule`。
- **reject**：拒绝当前调用，不执行创建工具，返回人工拒绝结果。
- **edit**：人工提交完整、合法的修改后日程参数，然后执行创建工具。必须校验工具名仍为 `create_wecom_schedule`、`user_id` 与原员工一致、时间格式正确且时长为正数，禁止以局部 patch 绕过审核。
- **respond**：不执行创建工具，直接使用人工回答作为该工具的调用结果。

审核拒绝、人工直接回答或审核参数非法均不得调用 `create_wecom_schedule`。

## 创建日程

只有 `approve` 或合法的 `edit` 恢复后，才调用一次或按草案逐项调用 `create_wecom_schedule`：

```python
create_wecom_schedule.invoke({
    "user_id": employee_user_id,
    "title": schedule["title"],
    "start_time": schedule["start_time"],
    "duration_minutes": schedule["duration_minutes"],
})
```

任何一次创建调用抛出异常或返回非真值，都返回 `日程创建失败：<异常信息>`；不要把部分成功伪装成整体成功。全部日程创建成功后，内部状态置为 `created`。

## 输出契约

最终只返回以下两类结果：

- 全部日程已通过人工审核且 `create_wecom_schedule` 成功：返回 Python 布尔值 `True`。
- 任意异常、上下文缺失、通知失败、员工拒绝或审核参数非法：返回包含阶段和原因的字符串，例如 `日程审核失败：员工拒绝创建日程`。

不得返回草案、审核详情或“已发送”文字代替上述结果；`True` 仅表示企业微信日程已成功创建，不表示客户已收到消息。

## 工具边界

- 必须调用 `notify_wecom_user` 申请人工审核。
- 必须通过 `HumanInTheLoopMiddleware` 拦截 `create_wecom_schedule`。
- 必须在审核通过后调用 `create_wecom_schedule`。
- 不调用 `send_wecom_kf_message`，不向客户发送消息。
- 不在审核前创建、更新或删除任何日程。
