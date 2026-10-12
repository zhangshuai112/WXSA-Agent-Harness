# 企微销售运营助手 Agent Harness

面向企业微信场景的销售运营智能体系统：在侧边栏中协助员工生成聊天建议、更新客户标签/画像、创建跟进日程，并通过人工审核（HITL）控制对外写操作。

## 功能概览

| 能力 | 说明 |
|------|------|
| 客户上下文聚合 | 拉取客户基本信息、标签、画像、订单、员工单聊与客服会话 |
| 聊天建议 | 按最新会话渠道路由：员工侧建议回复，或客服侧生成回复并审核后发送 |
| 标签 / 画像更新 | 基于聊天与订单生成完整标签或画像，审核后写入 Store（标签同步企微） |
| 日程创建 | 从客户上下文提炼待办，审核后创建企业微信日程 |
| 人机协同 | 关键写操作支持同意 / 拒绝 / 修改后执行 / 人工回复 |

## 系统架构

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  wecom_sidebar  │────▶│ Harness_hand_write│────▶│  PostgresStore      │
│  (员工侧边栏)    │     │  (LangGraph Agent) │     │  (客户/聊天/订单等)  │
└─────────────────┘     └────────┬─────────┘     └──────────▲──────────┘
                                 │                          │
                                 ▼                          │
                        OpenSandbox / Tools          ┌──────┴──────┐
                        企微 API / 多模态 OCR         │ wecom_wxsync │
                                                     │ (同步+回调)   │
                                                     └─────────────┘
┌─────────────────┐     ┌──────────────────┐
│  wecom_admin    │────▶│   同一 Postgres   │
│  (数据管理后台)  │     └──────────────────┘
└─────────────────┘

本地联调可不接真实企微：使用 wecom_test 灌库 + Mock 写操作
```

## 仓库结构

```
.
├── Harness_hand_write/   # 核心 Agent（LangGraph / deep agent、Skills、中间件）
├── wecom_sidebar/        # 员工侧边栏 Web（FastAPI + 前端，默认 :8000）
├── wecom_admin/          # Store 管理后台（Flask，默认 :5000）
├── wecom_wxsync/         # 企微 / 微信小店同步与事件回调（默认 :8880）
└── wecom_test/           # 本地 Demo 灌库与企微写操作 Mock
```

### 各模块职责

- **Harness_hand_write**  
  主智能体协调多个子 Agent：`get-customer-datas`、`wx-employee-chat-suggestion`、`update-customer-tags-or-profile`、`update-employee-schedule`。支持沙箱执行 Skills、Langfuse 追踪、审计日志与运行时长/工具次数限制。

- **wecom_sidebar**  
  登录后与 LangGraph Server 流式对话，展示 HITL 审核面板，注入 `external_id` / `follow_user_id` 等运行时上下文。

- **wecom_admin**  
  查看与编辑 Store 中的员工、客户、标签、画像、聊天记录、订单等。

- **wecom_wxsync**  
  会话存档、客户联系变更、客服消息、微信小店等同步进 PostgresStore，并处理企微回调通知。

- **wecom_test**  
  不依赖真实企微账号即可灌入 Demo 场景并 Mock `notify` / `schedule` / `tag` / `kf_message` 等写接口。详见 [wecom_test/README.md](wecom_test/README.md)。

## 技术栈

- **Agent**：Python 3.10+、LangGraph、deepagents、PostgresStore、OpenSandbox  
- **侧边栏**：FastAPI、uvicorn、JWT、LangGraph SDK  
- **管理后台 / 同步**：Flask、psycopg、企业微信 / 微信小店 API  
- **观测**：Langfuse（可选）、结构化审计 JSONL  

## 环境要求

- Python 3.10+
- PostgreSQL（与 Agent / Admin / wxsync 共用同一 `DATABASE_URI`）
- （可选）OpenSandbox，用于 Skills 沙箱执行
- （可选）Langfuse，用于 Agent 追踪
- 生产环境需配置企业微信自建应用、会话存档、客服与微信小店等相关密钥

建议使用独立 conda / venv（示例环境名 `Harness`）。

## 快速开始（本地 Demo）

以下路径以仓库根目录为准。先准备 Postgres，并配置各模块 `.env`（可参考各目录下的 `.env.example`）。

### 1. 配置 Agent

```bash
cd Harness_hand_write
cp .env.example .env
# 至少配置 DATABASE_URI，以及所用 LLM 的 API Key（如 DASHSCOPE_* / DEEPSEEK_*）
# 可选：LANGFUSE_*、OPENSANDBOX_* 等
pip install -e .
# 开发调试还可安装：langgraph-cli[inmem] 等（见 pyproject.toml dependency-groups）
```

### 2. 灌入 Demo 数据

```bash
cd wecom_test
cp .env.example .env   # DATABASE_URI 与 Agent 一致
pip install -r requirements.txt
python scripts/seed.py --clear
python scripts/verify.py --use-store-client
```

将 seed 输出的 `EXTERNAL_ID` 写入 `wecom_sidebar/.env`。

### 3. 启动 LangGraph Agent

```bash
cd Harness_hand_write
langgraph dev
# 默认 http://127.0.0.1:2024 ，graph id: agent
```

### 4. 启动侧边栏

```bash
cd wecom_sidebar
cp .env.example .env
# LANGGRAPH_SERVER_URL=http://127.0.0.1:2024
# EXTERNAL_ID=<与 seed 一致>
# WEB_USER_ID / WEB_PASSWORD / JWT_SECRET_KEY 按需修改
pip install -r requirements.txt
python wecom_sidebar_app.py
```

浏览器打开 `http://127.0.0.1:8000`，登录后即可与 Agent 对话。

