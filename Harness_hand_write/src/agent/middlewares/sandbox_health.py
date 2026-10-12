"""Per-user sandbox health check and automatic recovery middleware."""
from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware

from agent.backends.sandbox_proxy import SandboxBackendProxy
from agent.utils.agent_logger import get_logger

logger = get_logger("sandbox_health")


class SandboxHealthMiddleware(AgentMiddleware):
    """Ping and recover the current user's sandbox before each agent step."""

    def __init__(
        self,
        *,
        sandbox_backend: SandboxBackendProxy,
        user_id: str,
        agents_md_content: bytes,
    ) -> None:
        super().__init__()
        self._backend = sandbox_backend
        self._user_id = user_id
        self._agents_md = agents_md_content

    def before_agent(self, state: dict[str, Any], runtime: Any) -> None:
        # 同步钩子不执行网络 I/O；健康检查由异步钩子完成。
        return None

    async def abefore_agent(self, state: dict[str, Any], runtime: Any) -> None:
        if await self._check():
            return None

        logger.warning(
            "User sandbox is unhealthy; triggering automatic recovery. user_id=%s",
            self._user_id,
        )
        await self._recover()
        return None

    async def _check(self) -> bool:
        try:
            result = await self._backend.aexecute("echo ok")
            return result.exit_code == 0
        except Exception:
            return False

    async def _recover(self) -> None:
        from agent.backends.sandbox_manager import recreate_user_sandbox

        recovered = await recreate_user_sandbox(self._user_id)
        if recovered is not self._backend:
            self._backend.replace_backend(recovered)

        await self._backend.aupload_files([("/AGENTS.md", self._agents_md)])
        logger.info("Global sandbox automatic recovery completed")
