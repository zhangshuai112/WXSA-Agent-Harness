"""Structured audit logging for agent tool / model actions.

Emits one JSON object per line (JSONL) with fields:
who / what / tool / hitl / cost / latency — suitable for grep, file shipping,
or later ingestion into a log store.

Env:
- AUDIT_LOG_ENABLED: true/1/yes to enable (default true)
- AUDIT_LOG_PATH: optional JSONL path; default ``src/agent/logs/audit.jsonl``
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from agent.utils.agent_logger import LOG_DIR

_LOGGER = logging.getLogger("agent.audit")
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False
_STREAM_READY = False
_FILE_HANDLER: logging.Handler | None = None
_FILE_PATH: str | None = None


def _ensure_stream_handler() -> None:
    global _STREAM_READY
    if _STREAM_READY:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
    _STREAM_READY = True


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_audit_enabled() -> bool:
    # Default on: audit is cheap JSON lines; set AUDIT_LOG_ENABLED=false to disable.
    raw = os.getenv("AUDIT_LOG_ENABLED")
    if raw is None or raw.strip() == "":
        return True
    return _truthy(raw)


def _default_audit_path() -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return str(LOG_DIR / "audit.jsonl")


def _ensure_file_handler() -> None:
    """Attach a JSONL file handler (env path or default under agent/logs)."""
    global _FILE_HANDLER, _FILE_PATH
    path = (os.getenv("AUDIT_LOG_PATH") or "").strip() or _default_audit_path()
    if _FILE_HANDLER is not None and _FILE_PATH == path:
        return
    if _FILE_HANDLER is not None:
        _LOGGER.removeHandler(_FILE_HANDLER)
        _FILE_HANDLER.close()
        _FILE_HANDLER = None
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
    _FILE_HANDLER = handler
    _FILE_PATH = path


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_args(args: Any, *, max_str: int = 120) -> Any:
    """Summarize tool args for audit without dumping large payloads."""
    if args is None:
        return None
    if isinstance(args, Mapping):
        out: dict[str, Any] = {}
        for key, value in args.items():
            k = str(key)
            if any(
                s in k.lower()
                for s in ("password", "secret", "token", "api_key", "authorization")
            ):
                out[k] = "<redacted>"
            elif isinstance(value, str):
                out[k] = value if len(value) <= max_str else value[:max_str] + "…"
            elif isinstance(value, (int, float, bool)) or value is None:
                out[k] = value
            elif isinstance(value, (list, tuple)):
                out[k] = {"type": type(value).__name__, "len": len(value)}
            elif isinstance(value, Mapping):
                out[k] = {"type": "object", "keys": list(value.keys())[:20]}
            else:
                out[k] = type(value).__name__
        return out
    if isinstance(args, str):
        return args if len(args) <= max_str else args[:max_str] + "…"
    return type(args).__name__


def emit_audit_event(
    *,
    action: str,
    agent: str = "main",
    user_id: str | None = None,
    thread_id: str | None = None,
    tool: str | None = None,
    what: str | None = None,
    hitl: str | None = None,
    success: bool | None = None,
    latency_ms: float | None = None,
    tokens: int | None = None,
    cost: float | None = None,
    error: str | None = None,
    args_summary: Any = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Write one structured audit record."""
    if not is_audit_enabled():
        return

    _ensure_stream_handler()
    _ensure_file_handler()

    event: dict[str, Any] = {
        "ts": _utcnow_iso(),
        "action": action,
        "who": user_id or "",
        "thread_id": thread_id or "",
        "agent": agent,
        "what": what or action,
        "tool": tool or "",
        "hitl": hitl or "",
        "success": success,
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        "tokens": tokens,
        "cost": cost,
    }
    if args_summary is not None:
        event["args_summary"] = _safe_args(args_summary)
    if error:
        event["error"] = error[:500]
    if extra:
        event["extra"] = dict(extra)

    # Drop nulls for cleaner JSONL, keep empty strings for stable schema keys.
    compact = {k: v for k, v in event.items() if v is not None}
    _LOGGER.info("%s", json.dumps(compact, ensure_ascii=False, default=str))
