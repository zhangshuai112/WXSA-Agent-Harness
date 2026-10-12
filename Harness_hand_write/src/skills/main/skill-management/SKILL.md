---
name: skill-management
description: 用于管理技能的完整生命周期：从 URL 下载技能 ZIP 包并解压、根据需求创建新技能、沙箱内测试验证、分配给指定子 Agent。当用户要下载、创建、安装、分配技能时激活。
---

# 技能管理

你负责管理技能的完整生命周期。所有操作在沙箱内执行（安全隔离）。当前设计不把技能写入 PostgreSQL Store；跨会话保留依赖本地 `src/skills/` 同步与沙箱内已分配副本。

## 技能架构

```
/skills/{scope}/     ← 沙箱内技能根目录（scope = Agent 对应的技能域）
  └── {技能名}/       ← SkillsSyncMiddleware 从本地同步，或 assign_skill 从 /skills/main/ 复制
```

### Scope 映射表

| 子 Agent / Agent | scope | 技能路径 |
|------------------|-------|----------|
| `main` | `main` | `/skills/main/` |
| `get-customer-datas-agent` | `get-customer-datas-agent` | `/skills/get-customer-datas-agent/` |
| `wx_employee_chat_suggestion-agent` | `wx_employee_chat_suggestion-agent` | `/skills/wx_employee_chat_suggestion-agent/` |
| `update-customer-tags-or-profile-agent` | `update-customer-tags-or-profile-agent` | `/skills/update-customer-tags-or-profile-agent/` |
| `update-employee-schedule-agent` | `update-employee-schedule-agent` | `/skills/update-employee-schedule-agent/` |

> 所有技能在 scope 下平级存放。
> 子 Agent 通过渐进式披露自动发现所属 scope 下的技能，无需手动激活。
> `assign_skill` 的 `agent_name` 必须与上表第一列完全一致。

## 工作流

### 阶段 1 — 下载并解压（沙箱内，`/skills/main/`）

用户提供技能 ZIP 下载 URL。**仅允许**：

- `https://clawhub.ai/...`
- `https://www.modelscope.cn/skills/...`

一条命令完成下载 + 解压 + 结构校验：
```
execute("python /skills/main/skill-management/scripts/download_skill.py '{url}'")
```

脚本自动完成：
- 校验 URL 白名单（非允许来源直接失败）
- 从 URL 的 `slug` 参数或路径末段提取技能名
- `urllib` 下载 ZIP 到 `/skills/main/{name}.zip`
- `zipfile` 解压到 `/skills/main/{name}/`
- 校验：`SKILL.md` 存在性 + frontmatter（name、description）
- 清理 zip 包
- 输出 JSON：`{success, skill_name, path, files[], errors[]}`

> `success=false` → 根据 errors 信息修复，必要时重新下载。
> `success=true` → 进入阶段 2。

### 阶段 2 — 创建模式（用户描述需求，无 URL）

当用户直接描述需求而不是提供 URL 时：
1. 根据用户需求生成 SKILL.md，包含 frontmatter（name、description）和步骤说明
2. `write_file("/skills/main/{name}/SKILL.md", content)`
3. 如有附属 .py 脚本，一并写入同目录

### 阶段 3 — 功能测试（沙箱内）

在 `/skills/main/{name}/` 下进行：
```
① 阅读 SKILL.md 中的使用说明，确认入口和参数
② 如有 .py 脚本依赖第三方库，使用 pip 安装（阿里云镜像加速）：
   execute("pip install -i https://mirrors.aliyun.com/pypi/simple/ <package_name>")
   pip/python 已通过 PATH 注入自动路由到 /opt/skills-venv/bin/，无需绝对路径。
   常见依赖（numpy/pandas/matplotlib/requests/beautifulsoup4）已在沙箱初始化时预装到 venv
③ execute("python -m py_compile /skills/main/{name}/*.py") 检查语法
④ execute("cd /skills/main/{name} && python script.py --help") 确认可执行
⑤ 纯指引型技能（无脚本）: 跳过执行测试，仅验证 SKILL.md 步骤完整性
⑥ 失败 → 修复 → 重测，直到全部通过
```

### 阶段 4 — 分配

测试全部通过后：
```
① 调用 assign_skill(skill_name="{name}", agent_name="{Agent名}")
   → 工具自动将 /skills/main/{name}/ 复制到 /skills/{scope}/{name}/
   → 目标为 main 时技能已在 /skills/main/，无需复制
   → 子 Agent 下一轮对话即可通过渐进式披露发现新技能

② 清理工作区副本（可选，分配给非 main 后）：
   execute("rm -rf /skills/main/{name}")
```

> scope 由用户指定的目标 Agent 决定（查 Scope 映射表）。如用户未指定，先提醒再执行。
> 当前不将技能写入 Store；若需跨进程长期保留，应同步回本地 `src/skills/{scope}/` 源码目录。

### 阶段 5 — 未指定 Agent 时的提醒

```
用户未指定目标 → 提醒: "技能 '{name}' 已通过测试！请指定分配给哪个 Agent？
             可用: main（主 Agent）,
                   get-customer-datas-agent（获取客户数据）,
                   wx_employee_chat_suggestion-agent（员工/客服聊天建议）,
                   update-customer-tags-or-profile-agent（客户标签或画像）,
                   update-employee-schedule-agent（员工日程）"
           → 等待用户回复后 → 执行阶段 4
```

## 可用工具

- `execute("python /skills/main/skill-management/scripts/download_skill.py '{url}'")`: 仅允许 ClawHub / ModelScope Skills URL；下载 ZIP + 解压 + 结构校验，一步完成。输出 JSON。
- `assign_skill(skill_name, agent_name)`: 将 `/skills/main/{name}/` 复制到 `/skills/{scope}/{name}/`。自动校验 Agent → scope 映射，纯沙箱文件操作。
- `execute`: 执行 Shell 命令（Python 脚本测试、文件清理等）
- `read_file` / `write_file`: 沙箱文件读写
- `ls`: 查看目录结构
