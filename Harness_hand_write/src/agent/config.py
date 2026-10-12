import os
from datetime import timedelta
from pathlib import Path

import httpx
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI

from psycopg_pool import ConnectionPool
from langgraph.store.postgres import PostgresStore

from opensandbox.config import ConnectionConfig

from dotenv import dotenv_values, load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FILE_ENV = dotenv_values(PROJECT_ROOT / ".env")
# ---------- 用户 配置 ----------

USERNAME = os.getenv("USERNAME")
USERID = os.getenv("USERID")


# ---------- 大模型 配置 ----------
DASHSCOPE_API_KEY=os.getenv("DASHSCOPE_API_KEY")
DASHSCOPE_BASE_URL=os.getenv("DASHSCOPE_BASE_URL")

DEEPSEEK_API_KEY=os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL=os.getenv("DEEPSEEK_BASE_URL") or os.getenv("BASE_URL")

# ---------- postgresql 配置（用于持久化 Agent 短期记忆/checkpoint） ----------
POSTGRES_URI_CUSTOM = os.getenv("POSTGRES_URI_CUSTOM")
DATABASE_URI = (
    POSTGRES_URI_CUSTOM
    or FILE_ENV.get("DATABASE_URI")
    or os.getenv("DATABASE_URI")
)

# ---------- 沙箱 配置 ----------
OPENSANDBOX_URL=os.getenv("OPENSANDBOX_URL")
OPEN_SANDBOX_API_KEY=os.environ["OPEN_SANDBOX_API_KEY"]
# LangGraph 进程启动后预建 1 个 idle 沙箱，缩短首个新用户的冷启动（false 可本地禁用）
SANDBOX_PRE_WARM = os.getenv("SANDBOX_PRE_WARM", "true").lower() in (
    "1",
    "true",
    "yes",
)
# 主 Agent 是否启用 write_todos（TodoListMiddleware）跟踪多步子 Agent 委派进度
ENABLE_WRITE_TODOS = os.getenv("ENABLE_WRITE_TODOS", "true").lower() in (
    "1",
    "true",
    "yes",
)
# ---------- 模型配置 ----------
# 主 Agent 模型
Main_Model = ChatOpenAI(
    model="qwen3.8-flash",
    temperature=1.1,
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
    max_tokens=256000,
)
MAIN_MODEL = Main_Model
# 子agent模型 / 当备用模型本身已是主模型时的次选
Other_Model = ChatOpenAI(
    model="qwen3.7-plus",
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
    max_tokens=25600,
)
SUMMARY_MODEL = Main_Model
# 备用模型（当主模型故障时使用；子 Agent 若本身已是该模型则改用 Other_Model）
FALLBACK_MODEL = init_chat_model(
    "deepseek-v4-flash",
    model_provider="openai",
    temperature=1.0,
    base_url=DEEPSEEK_BASE_URL,
    api_key=DEEPSEEK_API_KEY,
    profile={
        "max_input_tokens": 12800,
        "max_output_tokens": 8192,
        "tool_calling": True,
        "structured_output": True,
    },
)


