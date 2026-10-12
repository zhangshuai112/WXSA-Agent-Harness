# 企微销售运营助手 · Agent Harness

面向企业微信场景的销售运营智能体：在侧边栏协助员工生成聊天建议、更新客户标签/画像、创建跟进日程，并通过人工审核（HITL）控制对外写操作。工程核心是自研 **Agent Harness**——编排与编码分离、沙箱隔离、多租户数据访问、工具约束、上下文治理、可观测评估，以及企微数据双通道同步。

---
## 系统架构

```
┌─────────────────┐     ┌──────────────────────────────┐
│  wecom_sidebar  │────▶│  Harness_hand_write           │
│  HITL / 限流    │     │  DeepAgents + YAML + Skills  │
└─────────────────┘     │  Per-user Sandbox + Middleware│
                        └──────────────┬───────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
              OpenSandbox        PostgresStore        Langfuse
              (代码/文件/联网)    (客户业务数据)       (追踪评估)
                                       ▲
                        ┌──────────────┴──────────────┐
                        │  wecom_wxsync（轮询+回调）    │
                        │  wecom_admin / wecom_test     │
                        └─────────────────────────────┘
```

---

## 仓库结构

```
.
├── Harness_hand_write/   # Agent Harness（编排、沙箱、中间件、Skills、Tools）
├── wecom_sidebar/        # 员工侧边栏（FastAPI，默认 :8000）
├── wecom_admin/          # Store 管理后台（Flask，默认 :5000）
├── wecom_wxsync/         # 企微双通道同步（默认 :8880）
└── wecom_test/           # Demo 灌库与写操作 Mock
```

设计细节见 [Harness_hand_write/设计方案.md](Harness_hand_write/设计方案.md)。

---

## 技术栈

- **Harness**：Python 3.10+、LangGraph、DeepAgents、OpenSandbox、PostgresStore
- **侧边栏**：FastAPI、JWT、LangGraph SDK
- **同步 / 管理**：Flask、psycopg、企业微信 / 微信小店 API
- **观测**：自托管 Langfuse、结构化审计 JSONL

---


## 1. 架构设计：编排与编码分离

基于 **DeepAgents + 子 Agent YAML** 实现编排与编码分离，形成可扩展的多 Agent 架构：

| 层级 | 职责 | 落地方式 |
|------|------|----------|
| 主 Agent | 任务拆解、委派、汇总 | `create_deep_agent` + Graph Factory |
| 子 Agent | 单一业务能力 | YAML 声明 name / model / tools / skills / interrupt_on |
| Skills | 可复用执行流程与约束 | 沙箱内 `SKILL.md` + 脚本，由中间件同步 |
| Tools | 原子能力（读 Store / 调企微 / OCR 等） | Python `@tool`，由 YAML `tools:` 白名单挂载 |

新增业务能力时，优先新增 YAML + Skill，而不是改主 Agent 硬编码。当前子 Agent：

| 子 Agent | 作用 |
|----------|------|
| `get-customer-datas-agent` | 按 `follow_user_id` + `external_id` 汇总客户全量上下文 |
| `wx-employee-chat-suggestion-agent` | 按最新聊天渠道路由：员工建议回复 / 客服审核后发送 |
| `update-customer-tags-or-profile-agent` | 生成并审核后全量更新标签或画像 |
| `update-employee-schedule-agent` | 生成日程草案，审核后创建企微日程 |

---

## 2. 安全隔离：OpenSandbox + 中间件

Agent 需要跑 Skills 脚本、读写临时文件、偶发联网装包——这些不能在宿主机上裸跑。本项目把 **代码执行环境** 放进 OpenSandbox，把 **客户业务数据** 放进 PostgreSQL / PostgresStore，两者分离。

### 2.1 沙箱怎么做的

整体链路：

```
请求携带 user_id
  → sandbox_manager 领取/创建/重连该用户沙箱
  → SandboxBackendProxy 包一层稳定句柄
  → OpenSandboxBackend 对接异步 OpenSandbox SDK
  → CompositeBackend：默认路径走沙箱，/memories/ 走 Store
  → Deep Agent / Skills 在沙箱内 execute、读写文件
```

