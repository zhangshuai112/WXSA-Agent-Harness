# src/backends/sandbox_setup.py
"""
OpenSandbox 沙箱的初始化与文件播种模块（异步）。

职责:
1. 获取或创建 OpenSandbox 沙箱，包装为 OpenSandboxBackend。
2. 播种技能文件（技能包 SKILL.md）。

注意：AGENTS.md 已迁移到 StoreBackend（全局共享），不经过沙箱。
用户长期记忆（/memories/）由 CompositeBackend 路由到 StoreBackend 持久化。
运行时的增量技能同步由 SkillsSyncMiddleware 负责。
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from opensandbox import Sandbox
from opensandbox.models.sandboxes import NetworkPolicy, NetworkRule

from agent.backends.custom_opensandbox import OpenSandboxBackend
from agent.config import (
    AGENTS_MD_FILENAME,
    LOCAL_AGENTS_MD,
    LOCAL_SKILLS_DIR,
    SANDBOX_SKILLS_ROOT,
)


def _truthy_env(name: str, default: bool = True) -> bool:
    import os

    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def build_sandbox_network_policy() -> NetworkPolicy:
    """默认拒绝出站；仅放行 pip 镜像与技能市场域名。"""
    return NetworkPolicy(
        defaultAction="deny",
        egress=[
            NetworkRule(action="allow", target="mirrors.aliyun.com"),
            NetworkRule(action="allow", target="clawhub.ai"),
            NetworkRule(action="allow", target="*.clawhub.ai"),
            NetworkRule(action="allow", target="modelscope.cn"),
            NetworkRule(action="allow", target="*.modelscope.cn"),
        ],
    )


async def _apply_network_policy(sandbox: Sandbox) -> None:
    """对已连接沙箱尽量补齐 egress 规则（新建时已在 create 传入）。"""
    policy = build_sandbox_network_policy()
    rules = policy.egress or []
    try:
        if hasattr(sandbox, "patch_egress_rules") and rules:
            await sandbox.patch_egress_rules(rules)
            print("[INFO] 已对现有沙箱 patch egress 白名单规则")
    except Exception as exc:
        print(f"[WARNING] 应用沙箱网络策略失败（可忽略若服务端未启用 egress）: {exc}")


async def setup_sandbox(config, sandbox_id=None, image=None) -> OpenSandboxBackend:
    """获取或创建沙箱，播种基础文件。"""
    network_policy: Optional[NetworkPolicy] = None
    if _truthy_env("SANDBOX_NETWORK_POLICY_ENABLED", default=True):
        network_policy = build_sandbox_network_policy()

    sandbox: Sandbox | None = None

    if sandbox_id:
        print(f"[INFO] 正在连接到现有沙箱: {sandbox_id}")
        try:
            sandbox = await Sandbox.connect(sandbox_id, connection_config=config)
            print(f"[INFO] 成功连接到沙箱: {sandbox_id}")
            if network_policy is not None:
                await _apply_network_policy(sandbox)
        except Exception as e:
            print(f"[WARNING] 连接沙箱失败: {e}，将创建新沙箱")
            sandbox_id = None
            sandbox = None

    if sandbox is None:
        if not image:
            image = "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2"

        print(f"[INFO] 正在创建新沙箱，使用镜像: {image}")
        create_kwargs = {
            "entrypoint": ["/opt/opensandbox/code-interpreter.sh"],
            "env": {"PYTHON_VERSION": "3.11"},
            "resource": {"cpu": "2", "memory": "4Gi"},
            "timeout": timedelta(minutes=100),
            "connection_config": config,
        }
        if network_policy is not None:
            create_kwargs["network_policy"] = network_policy
            print(
                "[INFO] 沙箱网络策略: defaultAction=deny, "
                "allow=mirrors.aliyun.com,clawhub.ai,modelscope.cn"
            )

        sandbox = await Sandbox.create(image, **create_kwargs)

    backend = OpenSandboxBackend(sandbox=sandbox)
    print(f"[INFO] 沙箱就绪，ID: {sandbox.id}")

    await _ensure_dirs(backend)
    await _seed_files(backend)
    await _create_venv(backend)

    return backend


_SKILL_DIRS = ["/analysis/temp"]
_VENV_PATH = "/opt/skills-venv"
_VENV_PIP = f"{_VENV_PATH}/bin/pip"
_PREINSTALL_PACKAGES = ["requests", "beautifulsoup4"]
_PYPI_INDEX = "https://mirrors.aliyun.com/pypi/simple/"
_PIP_INSTALL_ARGS = f"-i {_PYPI_INDEX} --default-timeout=60 --no-input -q"


async def _ensure_dirs(backend: OpenSandboxBackend) -> None:
    for d in _SKILL_DIRS:
        await backend.aexecute(f"mkdir -p {d}")


async def _create_venv(backend: OpenSandboxBackend) -> None:
    result = await backend.aexecute(f"python3 -m venv {_VENV_PATH}")
    if result.exit_code != 0:
        print(f"[WARNING] venv 创建失败: {result.output[:200]}")
        return
    print(f"[INFO] Python venv 就绪: {_VENV_PATH}")

    await backend.aexecute(
        f"{_VENV_PIP} install --upgrade pip {_PIP_INSTALL_ARGS}", timeout=60
    )

    _sentinel = "/tmp/.venv_packages_installed"
    if (await backend.aexecute(f"test -f {_sentinel}")).exit_code == 0:
        return

    pkgs = " ".join(_PREINSTALL_PACKAGES)
    print(f"[INFO] 正在安装 Python 依赖: {pkgs}...")
    result = await backend.aexecute(
        f"{_VENV_PIP} install {pkgs} {_PIP_INSTALL_ARGS}",
        timeout=300,
    )
    if result.exit_code == 0:
        await backend.aexecute(f"touch {_sentinel}")
        print("[INFO] 所有依赖安装成功")
    else:
        print(f"[WARNING] 依赖安装失败: {result.output[:200]}")


async def _seed_files(backend: OpenSandboxBackend) -> None:
    file_mapping: List[Tuple[Path, str]] = []

    if LOCAL_AGENTS_MD.exists():
        file_mapping.append((LOCAL_AGENTS_MD, AGENTS_MD_FILENAME))

    skills_base = Path(LOCAL_SKILLS_DIR)
    if skills_base.exists():
        for skill_dir in skills_base.iterdir():
            if not skill_dir.is_dir():
                continue
            for local_file in skill_dir.rglob("*"):
                if local_file.is_file():
                    rel = local_file.relative_to(skills_base).as_posix()
                    sandbox_path = f"{SANDBOX_SKILLS_ROOT}/{rel}"
                    file_mapping.append((local_file, sandbox_path))

    to_upload: List[Tuple[str, bytes]] = []
    for local_path, sandbox_path in file_mapping:
        if not local_path.exists():
            continue
        local_content = local_path.read_bytes()
        check = await backend.aexecute(f"test -f {sandbox_path}")
        if check.exit_code == 0:
            try:
                results = await backend.adownload_files([sandbox_path])
                if results and results[0].content and not results[0].error:
                    remote_content = results[0].content
                    if isinstance(remote_content, str):
                        remote_content = remote_content.encode("utf-8")
                    if remote_content == local_content:
                        continue
            except Exception:
                pass
        to_upload.append((sandbox_path, local_content))

    if to_upload:
        print(f"[INFO] 正在上传 {len(to_upload)} 个基础文件...")
        await backend.aupload_files(to_upload)
        print("[INFO] 基础文件上传完成。")
    else:
        print("[INFO] 所有基础文件已就绪，无需上传。")