def _model_id(model) -> str | None:
    """提取模型标识，用于判断主/备是否为同一模型。"""
    for attr in ("model_name", "model", "model_id"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return value
    return None


def resolve_fallback_model(primary):
    """为主模型选择备用模型。

    - 默认：FALLBACK_MODEL（deepseek-v4-flash）
    - 若主模型已是 FALLBACK_MODEL（子 Agent YAML 常见情况）：改用 Other_Model
    """
    primary_id = _model_id(primary)
    fallback_id = _model_id(FALLBACK_MODEL)
    if primary_id and fallback_id and primary_id == fallback_id:
        return Other_Model
    return FALLBACK_MODEL

# 子 Agent YAML 中 model: deepseek-v4-flash 通过 ProviderProfile 注入 DashScope 兼容参数
from deepagents import ProviderProfile, register_provider_profile

register_provider_profile(
    "deepseek-v4-flash",
    ProviderProfile(
        init_kwargs={
            "model_provider": "openai",
            "api_key": DEEPSEEK_API_KEY,
            "base_url": DEEPSEEK_BASE_URL,
            "temperature": 1.0,
            "max_tokens": 8192,
        }
    ),
)

# ---------- 沙箱配置 ----------
# OpenSandbox 异步连接配置（httpx.AsyncHTTPTransport）
SANDBOX_CONFIG = ConnectionConfig(
    domain=OPENSANDBOX_URL,
    use_server_proxy=True,
    request_timeout=timedelta(seconds=60),
    transport=httpx.AsyncHTTPTransport(limits=httpx.Limits(max_connections=20)),
    api_key=OPEN_SANDBOX_API_KEY
)

# ---------- 路径常量 ----------
EXAMPLE_DIR = Path(__file__).parent.parent
print(f'当前代码执行的工作目录为：{EXAMPLE_DIR}')
# 沙箱内技能根路径
SANDBOX_SKILLS_ROOT = "/skills"
# 沙箱内记忆根路径（用户私有记忆存放处）
SANDBOX_MEMORIES_ROOT = "/memories"
# 沙箱内分析中间文件存放目录
SANDBOX_ANALYSIS_ROOT = "/analysis"
# 沙箱内数据文件存放目录
SANDBOX_DATA_ROOT = "/data"
# 本地技能资源目录（项目内的路径，相对于项目根）
LOCAL_SKILLS_DIR = EXAMPLE_DIR / "skills"
# 本地下载目录（从沙箱下载文件的目标路径）
DOWNLOAD_DIR = EXAMPLE_DIR / "download"
# 本地子 Agent 配置目录
LOCAL_SUBAGENT_CONFIG_DIR = EXAMPLE_DIR / "agent/subagents"
# 本地的Agent记忆文件
LOCAL_AGENTS_MD = EXAMPLE_DIR / "agent/memory/AGENTS.md"

# ---------- 文件名常量 ----------
# 主 Agent 只读指引文件（上传到沙箱 /AGENTS.md）
AGENTS_MD_FILENAME = "/AGENTS.md"


# ---------- 用户技能持久化 ----------
# 技能持久化 StoreBackend 路由路径
# PERSISTED_SKILLS_ROOT = "/persisted-skills"
# # 技能 StoreBackend 命名空间（按 Agent scope 组织，无用户隔离）
# SKILLS_STORE_NAMESPACE = ("skills",)

# 子 Agent 名称 → 技能 scope 目录映射
SCOPE_MAP = {
    "main": "main",
    "get-customer-datas-agent": "get-customer-datas-agent",
    "wx_employee_chat_suggestion-agent": "wx_employee_chat_suggestion-agent",
    "update-customer-tags-or-profile-agent": "update-customer-tags-or-profile-agent",
    "update-employee-schedule-agent": "update-employee-schedule-agent",
}

# ---------- 中间件参数 ----------

# ---------- 持久化存储 ----------
# 客户业务数据使用 PostgresStore；LangGraph Server 管理 checkpoint/HITL。
# 连接池大小可用环境变量调整（需同时保证 Postgres max_connections 足够）：
#   PG_POOL_MIN_SIZE=2
#   PG_POOL_MAX_SIZE=20
_PG_POOL_MIN = int(os.getenv("PG_POOL_MIN_SIZE") or FILE_ENV.get("PG_POOL_MIN_SIZE") or "1")
_PG_POOL_MAX = int(os.getenv("PG_POOL_MAX_SIZE") or FILE_ENV.get("PG_POOL_MAX_SIZE") or "10")
if _PG_POOL_MIN < 1:
    _PG_POOL_MIN = 1
if _PG_POOL_MAX < _PG_POOL_MIN:
    _PG_POOL_MAX = _PG_POOL_MIN

pool = ConnectionPool(
    conninfo=DATABASE_URI,
    min_size=_PG_POOL_MIN,
    max_size=_PG_POOL_MAX,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
    },
)
STORE = PostgresStore(pool)
STORE.setup()



