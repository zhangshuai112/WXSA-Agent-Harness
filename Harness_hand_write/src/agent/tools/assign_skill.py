# src/tools/assign_skill.py
"""
技能分配工具

将 /skills/main/ 下已验证的技能分配给指定 Agent（主 Agent 或子 Agent）。
支持沙箱内复制和压缩包清理，不将技能文件写入 Store。
"""
from __future__ import annotations

from agent.config import SCOPE_MAP


def create_assign_skill_tool(sandbox_backend):
    """
    创建 assign_skill 工具工厂函数。

    Args:
        sandbox_backend: OpenSandboxBackend / SandboxBackendProxy，需支持 aexecute。
    Returns:
        assign_skill 工具函数（异步）。
    """
    from langchain_core.tools import tool

    @tool
    async def assign_skill(skill_name: str, agent_name: str) -> str:
        """
        将已验证的技能分配给指定 Agent。

        前提条件：技能已下载/创建到 /skills/main/{skill_name}/ 并通过测试。

        Args:
            skill_name: 技能目录名（如 "web-scraper"）
            agent_name: 目标 Agent（须与 SCOPE_MAP 键一致）：
                - "main" — 分配给主 Agent 自身（技能已就位，无需复制）
                - "get-customer-datas-agent"
                - "wx_employee_chat_suggestion-agent"
                - "update-customer-tags-or-profile-agent"
                - "update-employee-schedule-agent"

        Returns:
            分配确认或错误信息。
        """
        if agent_name not in SCOPE_MAP:
            available = ", ".join(SCOPE_MAP.keys())
            return f"错误：未知 Agent '{agent_name}'。可用: {available}"

        scope = SCOPE_MAP[agent_name]
        source_dir = f"/skills/main/{skill_name}"
        target_dir = f"/skills/{scope}/{skill_name}"

        check = await sandbox_backend.aexecute(f"test -f {source_dir}/SKILL.md")
        if check.exit_code != 0:
            return (
                f"错误：技能 '{skill_name}' 在 {source_dir}/ 下不存在。\n"
                f"请先完成技能下载/创建和测试。"
            )

        if agent_name == "main":
            cp_result = "（主 Agent 技能已就位，无需移动）"
        else:
            result = await sandbox_backend.aexecute(
                f"mkdir -p {target_dir} && cp -r {source_dir}/* {target_dir}/"
            )
            if result.exit_code != 0:
                return f"错误：复制技能文件失败:\n{result.output}"
            verify = await sandbox_backend.aexecute(f"ls {target_dir}/")
            cp_result = (
                f"✅ 已复制到沙箱 {target_dir}/\n"
                f"文件:\n{verify.output.strip()}"
            )

        cleanup_report = await _cleanup_packages(sandbox_backend)

        return (
            f"✅ 技能 '{skill_name}' 已分配给 Agent '{agent_name}'（scope: {scope}）\n"
            f"{cp_result}\n"
            f"{cleanup_report}"
        )

    assign_skill.name = "assign_skill"
    return assign_skill


async def _cleanup_packages(sandbox_backend) -> str:
    """删除 /skills/main/ 下的压缩包文件。"""
    patterns = "*.zip *.tar.gz *.tar *.tgz *.tar.bz2 *.tar.xz"
    cmd = f"cd /skills/main/ && rm -f {patterns} 2>/dev/null; ls {patterns} 2>/dev/null || echo 'none'"
    result = await sandbox_backend.aexecute(cmd)

    output = result.output.strip()
    if output == "none" or not output:
        return "🧹 压缩包已清理"
    return f"🧹 压缩包已清理（残留: {output}）"