### 5.（可选）管理后台

```bash
cd wecom_admin
cp .env.example .env   # DATABASE_URI 可留空以回退读取 ../Harness_hand_write/.env
pip install -r requirements.txt
python wecom_admin_app.py
# http://127.0.0.1:5000
```

### 6.（可选）Mock 企微写操作

避免本地误调真实企微 API：

```bash
cd wecom_test
python scripts/test_mock_wx.py
```

或在启动 Agent 前调用：

```python
from mock.wecom_api import enable_mock_wecom
enable_mock_wecom()
```

## 生产相关：数据同步与回调

对接真实企业微信时，配置并启动 `wecom_wxsync`：

```bash
cd wecom_wxsync
cp .env.example .env
# 填写 CORP_ID、应用 Secret、会话存档密钥、回调 Token、DATABASE_URI 等
pip install -r requirements.txt
python wechat_notify/run_wx_notify.py
```

数据模型说明见 [wecom_wxsync/docs/data_model.md](wecom_wxsync/docs/data_model.md)。  
Agent 设计细节见 [Harness_hand_write/设计方案.md](Harness_hand_write/设计方案.md)。

## 配置说明（摘要）

| 变量 / 文件 | 用途 |
|-------------|------|
| `DATABASE_URI` | 共用 PostgresStore 连接串 |
| `Harness_hand_write/.env` | LLM、沙箱、Langfuse、审计、运行限制 |
| `wecom_sidebar/.env` | LangGraph 地址、演示客户 `EXTERNAL_ID`、Web 登录与 JWT |
| `wecom_admin/.env` | 管理后台账号与 `DATABASE_URI` |
| `wecom_wxsync/.env` | 企微 / 小店密钥、回调、会话存档、通知 |

**请勿将含真实密钥的 `.env`、私钥、SDK 动态库提交到 Git。** 仓库中应只保留 `.env.example`。

## 默认端口

| 服务 | 端口 |
|------|------|
| LangGraph (`langgraph dev`) | 2024 |
| wecom_sidebar | 8000 |
| wecom_admin | 5000 |
| wecom_wxsync 回调 | 8880（可由 `FLASK_PORT` 覆盖） |

## 许可证

若未另行声明，以各子模块 `pyproject.toml` / 文件头约定为准；上传 GitHub 前请按团队要求补充根目录 LICENSE。
