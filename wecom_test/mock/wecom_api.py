"""Mock 企业微信 API，供本地测试 wx_tools 写操作。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MOCK_LOG: List[Dict[str, Any]] = []


def get_mock_log() -> List[Dict[str, Any]]:
    return list(_MOCK_LOG)


def clear_mock_log() -> None:
    _MOCK_LOG.clear()


def _record(action: str, **payload: Any) -> None:
    entry = {"action": action, "time": datetime.now().isoformat(), **payload}
    _MOCK_LOG.append(entry)
    logger.info("[MockWeCom] %s %s", action, json.dumps(payload, ensure_ascii=False))


class MockWxWorkAPI:
    """与 WxWorkAPI 方法签名兼容的 Mock 实现。"""

    def get_access_token(self) -> str:
        return "mock_access_token_for_local_test"

    def send_kf_message(self, customer_id: str, open_kfid: str, content: str) -> dict:
        _record(
            "send_kf_message",
            customer_id=customer_id,
            open_kfid=open_kfid,
            content=content,
        )
        return {"errcode": 0, "errmsg": "ok", "msgid": f"mock_kf_{len(_MOCK_LOG)}"}

    def create_schedule(
        self,
        user_id: str,
        title: str,
        start_time: str,
        duration_minutes: int = 30,
    ) -> bool:
        _record(
            "create_schedule",
            user_id=user_id,
            title=title,
            start_time=start_time,
            duration_minutes=duration_minutes,
        )
        return True

    def notify_user(
        self,
        user_id: str,
        content: str,
        title: str = "企微运营 Harness 操作确认",
        msgtype: str = "text",
    ) -> bool:
        _record(
            "notify_user",
            user_id=user_id,
            title=title,
            msgtype=msgtype,
            content=content,
        )
        return True

    def update_customer_tag(
        self,
        user_id: str,
        external_id: str,
        tag_ids_add: List[str] | None = None,
        tag_ids_remove: List[str] | None = None,
    ) -> bool:
        tag_ids_add = tag_ids_add or []
        tag_ids_remove = tag_ids_remove or []
        _record(
            "update_customer_tag",
            user_id=user_id,
            external_id=external_id,
            tag_ids_add=tag_ids_add,
            tag_ids_remove=tag_ids_remove,
        )
        _sync_tags_to_store(user_id, external_id, tag_ids_add, tag_ids_remove)
        return True

    def get_user_info(self, user_id: str) -> None:
        _record("get_user_info", user_id=user_id)


def _sync_tags_to_store(
    user_id: str,
    external_id: str,
    tag_ids_add: List[str],
    tag_ids_remove: List[str],
) -> None:
    """Mock 标签更新时同步 PostgresStore（与真实 webhook 入库行为近似）。"""
    try:
        import os

        from dotenv import load_dotenv
        from langgraph.store.postgres import PostgresStore
        from psycopg_pool import ConnectionPool

        load_dotenv()
        shared = Path(__file__).resolve().parents[2] / "Harness_hand_write" / ".env"
        if shared.exists():
            load_dotenv(shared, override=False)

        uri = os.getenv("DATABASE_URI") or os.getenv("POSTGRES_URI_CUSTOM")
        if not uri:
            return

        pool = ConnectionPool(
            conninfo=uri,
            min_size=1,
            max_size=1,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        store = PostgresStore(pool)
        item = store.get(("external_user", user_id), external_id)
        if not item:
            return
        value = dict(item.value)
        tags = list(value.get("tags") or [])
        for tid in tag_ids_add:
            if tid not in tags:
                tags.append(tid)
        for tid in tag_ids_remove:
            if tid in tags:
                tags.remove(tid)
        value["tags"] = tags
        store.put(("external_user", user_id), external_id, value)
    except Exception as exc:
        logger.warning("Mock 标签同步 Store 失败: %s", exc)


def enable_mock_wecom() -> MockWxWorkAPI:
    """返回 Mock 实例，并 patch wx_tools 使用的 API 工厂。"""
    mock = MockWxWorkAPI()
    try:
        import tools.wx_tools as wx_tools

        wx_tools._get_wxwork_api = lambda: mock  # type: ignore[assignment]
        logger.info("已 patch wx_tools._get_wxwork_api -> MockWxWorkAPI")
    except ImportError:
        logger.warning("wx_tools 未加载，仅返回 Mock 实例")
    return mock