**（1）自定义 `OpenSandboxBackend`**

- 实现 DeepAgents 的 `SandboxBackendProtocol`（`aexecute` / `aupload_files` / `adownload_files` 等）。
- 命令在远端 code-interpreter 容器内执行，不落宿主进程。
- 执行前注入沙箱 PATH（`/opt/skills-venv`、Python/Node 等），非交互 shell 也能找到工具链。
- 超时、stderr 等统一封装成 `ExecuteResponse`，便于中间件识别故障。

**（2）创建与播种（`sandbox_setup`）**

- 镜像：阿里云 OpenSandbox `code-interpreter`；资源约 2 CPU / 4Gi；Python 3.11。
- 新建时挂 **出站网络策略**：默认 `deny`，仅放行 `mirrors.aliyun.com`、`clawhub.ai`、`modelscope.cn` 等（`SANDBOX_NETWORK_POLICY_ENABLED`，默认开）。
- 初始化目录（如 `/analysis/temp`）、创建 `/opt/skills-venv`，预装 `requests` / `beautifulsoup4`（走白名单 pip 源）。
- 首次播种：把本地 `src/skills/**` 与 `AGENTS.md` 上传进沙箱（已存在且内容一致则跳过）。

**（3）稳定句柄 `SandboxBackendProxy`**

- Agent、工具、中间件长期持有 Proxy，不直接持有具体沙箱实例。
- 沙箱重建时只 `replace_backend(新实例)`，外层引用不变，图和工具无需整图重建。

**（4）与数据面分离**

- Skills / shell / 临时文件 → 沙箱。
- 客户标签、画像、聊天、订单 → PostgresStore（宿主侧工具读写）。
- 即使用户沙箱被销毁重建，业务数据仍在库里；长期记忆走 `/memories/` → StoreBackend。

### 2.2 沙箱相关中间件各自干什么

主 Agent 中间件栈里，与沙箱强相关的三件套分工如下（健康恢复优先，同步保证技能新鲜，熔断兜底防死循环）：

| 中间件 | 触发时机 | 做什么 | 不做什么 |
|--------|----------|--------|----------|
| `SandboxHealthMiddleware` | 每个 agent step 前（`abefore_agent`） | `echo ok` ping 当前用户沙箱；失败则 `recreate_user_sandbox`，再经 Proxy 热替换，并重新上传 `AGENTS.md` | 不管 Skills 内容是否更新；不统计错误次数 |
| `SkillsSyncMiddleware` | 每个 agent 周期开始前 | 对比本地 `src/skills/` 与沙箱内文件（MD5）；有变更则上传；若有更新则插入系统通知，提醒 Agent `ls /skills/` | 不负责沙箱宕机恢复 |
| `SandboxCircuitBreakerMiddleware` | 每次调模型前（`before_model`） | 从消息尾部向前数连续「沙箱类」ToolMessage 错误；超过阈值（默认 > 3）则注入熔断说明并 `jump_to=end`，结束本轮 | 不尝试重建沙箱（重建交给 Health） |

协作关系可以记成：

```
Health：能修就修（ping 失败 → 重建）
  ↓ 修不好 / 连续工具报沙箱错
Breaker：别再空转（连续错误超阈值 → 熔断结束）
SkillsSync：环境活着时，保证沙箱里的技能与仓库一致
```

客户业务数据仍由 Store 工具访问，不经过沙箱文件系统，避免把敏感库凭证和执行环境绑死在同一容器里。

---

## 3. 用户隔离：沙箱按人、数据按客户跟进关系

| 维度 | 键 | 说明 |
|------|-----|------|
| 执行环境 | `user_id` | 一人一沙箱；Postgres `agent_runtime.sandbox_registry` 持久映射；支持预热与热替换 Proxy |
| 业务数据 | `follow_user_id` + `external_id` | 读写客户信息、标签、画像、员工侧聊天等均按「跟进员工 + 外部联系人」定位 |
| 客服 / 订单等 | `external_id` / `union_id` | 客服会话按客户；订单按 `union_id`（由客户信息解析） |

