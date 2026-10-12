# wecom_test — 企业微信场景本地模拟

在**不依赖真实企业微信账号**的情况下，为 `Harness_hand_write` Agent 灌入 Demo 数据并 Mock 写操作。

## 场景说明

默认 Demo：**员工程建章**跟进客户**张总（张建国）**，筹备儿子婚礼酒席用酒：

- 员工 / 客户 / 标签 / 画像
- 企微单聊历史（含「明天上午10点到店商量酒席」）
- 客服会话记录
- 微信小商店历史订单

## 前置条件

1. Postgres 已启动，且 `Harness_hand_write/.env` 中 `DATABASE_URI` 可用
2. 使用 conda 环境 `Harness`：

```powershell
conda activate Harness
cd D:\Harness_hand_write\wecom_test
pip install -r requirements.txt
```

## 1. 灌库

```powershell
python scripts/seed.py --clear
```

输出中的 `EXTERNAL_ID` 需与 `wecom_sidebar/.env` 的 `EXTERNAL_ID` 一致。

## 2. 验证 Store

```powershell
python scripts/verify.py --use-store-client
```

## 3. Mock 企业微信写操作

Agent 的 `wx_tools` 默认会调真实企业微信 API。本地测试可先 Mock：

```powershell
python scripts/test_mock_wx.py
```

或在启动 Agent 前于代码中调用：

```python
from mock.wecom_api import enable_mock_wecom
enable_mock_wecom()
```

Mock 会记录 `notify_user` / `create_schedule` / `update_customer_tag` / `send_kf_message` 调用，标签更新还会同步到 PostgresStore。

## 4. 联调 Agent + Sidebar

**终端 A — LangGraph**

```powershell
cd D:\Harness_hand_write\Harness_hand_write
langgraph dev
```

**终端 B — Sidebar**

```powershell
cd D:\Harness_hand_write\wecom_sidebar
# .env: LANGGRAPH_SERVER_URL=http://127.0.0.1:2024
#       EXTERNAL_ID=wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg
python wecom_sidebar_app.py
```

浏览器打开 `http://127.0.0.1:8000`，选择菜单或直接对话。Agent 会从 Store 读到张总的聊天记录、画像和订单。

## 目录结构

```
wecom_test/
  scenario/demo_data.py   # 场景 fixture
  seed_store/seeder.py       # 写入 PostgresStore
  mock/wecom_api.py       # Mock WxWorkAPI
  scripts/
    seed.py               # 灌库
    verify.py             # 验证读取
    test_mock_wx.py       # wx_tools Mock 冒烟
```

## 自定义场景

编辑 `scenario/demo_data.py` 或在 `seed.py` 传入：

```powershell
python scripts/seed.py --employee-user-id ChengJianZhang --external-id YOUR_EXTERNAL_ID --clear
```

## 与 wecom_admin 的关系

灌库后可用 `wecom_admin`（端口 5000）在 Web 界面查看 / 编辑 Store 中的客户、标签、聊天记录等。
