---
name: update-customer-tags-skill
description: 根据上下文中的客户近期聊天记录、客户资料和公司全局标签库生成客户标签，通知指定员工进行人工审核，审核通过后先全量覆盖更新 Store，再调用 update_wecom_customer_tags 同步到企业微信。
---

# 客户标签更新

## 目标

本 skill 负责为一个企业微信客户生成并更新标签。客户近期聊天历史（客服与员工）、客户基本信息、已有客户标签、客户画像以及公司全局可选标签库都已经放在当前 agent 上下文中时，直接使用这些上下文生成候选标签；不要重复查询已经提供的数据。标签更新采用全量覆盖语义：审核通过后，`update_customer_tags` 的 `tag_ids` 必须是审核后的完整标签 ID 列表，而不是增量列表。Store 写入成功后，再调用 `update_wecom_customer_tags` 把差量同步到企业微信。

最终返回值只能是：

- `True`：人工同意候选标签，或员工修改后通过，且 Store 与企业微信均更新成功（或无需同步企微）。
- 失败原因字符串：流程异常、人工拒绝或更新工具返回失败时，返回简短、可诊断的原因（不要吞掉异常）。

除成功外不要返回 `True`，也不要把候选标签或审核详情作为最终结果。

## 必要上下文

执行前确认上下文至少包含：

- 客户 `external_id`、姓名/可用称呼等基本信息；
- 负责员工 `follow_user_id`（也是发送审核通知的企业微信 `user_id`）；
- 客服与员工同客户的近期聊天历史；
- 当前客户标签和客户画像；
- 公司全局标签库，至少能映射每个可选标签的 `tag_id` 与 `tag_name`。

缺少 `external_id`、`follow_user_id`、聊天历史、客户数据或可选标签库时，不得猜测或编造标签，直接返回具体失败原因。允许历史记录为空，但必须能明确判断为空而不是查询异常。

## 生成候选标签

从上下文提取客户的稳定事实、近期需求、意向、阶段、偏好和服务风险，仅从公司全局标签库中选择标签。输出内部候选对象，格式如下：

```json
{
  "external_id": "客户 external_id",
  "follow_user_id": "负责员工 user_id",
  "customer_name": "客户名称",
  "tag_ids": ["可选标签库中的 tag_id"],
  "tag_names": ["对应的标签名称"],
  "reasoning": "基于聊天和客户资料的简短依据"
}
```

要求：

1. `tag_ids` 去重、保持稳定顺序，并且每个 ID 都必须存在于全局标签库。
2. 不要把自由文本、推测、临时状态或不存在于标签库的名称写入 `tag_ids`。
3. 生成失败或无法得到合法标签时抛出/返回异常原因，不调用通知和更新工具。

## 申请人工审核

候选标签生成后，必须调用 `notify_wecom_user`，向 `follow_user_id` 发送审核通知。通知应包含客户标识、候选标签名称/ID、生成依据摘要，以及前端待选择的审核动作；通知是给员工的审核提醒，不是发给客户的消息。

通知调用失败视为流程失败：返回异常原因，并停止后续审核与更新。

## HumanInTheLoopMiddleware

使用项目当前安装版本提供的 `HumanInTheLoopMiddleware`，不要自行实现另一套中断机制。把“提交客户标签更新”作为必须人工确认的工具调用，并只使用四种原生决策：

- `approve`：同意当前调用并执行标签更新工具；
- `reject`：拒绝当前调用，标签更新工具不执行；
- `edit`：人工编辑完整标签参数后执行标签更新工具；
- `respond`：标签更新工具不执行，直接使用人工回答作为工具调用结果。

中断数据必须包含并持久化 `thread_id`/checkpoint、`external_id`、`follow_user_id`、候选 `tag_ids`/`tag_names`、通知状态和审核状态。前端显示中断后，必须使用同一 thread/checkpoint 通过 `Command(resume=...)` 恢复，不能新建线程。

恢复处理规则：

1. `approve` 使用当前候选 `tag_ids`；
2. `reject` 立即返回“员工拒绝更新客户标签”，不得调用 `update_customer_tags`；
3. `edit` 必须校验员工修改后的完整标签 ID 列表（允许明确的空列表表示清空全部标签），所有 ID 均在全局标签库中，然后执行修改后的调用；
4. `respond` 使用人工回答作为工具结果，不执行 `update_customer_tags`。

任何审核动作缺失、非法或编辑内容无法校验，都视为异常并返回失败原因；不能绕过人工中断。

## 审核通过后写入 Store，再同步企业微信

仅当 `approve` 或合法的 `edit` 成功恢复后，先调用：

```text
update_customer_tags(
    external_id=external_id,
    follow_user_id=follow_user_id,
    tag_ids=approved_tag_ids,
)
```

这里的 `approved_tag_ids` 必须是完整覆盖后的列表。`update_customer_tags` 只写 Store，不要改这个工具的行为。

`update_customer_tags` 返回 `True` 后，根据审核前上下文中的当前标签与 `approved_tag_ids` 计算差量，再调用：

```text
update_wecom_customer_tags(
    user_id=follow_user_id,
    external_id=external_id,
    tag_ids_add=[最终有、当前没有的 tag_id],
    tag_ids_remove=[当前有、最终没有的 tag_id],
)
```

若 `tag_ids_add` 与 `tag_ids_remove` 均为空，可跳过企微同步。`update_wecom_customer_tags` 不需要人工中断。Store 成功但企微失败时，返回明确失败原因并说明 Store 已写入。不要在审核通过后自动发送客户消息。

## 异常与返回

将工具异常、参数校验错误、通知失败、标签 ID 非法、checkpoint 恢复失败、Store 写入失败和企业微信同步失败转换为简短失败原因并返回。成功只返回 `True`；拒绝、未完成再次审核或其他非成功结果也必须返回原因字符串。
