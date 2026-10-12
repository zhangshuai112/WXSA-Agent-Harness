"""LangChain tools for WeCom notifications and customer operations."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from utils.agent_logger import get_logger
from wechat_client.wechat_tool_api import WxWorkAPI


logger = get_logger("wx_tools")


def _get_wxwork_api() -> WxWorkAPI:
    """Create the configured WeCom API client lazily."""
    return WxWorkAPI()


def _sync_notify_wecom_user(
    user_id: str,
    content: str,
    title: str = "企微运营 Harness 操作确认",
    msgtype: str = "text",
) -> bool:
    if not user_id or not content:
        raise ValueError("user_id and content are required")
    if msgtype not in {"text", "textcard"}:
        raise ValueError("msgtype must be 'text' or 'textcard'")

    return _get_wxwork_api().notify_user(
        user_id=user_id,
        content=content,
        title=title,
        msgtype=msgtype,
    )


@tool(
    "notify_wecom_user",
    description=(
        "向企业微信指定员工发送文本或文本卡片通知。"
        "需要提供员工 user_id 和通知内容；只有在确实需要通知员工时调用。"
    ),
)
async def notify_wecom_user(
    user_id: str,
    content: str,
    title: str = "企微运营 Harness 操作确认",
    msgtype: str = "text",
) -> bool:
    """Send a notification to a specified WeCom employee.

    Args:
        user_id: The recipient's WeCom user ID.
        content: Notification content.
        title: Text-card title. Used only when msgtype is ``textcard``.
        msgtype: ``text`` or ``textcard``.

    Returns:
        True when WeCom accepts the message.
    """
    return await asyncio.to_thread(
        _sync_notify_wecom_user,
        user_id,
        content,
        title,
        msgtype,
    )


def _sync_update_wecom_customer_tags(
    user_id: str,
    external_id: str,
    tag_ids_add: Optional[List[str]] = None,
    tag_ids_remove: Optional[List[str]] = None,
) -> bool:
    if not user_id or not external_id:
        raise ValueError("user_id and external_id are required")

    add_ids = list(dict.fromkeys(str(tag).strip() for tag in (tag_ids_add or []) if str(tag).strip()))
    remove_ids = list(
        dict.fromkeys(str(tag).strip() for tag in (tag_ids_remove or []) if str(tag).strip())
    )

    if not add_ids and not remove_ids:
        return True

    # The API receives both lists; removing an overlapping tag is the safer result.
    add_ids = [tag_id for tag_id in add_ids if tag_id not in set(remove_ids)]
    return _get_wxwork_api().update_customer_tag(
        user_id=user_id,
        external_id=external_id,
        tag_ids_add=add_ids,
        tag_ids_remove=remove_ids,
    )


@tool(
    "update_wecom_customer_tags",
    description=(
        "更新企业微信客户标签。"
        "通过 tag_ids_add 新增标签，通过 tag_ids_remove 删除标签。"
        "同一个标签同时出现在新增和删除列表时，以删除为准。"
    ),
)
async def update_wecom_customer_tags(
    user_id: str,
    external_id: str,
    tag_ids_add: Optional[List[str]] = None,
    tag_ids_remove: Optional[List[str]] = None,
) -> bool:
    """Add and remove tags from a WeCom external customer.

    Args:
        user_id: The WeCom user ID responsible for the customer.
        external_id: The customer's WeCom external user ID.
        tag_ids_add: Tag IDs to add.
        tag_ids_remove: Tag IDs to remove.

    Returns:
        True when the WeCom tag update succeeds.
    """
    return await asyncio.to_thread(
        _sync_update_wecom_customer_tags,
        user_id,
        external_id,
        tag_ids_add,
        tag_ids_remove,
    )


def _sync_create_wecom_schedule(
    user_id: str,
    title: str,
    start_time: str,
    duration_minutes: int = 30,
) -> bool:
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be greater than 0")

    return _get_wxwork_api().create_schedule(
        user_id=user_id,
        title=title,
        start_time=start_time,
        duration_minutes=duration_minutes,
    )


@tool(
    "create_wecom_schedule",
    description=(
        "在企业微信中为指定员工创建日程。"
        "start_time 格式必须为 YYYY-MM-DD HH:MM:SS，duration_minutes 表示持续分钟数。"
    ),
)
async def create_wecom_schedule(
    user_id: str,
    title: str,
    start_time: str,
    duration_minutes: int = 30,
) -> bool:
    """Create a WeCom schedule for an employee.

    Args:
        user_id: The employee's WeCom user ID.
        title: Schedule title.
        start_time: Start time in ``YYYY-MM-DD HH:MM:SS`` format.
        duration_minutes: Duration in minutes.

    Returns:
        True when the schedule is created successfully.
    """
    return await asyncio.to_thread(
        _sync_create_wecom_schedule,
        user_id,
        title,
        start_time,
        duration_minutes,
    )


def _sync_send_wecom_kf_message(
    external_id: str,
    open_kfid: str,
    content: str,
) -> Dict[str, Any]:
    external_id = (external_id or "").strip()
    open_kfid = (open_kfid or "").strip()
    content = (content or "").strip()
    if not external_id or not open_kfid or not content:
        return {
            "success": False,
            "error_code": "KF_INVALID_ARGS",
            "error": "external_id, open_kfid and content are required",
        }

    from tools.kf_send_guard import (
        evaluate_kf_send_window,
        record_kf_outbound_message,
    )

    window = evaluate_kf_send_window(external_id, open_kfid=open_kfid)
    if not window.get("success"):
        logger.warning(
            "KF send blocked: code=%s external_id=%s open_kfid=%s error=%s",
            window.get("error_code"),
            external_id,
            open_kfid,
            window.get("error"),
        )
        return window

    try:
        # WeCom KF send_msg.touser 与 Store 的 external_id 为同一客户标识
        wecom_result = _get_wxwork_api().send_kf_message(
            customer_id=external_id,
            open_kfid=open_kfid,
            content=content,
        )
    except Exception as exc:
        logger.error("KF send failed after window check: %s", exc)
        return {
            "success": False,
            "error_code": "KF_SEND_FAILED",
            "error": str(exc),
            "quota": {
                "outbound_used": window.get("outbound_used"),
                "outbound_remaining": window.get("outbound_remaining"),
                "max_outbound": window.get("max_outbound"),
                "window_remaining_hours": window.get("window_remaining_hours"),
            },
        }

    msg_id = None
    if isinstance(wecom_result, dict):
        msg_id = wecom_result.get("msgid") or wecom_result.get("msg_id")
    record_kf_outbound_message(
        external_id=external_id,
        open_kfid=open_kfid,
        content=content,
        msg_id=str(msg_id) if msg_id else None,
    )

    used = int(window.get("outbound_used") or 0) + 1
    remaining = max(int(window.get("max_outbound") or 5) - used, 0)
    return {
        "success": True,
        "wecom": wecom_result,
        "quota": {
            "outbound_used": used,
            "outbound_remaining": remaining,
            "max_outbound": window.get("max_outbound"),
            "window_remaining_hours": window.get("window_remaining_hours"),
        },
    }


@tool(
    "send_wecom_kf_message",
    description=(
        "通过企业微信客服向指定客户发送文本消息。"
        "external_id 即客服接口 touser（旧称 customer_id），与系统上下文中的客户 ID 相同；"
        "open_kfid 使用系统上下文注入的企业微信客服账号 ID。"
        "硬性限制：仅在客户主动发消息后的 48 小时内可发，且同一窗口内最多 5 条客服回复；"
        "超限时工具直接返回失败，不会调用企微接口。"
        "仅当客户处于对应 open_kfid 的有效客服会话中，且消息已完成必要人工审核时调用。"
        "该消息以企业微信客服身份发送，不以员工个人身份发送。"
    ),
)
async def send_wecom_kf_message(
    external_id: str,
    open_kfid: str,
    content: str,
) -> Dict[str, Any]:
    """Send an approved text message through WeCom customer service.

    Args:
        external_id: Customer external user ID; also the KF API ``touser``.
        open_kfid: WeCom customer-service account ID (from runtime context).
        content: Text message content.

    Returns:
        On success: ``{"success": True, "wecom": ..., "quota": ...}``.
        On window/quota failure: ``{"success": False, "error_code": ..., "error": ...}``.
    """
    return await asyncio.to_thread(
        _sync_send_wecom_kf_message,
        external_id,
        open_kfid,
        content,
    )


wx_tools = [
    notify_wecom_user,
    update_wecom_customer_tags,
    create_wecom_schedule,
    send_wecom_kf_message,
]


__all__ = [
    "notify_wecom_user",
    "update_wecom_customer_tags",
    "create_wecom_schedule",
    "send_wecom_kf_message",
    "wx_tools",
]
