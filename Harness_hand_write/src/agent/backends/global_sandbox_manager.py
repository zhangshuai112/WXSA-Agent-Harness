"""Global OpenSandbox manager shared by FastAPI and Agent Protocol processes.

Persists the single global sandbox id to disk so separate processes can reconnect.
Uses the async OpenSandbox SDK.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from opensandbox import Sandbox
from opensandbox.config import ConnectionConfig

from agent.backends.custom_opensandbox import OpenSandboxBackend
from agent.backends.sandbox_proxy import SandboxBackendProxy
from agent.utils.agent_logger import get_logger

logger = get_logger("global_sandbox_manager")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"
STATE_DIR = PROJECT_ROOT / ".langgraph_api"
STATE_FILE = STATE_DIR / "global_sandbox.json"

LOCAL_SKILLS_DIR = SRC_DIR / "skills"
LOCAL_AGENTS_MD = SRC_DIR / "agent" / "memory" / "AGENTS.md"
AGENTS_MD_FILENAME = "/AGENTS.md"
SANDBOX_SKILLS_ROOT = "/skills"
DEPENDENCIES_SENTINEL = "/tmp/.global_sandbox_packages_installed"

SANDBOX_IMAGE = (
    "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/"
    "code-interpreter:v1.0.2"
)

SANDBOX_CONFIG = ConnectionConfig(
    domain="",
    api_key="my-sandbox-api-key",
    use_server_proxy=True,
    request_timeout=timedelta(seconds=60),
    transport=httpx.AsyncHTTPTransport(limits=httpx.Limits(max_connections=20)),
)

_lock = asyncio.Lock()
_proxy: SandboxBackendProxy | None = None


def _read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read global sandbox state", exc_info=True)
        return {}


def _write_state(sandbox_id: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "sandbox_id": sandbox_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


async def _connect_sandbox(sandbox_id: str) -> OpenSandboxBackend:
    sandbox = await Sandbox.connect(sandbox_id, connection_config=SANDBOX_CONFIG)
    backend = OpenSandboxBackend(sandbox=sandbox)
    await _ping_backend(backend)
    await _ensure_sandbox_ready(backend)
    return backend


async def _create_sandbox() -> OpenSandboxBackend:
    sandbox = await Sandbox.create(
        SANDBOX_IMAGE,
        entrypoint=["/opt/opensandbox/code-interpreter.sh"],
        env={"PYTHON_VERSION": "3.11"},
        resource={"cpu": "2", "memory": "4Gi"},
        timeout=timedelta(minutes=10),
        connection_config=SANDBOX_CONFIG,
    )
    backend = OpenSandboxBackend(sandbox=sandbox)
    await _ensure_sandbox_ready(backend)
    await asyncio.to_thread(_write_state, backend.id)
    return backend


async def _ping_backend(backend: OpenSandboxBackend | SandboxBackendProxy) -> None:
    result = await backend.aexecute("echo ok", timeout=30)
    if result.exit_code != 0:
        raise RuntimeError(f"Sandbox health check failed: {result.output[:500]}")


async def _ensure_sandbox_ready(backend: OpenSandboxBackend | SandboxBackendProxy) -> None:
    sentinel = DEPENDENCIES_SENTINEL
    await backend.aexecute("mkdir -p /analysis/temp")
    await backend.aexecute("python3 -m venv /opt/skills-venv", timeout=120)
    if (await backend.aexecute(f"test -f {sentinel}")).exit_code != 0:
        result = await backend.aexecute(
            "/opt/skills-venv/bin/pip install requests beautifulsoup4 "
            "-i https://mirrors.aliyun.com/pypi/simple/ --default-timeout=60 --no-input -q",
            timeout=300,
        )
        if result.exit_code == 0:
            await backend.aexecute(f"touch {sentinel}")
    await _seed_files(backend)


async def _seed_files(backend: OpenSandboxBackend | SandboxBackendProxy) -> None:
    uploads: list[tuple[str, bytes]] = []
    if LOCAL_AGENTS_MD.exists():
        uploads.append((AGENTS_MD_FILENAME, LOCAL_AGENTS_MD.read_bytes()))

    if LOCAL_SKILLS_DIR.exists():
        for local_file in LOCAL_SKILLS_DIR.rglob("*"):
            if local_file.is_file():
                rel = local_file.relative_to(LOCAL_SKILLS_DIR).as_posix()
                uploads.append((f"{SANDBOX_SKILLS_ROOT}/{rel}", local_file.read_bytes()))

    if uploads:
        await backend.aupload_files(uploads)


async def ensure_global_sandbox() -> SandboxBackendProxy:
    """Return the shared global sandbox, reconnecting or recreating if needed."""
    global _proxy
    async with _lock:
        if _proxy is not None:
            try:
                await _ping_backend(_proxy)
                return _proxy
            except Exception:
                logger.warning(
                    "Cached global sandbox is unhealthy; recreating", exc_info=True
                )

        state = await asyncio.to_thread(_read_state)
        sandbox_id = state.get("sandbox_id")
        if sandbox_id:
            try:
                backend = await _connect_sandbox(sandbox_id)
                _proxy = SandboxBackendProxy(backend)
                return _proxy
            except Exception:
                logger.warning(
                    "Failed to reconnect global sandbox %s", sandbox_id, exc_info=True
                )

        backend = await _create_sandbox()
        _proxy = SandboxBackendProxy(backend)
        return _proxy


async def ping_global_sandbox() -> bool:
    try:
        backend = await ensure_global_sandbox()
        await _ping_backend(backend)
        return True
    except Exception:
        return False


async def recreate_global_sandbox() -> SandboxBackendProxy:
    global _proxy
    async with _lock:
        backend = await _create_sandbox()
        if _proxy is None:
            _proxy = SandboxBackendProxy(backend)
        else:
            _proxy.replace_backend(backend)
        return _proxy


def get_global_sandbox_sync() -> SandboxBackendProxy:
    """同步入口：仅在无运行事件循环时可用（如 CLI）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(ensure_global_sandbox())
    raise RuntimeError(
        "get_global_sandbox_sync() 不可在运行中的事件循环内调用；"
        "请改用 await ensure_global_sandbox()。"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ensure", action="store_true", help="Create or reconnect the global sandbox."
    )
    args = parser.parse_args()
    if args.ensure:
        backend = get_global_sandbox_sync()
        print(f"Global sandbox ready: {backend.id}")


if __name__ == "__main__":
    main()
