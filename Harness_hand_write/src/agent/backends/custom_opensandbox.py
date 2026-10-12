# src/backends/open_sandbox_backend.py
"""OpenSandbox 沙箱后端实现（异步 SDK），遵循 SandboxBackendProtocol 协议。"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox
from opensandbox import Sandbox
from opensandbox.models import WriteEntry
from opensandbox.models.execd import RunCommandOpts

from agent.utils.agent_logger import get_logger

logger = get_logger("opensandbox")


def _run_coro_sync(coro):
    """在无运行事件循环时执行协程；已在 loop 内则报错（应改用 a* 方法）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "OpenSandboxBackend 同步方法不可在运行中的事件循环内调用；"
        "请改用 await aexecute / aupload_files / adownload_files。"
    )


class OpenSandboxBackend(BaseSandbox):
    """基于 OpenSandbox 异步 SDK 的沙箱后端。

    主路径为 ``aexecute`` / ``aupload_files`` / ``adownload_files``。
    同步 ``execute`` / ``upload_files`` / ``download_files`` 仅供无事件循环的脚本使用。
    """

    def __init__(
        self,
        *,
        sandbox: Sandbox,
        timeout: int = 2 * 60 * 60,
    ) -> None:
        logger.info("正在初始化异步 OpenSandbox，沙盒 ID: %s", sandbox.id)
        self._sandbox = sandbox
        self._default_timeout = timeout
        logger.debug("OpenSandbox 初始化完成，默认超时时间=%s秒", timeout)

    @property
    def id(self) -> str:
        return self._sandbox.id

    # 沙箱中非交互式 shell 不会加载 /etc/profile，需要手动注入环境变量
    SANDBOX_PATH = (
        "/opt/skills-venv/bin:"
        "/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin:"
        "/opt/go/1.25.5/bin:"
        "/opt/node/v22.2.0/bin:"
        "/usr/lib/jvm/java-21-openjdk-amd64/bin:"
        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        return _run_coro_sync(self.aexecute(command, timeout=timeout))

    async def aexecute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        effective_timeout = timeout if timeout is not None else self._default_timeout
        wrapped = f'export PATH="{self.SANDBOX_PATH}:$PATH" && {command}'
        logger.debug(
            "准备异步执行命令：%s...（超时时间=%s秒）",
            command[:100],
            effective_timeout,
        )
        return await self._aexecute_command(wrapped, timeout=effective_timeout)

    async def _aexecute_command(
        self,
        command: str,
        *,
        timeout: int,
    ) -> ExecuteResponse:
        try:
            result = await self._sandbox.commands.run(
                command,
                opts=RunCommandOpts(timeout=timedelta(seconds=timeout)),
            )
            stdout = ""
            stderr = ""
            if result.logs.stdout:
                stdout = "\n".join([log.text for log in result.logs.stdout])
            if result.logs.stderr:
                stderr = "\n".join([log.text for log in result.logs.stderr])

            output = stdout
            if stderr and stderr.strip():
                output += f"\n<stderr>{stderr.strip()}</stderr>"

            logger.info("命令执行成功，退出码：%s", result.exit_code or 0)
            return ExecuteResponse(
                output=output,
                exit_code=result.exit_code or 0,
                truncated=False,
            )
        except Exception as e:
            error_msg = str(e)
            logger.error("执行命令时发生错误：%s", error_msg, exc_info=True)
            if "timeout" in error_msg.lower():
                return ExecuteResponse(
                    output=f"命令在 {timeout} 秒后超时",
                    exit_code=124,
                    truncated=False,
                )
            return ExecuteResponse(
                output=f"执行命令时出错：{error_msg}",
                exit_code=1,
                truncated=False,
            )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return _run_coro_sync(self.adownload_files(paths))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            try:
                content = await self._sandbox.files.read_file(path)
                content_bytes = (
                    content.encode("utf-8") if isinstance(content, str) else content
                )
                responses.append(
                    FileDownloadResponse(path=path, content=content_bytes, error=None)
                )
            except Exception:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return _run_coro_sync(self.aupload_files(files))

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        upload_entries: list[WriteEntry] = []

        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            try:
                if isinstance(content, bytes):
                    try:
                        content_str = content.decode("utf-8")
                    except UnicodeDecodeError:
                        content_str = content.decode("latin-1")
                else:
                    content_str = str(content)
                upload_entries.append(WriteEntry(path=path, data=content_str, mode=0o644))
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as e:
                responses.append(FileUploadResponse(path=path, error=str(e)))

        if upload_entries:
            try:
                await self._sandbox.files.write_files(upload_entries)
            except Exception as e:
                for resp in responses:
                    if resp.error is None:
                        resp.error = f"upload_failed: {e}"
        return responses
