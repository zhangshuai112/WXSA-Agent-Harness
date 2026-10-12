"""
代理层
SandboxBackendProxy — 稳定句柄，内部 backend 可热替换(如果沙箱实例出现问题就可以直接创建一个新的)。

显式代理 SandboxBackendProtocol 全部 18 个方法 + id property，
确保 Python MRO 不会找到协议层的 NotImplementedError 默认实现。
"""
from __future__ import annotations

# 设计说明：调用方长期持有本代理，而非直接持有真实后端。沙箱重建时只需
# 替换 _backend，已有 Agent、工具和中间件仍使用同一对象，不会引用旧沙箱。

from deepagents.backends.protocol import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    SandboxBackendProtocol,
    WriteResult,
)


class SandboxBackendProxy(SandboxBackendProtocol):
    """代理所有 SandboxBackendProtocol 方法到内部 backend，支持热替换。"""

    def __init__(self, backend: SandboxBackendProtocol) -> None:
        # 保存当前实际工作的后端实例。
        self._backend = backend

    @property
    def id(self) -> str:
        # ID 必须透传给当前后端，重建后自然返回新沙箱 ID。
        return self._backend.id

    def replace_backend(self, backend: SandboxBackendProtocol) -> None:
        # 热替换仅改变内部引用，故外部持有的 proxy 身份保持稳定。
        self._backend = backend

    # ---- 同步方法 ----

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        # 同步命令执行直接委托给当前后端。
        return self._backend.execute(command, timeout=timeout)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        # 读取指定文件的分页内容。
        return self._backend.read(file_path, offset, limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        # 写入完整文本文件。
        return self._backend.write(file_path, content)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        # 按协议执行文本替换，可选择替换全部匹配项。
        return self._backend.edit(file_path, old_string, new_string, replace_all)

    def ls_info(self, path: str) -> list:
        # 列出目录条目及其元数据。
        return self._backend.ls_info(path)

    def ls(self, path: str) -> list:
        # SkillsMiddleware 等组件依赖 ls（不仅是 ls_info）。
        backend_ls = getattr(self._backend, "ls", None)
        if callable(backend_ls):
            return backend_ls(path)
        entries = self._backend.ls_info(path)
        return [getattr(entry, "path", str(entry)) for entry in entries]

    def glob_info(self, pattern: str, path: str = "/") -> list:
        # 在给定根目录中按 glob 模式查找。
        return self._backend.glob_info(pattern, path)

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list | str:
        # 在文件内容中执行原始文本搜索。
        return self._backend.grep_raw(pattern, path, glob)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        # 批量上传二进制文件到沙箱。
        return self._backend.upload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        # 批量下载沙箱文件。
        return self._backend.download_files(paths)

    # ---- 异步方法 ----

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        # 异步版本同样只做透明转发。
        return await self._backend.aexecute(command, timeout=timeout)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        # 异步读取文件。
        return await self._backend.aread(file_path, offset, limit)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        # 异步写入文件。
        return await self._backend.awrite(file_path, content)

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        # 异步文本编辑。
        return await self._backend.aedit(file_path, old_string, new_string, replace_all)

    async def als_info(self, path: str) -> list:
        # 异步列目录。
        return await self._backend.als_info(path)

    async def als(self, path: str) -> list:
        backend_als = getattr(self._backend, "als", None)
        if callable(backend_als):
            return await backend_als(path)
        import asyncio

        return await asyncio.to_thread(self.ls, path)

    async def aglob_info(self, pattern: str, path: str = "/") -> list:
        # 异步 glob 搜索。
        return await self._backend.aglob_info(pattern, path)

    async def agrep_raw(self, pattern: str, path: str | None = None, glob: str | None = None) -> list | str:
        # 异步文本搜索。
        return await self._backend.agrep_raw(pattern, path, glob)

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        # 异步批量上传。
        return await self._backend.aupload_files(files)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        # 异步批量下载。
        return await self._backend.adownload_files(paths)

    # ---- fallback：未来新增的方法 ----

    def __getattr__(self, name: str):
        # 私有属性不透传，避免外部绕过代理修改其内部状态。
        if name.startswith("_"):
            raise AttributeError(name)
        # 协议未来新增方法时，仍可在不升级代理的情况下委托到底层。
        return getattr(self._backend, name)
