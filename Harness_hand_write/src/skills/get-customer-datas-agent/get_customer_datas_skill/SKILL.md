---
name: get-customer-datas-skill
description: 根据企业微信客户 external_id 和员工 follow_user_id，汇总客户订单、标签、画像、聊天记录以及公司全局标签库，并返回统一 JSON 字典。
---

# 客户数据获取技能

## 用途

当需要全面了解一个企业微信客户时，使用本技能调用 Store 查询工具，汇总客户的基础关联信息、订单历史、客户标签、客户画像、员工与客户聊天记录、企业微信客服聊天历史以及公司全局标签库。

## 输入

必须获取以下两个参数：

- `external_id`：客户的企业微信外部联系人 ID。
- `follow_user_id`：负责跟进该客户的企业微信员工 user_id。

如果缺少任一参数，不得调用查询工具，应先向用户请求缺失参数。

## 工具调用流程

### 1. 获取客户基础信息和 union_id

调用：

```text
get_customer_info(
    external_id=external_id,
    follow_user_id=follow_user_id
)
```

从返回的客户信息中提取 `union_id`。

如果客户信息查询失败或没有返回 `union_id`：

- 仍然继续调用客户标签、客户画像、聊天记录、客服聊天记录和全局标签库工具。
- 不调用 `get_order_history`，因为订单查询必须使用有效的 `union_id`。
- 将 `order_history` 设置为空字符串 `""`。

### 2. 获取订单历史

仅当 `union_id` 有效时调用：

```text
get_order_history(union_id=union_id)
```

将返回结果保存到 `order_history`。

### 3. 获取客户标签

调用：

```text
get_customer_tags(
    external_id=external_id,
    follow_user_id=follow_user_id
)
```

将返回结果保存到 `customer_tags`。

### 4. 获取客户画像

调用：

```text
get_customer_profile(
    external_id=external_id,
    follow_user_id=follow_user_id
)
```

将返回结果保存到 `customer_profile`。

### 5. 获取员工与客户聊天记录

调用：

```text
get_chat_history(
    external_id=external_id,
    follow_user_id=follow_user_id
)
```

将返回结果保存到 `chat_history`。

### 6. 获取企业微信客服与客户聊天记录

调用：

```text
get_kf_history(external_id=external_id)
```

将返回结果保存到 `kf_history`。

### 7. 获取公司全局标签库

调用：

```text
get_tag_setting()
```

将返回结果保存到 `tag_setting`。

## 调用要求

- 查询工具应尽量连续完成，不要在中间向用户输出未汇总的中间结果。
- `get_order_history` 必须使用 `get_customer_info` 返回的 `union_id`，不能使用 `external_id` 代替。
- 每个工具调用失败时，记录对应字段为空字符串 `""`，继续执行其他不依赖该字段的查询。
- 不要修改、补造或推测客户的订单、标签、画像和聊天记录。
- 本技能只负责查询和汇总，不调用任何写入、更新、删除或通知工具。

## 返回格式

最终只返回一个 JSON 字典，不要添加 Markdown 代码块、解释性文字或额外字段：

```json
{
  "order_history": "",
  "customer_tags": "",
  "customer_profile": "",
  "chat_history": "",
  "kf_history": "",
  "tag_setting": ""
}
```

每个字段的值应填入对应工具的原始返回结果。如果某项查询失败、没有数据或因缺少依赖无法执行，则该字段使用空字符串 `""`。

## 字段说明

| 字段 | 来源工具 | 说明 |
| --- | --- | --- |
| `order_history` | `get_order_history` | 客户订单历史；依赖 `union_id` |
| `customer_tags` | `get_customer_tags` | 客户当前标签 |
| `customer_profile` | `get_customer_profile` | 项目 Store 中保存的客户画像 |
| `chat_history` | `get_chat_history` | 员工与客户的近期聊天记录 |
| `kf_history` | `get_kf_history` | 企业微信客服与客户的聊天历史 |
| `tag_setting` | `get_tag_setting` | 公司全局标签库 |
