"""项目统一日志入口。

用法::

    from utils.agent_logger import get_logger, configure_logging

    configure_logging()  # 进程启动时调用一次（可重复，幂等）
    logger = get_logger("wx_tools")
    logger.info("...")

日志目录：``src/agent/logs/``。不同业务部分写入不同文件：

- main.log           主 Agent / graph
- wx.log             企微工具与 API
- store.log          Store 读写 / 客户同步
- sandbox.log        OpenSandbox 与沙箱中间件
- middleware.log     其它中间件
- observability.log  Langfuse 等观测
- agent.log          未归类默认

环境变量：

- LOG_LEVEL：全局默认级别（默认 INFO）
- LOG_LEVEL_<PART>：覆盖某部分，如 LOG_LEVEL_SANDBOX=ERROR
"""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Optional, Tuple

# src/agent/logs
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"

_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_FORMATTER = logging.Formatter(_FORMAT)

# 逻辑分区 → 日志文件名
PART_FILES: Dict[str, str] = {
    "main": "main.log",
    "wx": "wx.log",
    "store": "store.log",
    "sandbox": "sandbox.log",
    "middleware": "middleware.log",
    "observability": "observability.log",
    "default": "agent.log",
}

# 分区默认级别（可被 LOG_LEVEL / LOG_LEVEL_<PART> 覆盖）
PART_DEFAULT_LEVELS: Dict[str, int] = {
    "main": logging.INFO,
    "wx": logging.INFO,
    "store": logging.INFO,
    "sandbox": logging.ERROR,  # 沙箱默认少说话
    "middleware": logging.INFO,
    "observability": logging.INFO,
    "default": logging.INFO,
}

# logger 短名 / 模块路径片段 → 分区
_NAME_PART_RULES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("main_agent", "graph", "agent.main", "agent.graph"), "main"),
    (("wx_tools", "wechat_tool", "wechat_client", "agent.tools.wx"), "wx"),
    (("store_tool", "customer_sync", "agent.tools.store", "agent.store"), "store"),
    (
        (
            "opensandbox",
            "custom_opensandbox",
            "sandbox_manager",
            "global_sandbox",
            "sandbox_health",
            "sandbox_breaker",
            "agent.backends",
        ),
        "sandbox",
    ),
    (
        (
            "context_injection",
            "tool_error",
            "skills_sync",
            "agent.middlewares",
        ),
        "middleware",
    ),
    (("langfuse", "observability", "agent.observability"), "observability"),
)

_configured = False
_file_handlers: Dict[str, logging.Handler] = {}
_logger_files: Dict[str, str] = {}  # logger name -> file path attached


def _parse_level(value: Optional[str], default: int) -> int:
    if value is None or not str(value).strip():
        return default
    text = str(value).strip().upper()
    if text.isdigit():
        return int(text)
    return getattr(logging, text, default)


def _global_default_level() -> int:
    return _parse_level(os.getenv("LOG_LEVEL"), logging.INFO)


def resolve_part(name: str) -> str:
    """根据 logger 名解析业务分区。"""
    normalized = (name or "default").strip().lower()
    if normalized.startswith("agent."):
        normalized = normalized[len("agent.") :]
    # 显式分区名
    if normalized in PART_FILES:
        return normalized
    for keywords, part in _NAME_PART_RULES:
        for kw in keywords:
            if kw in normalized or normalized.startswith(kw):
                return part
    return "default"


def part_level(part: str) -> int:
    env_key = f"LOG_LEVEL_{part.upper()}"
    return _parse_level(os.getenv(env_key), PART_DEFAULT_LEVELS.get(part, _global_default_level()))


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _shared_file_handler(filename: str) -> logging.Handler:
    _ensure_log_dir()
    path = LOG_DIR / filename
    key = str(path)
    if key not in _file_handlers:
        handler = RotatingFileHandler(
            path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(_FORMATTER)
        handler.setLevel(logging.DEBUG)  # 真正过滤看 logger level
        _file_handlers[key] = handler
    return _file_handlers[key]


def _safe_logger_name(name: str) -> str:
    """对外短名规范成 agent.* 层级，便于 propagate 到 agent 控制台。"""
    raw = (name or "default").strip()
    if not raw:
        raw = "default"
    if raw == "__main__":
        return "agent.main"
    # 已是 agent.xxx
    if raw.startswith("agent."):
        return raw
    # 传入 __name__ 如 agent.tools.wx_tools
    if raw.startswith("agent"):
        return raw if "." in raw else f"agent.{raw}"
    # 短名 wx_tools → agent.wx_tools
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", raw)
    return f"agent.{safe}"


def configure_logging() -> None:
    """幂等：配置 agent 根 logger 的控制台输出。"""
    global _configured
    if _configured:
        return

    _ensure_log_dir()
    root_agent = logging.getLogger("agent")
    root_agent.setLevel(_global_default_level())
    root_agent.propagate = False

    if not any(isinstance(h, logging.StreamHandler) for h in root_agent.handlers):
        console = logging.StreamHandler()
        console.setFormatter(_FORMATTER)
        console.setLevel(logging.DEBUG)
        root_agent.addHandler(console)

    # 默认落一份总览，避免只有分区文件时丢“未挂文件”的日志
    default_file = _shared_file_handler(PART_FILES["default"])
    if default_file not in root_agent.handlers:
        root_agent.addHandler(default_file)

    _configured = True


def get_logger(name: str = "default", level: Optional[int] = None) -> logging.Logger:
    """获取带分区文件输出的 logger。

    Args:
        name: 短名（如 ``wx_tools``）或 ``__name__``。
        level: 显式级别；默认按分区 / 环境变量。
    """
    configure_logging()
    logger_name = _safe_logger_name(name)
    part = resolve_part(logger_name)

    logger = logging.getLogger(logger_name)
    effective_level = level if level is not None else part_level(part)
    logger.setLevel(effective_level)
    logger.propagate = True  # 升到 agent 控制台 + agent.log

    filename = PART_FILES.get(part, PART_FILES["default"])
    file_handler = _shared_file_handler(filename)
    # 同一 logger 只挂一次该文件 handler
    if _logger_files.get(logger_name) != str(LOG_DIR / filename):
        if file_handler not in logger.handlers:
            logger.addHandler(file_handler)
        _logger_files[logger_name] = str(LOG_DIR / filename)

    return logger


__all__ = [
    "LOG_DIR",
    "PART_FILES",
    "configure_logging",
    "get_logger",
    "resolve_part",
    "part_level",
]
