"""企微运营 Harness 微信同步 Store 访问层。

旧版通过 LangGraph SDK + ``/wecom/get_token`` 远程写入 Store；
当前项目与 Agent / wecom_admin 共用 PostgreSQL ``PostgresStore``，改为直连数据库。
"""

from __future__ import annotations

import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz
from dotenv import load_dotenv
from langgraph.store.base import Item, SearchItem
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

load_dotenv()
_shared_env = Path(__file__).resolve().parents[2] / "Harness_hand_write" / ".env"
if _shared_env.exists():
    load_dotenv(_shared_env, override=False)


def timestamp2YYYYMMDD(timestamp: int) -> str:
    """UTC 时间戳 → 东八区 ``YYYYMMDD`` 字符串。"""
    if not timestamp:
        return ""
    try:
        tz_china = pytz.timezone("Asia/Shanghai")
        dt_utc = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt_utc.astimezone(tz_china).strftime("%Y%m%d")
    except Exception:
        return ""


def _resolve_database_uri(database_uri: Optional[str] = None) -> str:
    uri = (
        database_uri
        or os.getenv("DATABASE_URI")
        or os.getenv("POSTGRES_URI_CUSTOM")
    )
    if not uri:
        raise ValueError(
            "缺少 DATABASE_URI。请在 wecom_wxsync/.env 或 Harness_hand_write/.env 中配置。"
        )
    return uri


class WecomStoreAPI:
    """封装 PostgresStore，供微信同步服务读写业务数据。"""

    def __init__(self, database_uri: Optional[str] = None) -> None:
        uri = _resolve_database_uri(database_uri)
        self._pool = ConnectionPool(
            conninfo=uri,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        self.store = PostgresStore(self._pool)
        self.store.setup()

    @staticmethod
    def _item_to_dict(item: Optional[Item]) -> Dict[str, Any]:
        if not item:
            return {}
        if isinstance(item.value, dict):
            return item.value.copy()
        return item.value if item.value is not None else {}

    # ==================== 写入（同步服务使用） ====================

    def upsert_external_user(
        self,
        external_id: str,
        union_id: str,
        follow_user_id: str,
        name: str,
        remark_name: str = "",
        tags: Optional[List[str]] = None,
    ) -> None:
        self.store.put(
            ("external_user", follow_user_id),
            external_id,
            {
                "external_id": external_id,
                "union_id": union_id,
                "follow_user_id": follow_user_id,
                "name": name,
                "remark_name": remark_name,
                "tags": list(tags or []),
            },
        )

    def upsert_tags_setting(
        self,
        tag_id: str,
        strategy_id: int,
        group_id: str,
        group_name: str,
        tag_name: str,
        deleted: bool,
    ) -> None:
        self.store.put(
            ("tags_setting",),
            tag_id,
            {
                "strategy_id": strategy_id,
                "group_id": group_id,
                "group_name": group_name,
                "tag_id": tag_id,
                "tag_name": tag_name,
                "deleted": deleted,
            },
        )

    def upsert_wxqy_msg(
        self,
        msg_id: str,
        from_id: str,
        to_id: str,
        msg_time: int,
        content: str,
        seq: int,
    ) -> None:
        from_to_sorted_key = "".join(sorted([from_id, to_id]))
        self.store.put(
            ("wxqy_msg", from_to_sorted_key),
            msg_id,
            {
                "msg_id": msg_id,
                "from_to_sorted_key": from_to_sorted_key,
                "from_id": from_id,
                "to_id": to_id,
                "YYYYMMDD": timestamp2YYYYMMDD(msg_time),
                "msg_time": msg_time,
                "content": content,
                "seq": seq,
            },
        )

    def upsert_wxkf_msg(
        self,
        msg_id: str,
        external_id: str,
        open_kfid: str,
        servicer_userid: str,
        msg_time: int,
        origin: int,
        msgtype: str,
        content: str,
    ) -> None:
        self.store.put(
            ("wxkf_msg", external_id),
            msg_id,
            {
                "msg_id": msg_id,
                "external_id": external_id,
                "open_kfid": open_kfid,
                "servicer_userid": servicer_userid,
                "YYYYMMDD": timestamp2YYYYMMDD(msg_time),
                "msg_time": msg_time,
                "origin": origin,
                "msg_type": msgtype,
                "content": content,
            },
        )

    def upsert_wxxd_order(
        self,
        union_id: str,
        order_id: str,
        open_id: str,
        order_status: int,
        order_products: List[str],
        order_price: float,
        order_create_time: int,
        order_raw_info: Dict[str, Any],
    ) -> None:
        self.store.put(
            ("wxxd_order", union_id),
            order_id,
            {
                "order_id": order_id,
                "open_id": open_id,
                "union_id": union_id,
                "order_status": order_status,
                "order_products": order_products,
                "order_price": order_price,
                "order_create_time": order_create_time,
                "YYYYMMDD": timestamp2YYYYMMDD(order_create_time),
                "order_raw_info": order_raw_info,
            },
        )

    def upsert_wecom_global_state(self, key: str, value: Any) -> None:
        self.store.put(("wecom_global_state",), key, value)

    def get_wecom_global_state(self, key: str) -> Dict[str, Any]:
        return self._item_to_dict(self.store.get(("wecom_global_state",), key))


def create_wecom_store_api(
    database_uri: Optional[str] = None,
    *,
    url: Optional[str] = None,
    server_url: Optional[str] = None,
    user_id: Optional[str] = None,
    password: Optional[str] = None,
) -> WecomStoreAPI:
    """创建 Store 客户端。

    新用法：``create_wecom_store_api()`` 或 ``create_wecom_store_api(database_uri=...)``。

    旧参数 ``url`` / ``server_url`` / ``user_id`` / ``password`` 已废弃。
    """
    legacy = url or server_url or user_id or password
    if legacy:
        warnings.warn(
            "WECOM_SERVER_URL / WECOM_USER_ID / WECOM_PASSWORD 已废弃，"
            "请改用 DATABASE_URI 直连 PostgresStore。",
            DeprecationWarning,
            stacklevel=2,
        )
    return WecomStoreAPI(database_uri=database_uri)