`CompositeBackend`：默认路径走用户沙箱；`/memories/` 走 StoreBackend（按 `user_id` 命名空间），沙箱可重建而记忆仍按租户保留。

---

## 4. 工具约束：错误捕捉、限流、审计与 HITL

自定义中间件约束工具与模型行为，并在敏感写路径强制人工介入：

| 机制 | 作用 |
|------|------|
| `ToolErrorMiddleware` | 工具异常转为可恢复 ToolMessage，避免单次失败拖垮整轮 |
| `ModelCallLimitMiddleware` | 单轮模型调用上限（默认 ≤ 50） |
| `ToolCallLimitMiddleware` | 单轮工具调用上限（默认 ≤ 200） |
| `AgentRunLimitTracker` | 侧边栏整轮保险丝：按任务类型限制工具次数与墙钟；HITL 等待时暂停计时 |
| `AuditMiddleware` | 结构化记录 who / what / tool / hitl / tokens / latency |

**HITL 敏感工具**（审核选项：同意 / 拒绝 / 修改后执行 / 人工回复）：

- 改标签：`update_customer_tags`（Store）+ `update_wecom_customer_tags`（企微）
- 改画像：`update_customer_profile`
- 发客服消息：`send_wecom_kf_message`（另含 48h / 5 条窗口硬限制）
- 建日程：`create_wecom_schedule`

---

## 5. 上下文管理：卸载 + 多 Agent 隔离 + Skills

通过多层手段控制上下文膨胀：

1. **工具结果卸载 / 摘要中间件**：接近模型上限时自动压缩；提供 `compact_conversation` 供 Agent 主动压缩（完整历史可落到 backend）。
2. **Multi-Agent 上下文隔离**：子 Agent 只接收主 Agent 放入任务上下文的字段，不直接读主 Agent `RunnableConfig`；各子 Agent 工具白名单独立。
3. **Skills 缩减上下文**：流程、参数依赖、返回格式写在 Skill 中，避免把长流程堆进 system prompt；已有数据禁止重复查询。

---

## 6. 观测评估：审计日志 + 自托管 Langfuse

- **结构化审计中间件 + 分区日志**：落盘 JSONL / 分模块 log，监管每一步行动。
- **自托管 Langfuse**：追踪图执行与关键步骤，支持打分与对照评估，驱动 Agent 持续优化。
- System prompt 可从 Langfuse（如 `main/system@production`）拉取，失败回退本地 `prompt.py`。

---

## 7. 企微数据与本地同步：轮询 + 回调双通道

`wecom_wxsync` 采用 **定时轮询 + 事件回调** 双通道，将客户标签、聊天消息与订单等增量写入本地 PostgresStore，供 Agent 统一读取，避免运行时直打企微拉全量。

详情见 [wecom_wxsync/docs/data_model.md](wecom_wxsync/docs/data_model.md)。

---

## Skills 说明

Skills 在沙箱内执行，描述「怎么做」；由对应子 Agent YAML 挂载。

| Skill | 所属子 Agent | 作用 |
|-------|--------------|------|
| `get-customer-datas-skill` | get-customer-datas | 按固定顺序拉取客户信息、订单、标签、画像、员工/客服聊天、全局标签库，返回统一 JSON |
| `employee-chat-suggestion-skill` | wx-employee-chat-suggestion | 基于员工侧聊天与客户数据生成回复建议，HITL 审核后输出建议（不直发客户） |
| `kf-chat-skill` | wx-employee-chat-suggestion | 基于客服侧聊天生成回复，HITL 通过后调用客服发送工具 |
| `update-customer-tags-skill` | update-customer-tags-or-profile | 生成完整标签列表，审核后全量写 Store 并差量同步企微 |
| `update-customer-profile-skill` | update-customer-tags-or-profile | 生成完整画像，审核后全量写 Store（不同步企微画像） |
| `create-employee-schedule-skill` | update-employee-schedule | 生成日程草案，审核后创建企业微信日程 |
| `skill-management` | 主 Agent | 在沙箱内下载/创建/验证/分配技能，管理 Skills 生命周期 |

---

## Tools 说明

### Store 工具（本地 PostgresStore）

| 工具 | 作用 | 访问键 |
|------|------|--------|
| `get_employee_info` | 查员工 user_id / 姓名 | `user_id` |
| `get_customer_info` | 查客户基本信息与 union_id | `external_id` + `follow_user_id` |
| `get_customer_tags` | 查客户标签 | 同上 |
| `get_customer_profile` | 查客户画像 | 同上 |
| `get_chat_history` | 员工与客户近期聊天 | 同上 |
| `get_kf_history` | 企微客服与客户聊天 | `external_id` |
| `get_order_history` | 微信小店订单历史 | `union_id` |
| `get_tag_setting` | 公司全局标签库 | — |
| `update_customer_tags` | 全量覆盖更新客户标签（HITL） | `external_id` + `follow_user_id` |
| `update_customer_profile` | 全量覆盖更新客户画像（HITL） | 同上 |

### 企微工具（写操作 / 通知）

| 工具 | 作用 | HITL |
|------|------|------|
| `notify_wecom_user` | 向指定员工发审核/操作通知 | 否 |
| `update_wecom_customer_tags` | 将标签差量同步到企业微信 | 配合标签流程 |
| `send_wecom_kf_message` | 以客服身份向客户发消息（含发送窗口硬限制） | 是 |
| `create_wecom_schedule` | 为员工创建企业微信日程 | 是 |

### 沙箱与其它工具

| 工具 | 作用 |
|------|------|
| `assign_skill` | 将技能分配到指定子 Agent 沙箱域 |
| `download_sandbox_file` | 从沙箱下载文件到本地目录 |
| `web_search` | 联网检索补充公开信息 |
| `paddleocr_multimodal_extract` | 从图片/PDF 提取文本与版面信息 |
| `compact_conversation` | 主动压缩对话上下文（摘要中间件提供） |

---



## 快速开始（本地 Demo）

环境：Python 3.10+、PostgreSQL（共用 `DATABASE_URI`）。可选 OpenSandbox、Langfuse。各目录复制 `.env.example` → `.env`。

```bash
# 1) Agent Harness
cd Harness_hand_write && cp .env.example .env && pip install -e .
# 配置 DATABASE_URI、LLM Key；沙箱：OPENSANDBOX_URL、OPEN_SANDBOX_API_KEY

# 2) Demo 数据
cd ../wecom_test && cp .env.example .env && pip install -r requirements.txt
python scripts/seed.py --clear
python scripts/verify.py --use-store-client
# 将 EXTERNAL_ID 写入 wecom_sidebar/.env

# 3) 启动 Agent
cd ../Harness_hand_write && langgraph dev   # :2024

# 4) 启动侧边栏
cd ../wecom_sidebar && cp .env.example .env && pip install -r requirements.txt
python wecom_sidebar_app.py                # :8000
```

可选：

```bash
cd wecom_admin && python wecom_admin_app.py           # :5000
cd wecom_test && python scripts/test_mock_wx.py       # Mock 企微写接口
cd wecom_wxsync && python wechat_notify/run_wx_notify.py  # 生产同步/回调
```

### 配置摘要

| 项 | 用途 |
|----|------|
| `DATABASE_URI` | PostgresStore / 沙箱注册表 |
| `OPENSANDBOX_*` / `SANDBOX_PRE_WARM` / `SANDBOX_NETWORK_POLICY_ENABLED` | 沙箱 |
| `AGENT_RUN_LIMITS_*` | 整轮工具次数与墙钟 |
| `LANGFUSE_*` | 自托管追踪与评估 |
| `AUDIT_LOG_*` | 结构化审计 |
| `wecom_wxsync/.env` | 企微密钥、回调、会话存档 |

**请勿提交含真实密钥的 `.env`、私钥或 SDK 动态库。**

| 服务 | 端口 |
|------|------|
| LangGraph | 2024 |
| wecom_sidebar | 8000 |
| wecom_admin | 5000 |
| wecom_wxsync | 8880 |

---

## 许可证

若未另行声明，以各子模块约定为准。
