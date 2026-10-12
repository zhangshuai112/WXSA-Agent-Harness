"""企微运营 Harness 管理后台 Store 访问层。

旧版通过 LangGraph SDK + ``/wecom/get_token`` 访问远程 Store；
当前项目与 Agent 共用同一 PostgreSQL（``PostgresStore``），因此改为直连数据库。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langgraph.store.base import Item, SearchItem
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

# 本地 .env + 主项目 .env（若存在则复用 DATABASE_URI）
load_dotenv()
_shared_env = Path(__file__).resolve().parents[2] / "Harness_hand_write" / ".env"
if _shared_env.exists():
    load_dotenv(_shared_env, override=False)


def _resolve_database_uri(database_uri: Optional[str] = None) -> str:
    uri = (
        database_uri
        or os.getenv("DATABASE_URI")
        or os.getenv("POSTGRES_URI_CUSTOM")
    )
    if not uri:
        raise ValueError(
            "缺少 DATABASE_URI。请在 wecom_admin/.env 或 Harness_hand_write/.env 中配置。"
        )
    return uri


class WecomStoreAPI:
    """封装 PostgresStore，供管理后台读写业务数据。"""

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

    @classmethod
    def _search_to_dict_list(cls, items: List[SearchItem]) -> List[Dict[str, Any]]:
        if not items:
            return []
        return [cls._item_to_dict(item) for item in items]

    # ==================== 员工信息 ====================

    def upsert_employee(self, user_id: str, name: str) -> None:
        self.store.put(
            ("employee",),
            user_id,
            {"user_id": user_id, "name": name},
        )

    def delete_employee(self, user_id: str) -> None:
        self.store.delete(("employee",), user_id)

    def get_employee_by_user_id(self, user_id: str) -> Dict[str, Any]:
        if not user_id:
            return {}
        return self._item_to_dict(self.store.get(("employee",), user_id))

    def list_all_employee(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        items = self.store.search(("employee",), limit=limit)
        return self._search_to_dict_list(items)

    # ==================== 外部客户信息 ====================

    def get_external_user_by_external_id(
        self, external_id: str, follow_user_id: str
    ) -> Dict[str, Any]:
        if not external_id or not follow_user_id:
            return {}
        return self._item_to_dict(
            self.store.get(("external_user", follow_user_id), external_id)
        )

    def list_external_user_by_follow_user_id(
        self, follow_user_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not follow_user_id:
            return []
        items = self.store.search(("external_user", follow_user_id), limit=limit)
        return self._search_to_dict_list(items)

    def get_external_user_by_union_id(
        self,
        union_id: str,
        follow_user_id: str,
        limit: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        if not union_id or not follow_user_id:
            return None
        items = self.store.search(
            ("external_user", follow_user_id),
            filter={"union_id": union_id},
            limit=limit or 1,
        )
        if not items:
            return None
        return self._item_to_dict(items[0])

    def get_external_user_tag_by_external_id(
        self, external_id: str, follow_user_id: str
    ) -> List[Dict[str, Any]]:
        customer = self.get_external_user_by_external_id(external_id, follow_user_id)
        tag_ids = customer.get("tags", []) if customer else []
        tag_details: List[Dict[str, Any]] = []
        for tag_id in tag_ids:
            tag = self.get_tags_setting_by_tag_id(tag_id)
            if tag and tag.get("deleted") is False:
                tag_details.append(tag)
        return tag_details

    # ==================== 客户 profile ====================

    def get_profile_by_external_id(
        self, external_id: str, follow_user_id: str
    ) -> Dict[str, Any]:
        if not external_id or not follow_user_id:
            return {}
        return self._item_to_dict(
            self.store.get(("external_user_profile", follow_user_id), external_id)
        )

    # ==================== 全局标签定义 ====================

    def get_tags_setting_by_tag_id(self, tag_id: str) -> Dict[str, Any]:
        if not tag_id:
            return {}
        return self._item_to_dict(self.store.get(("tags_setting",), tag_id))

    def list_all_tags_setting(
        self,
        limit: Optional[int] = None,
        strategy_id: Optional[int] = None,
        group_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        items = self.store.search(("tags_setting",), limit=limit)
        results = self._search_to_dict_list(items)
        if strategy_id is not None:
            results = [item for item in results if item.get("strategy_id") == strategy_id]
        if group_id is not None:
            results = [item for item in results if item.get("group_id") == group_id]
        return [item for item in results if item.get("deleted") is False]

    # ==================== 企业微信聊天 ====================

    def get_wxqy_msg_by_msg_id(
        self, msg_id: str, external_id: str, user_id: str
    ) -> Dict[str, Any]:
        from_to_key = "".join(sorted([external_id, user_id]))
        return self._item_to_dict(
            self.store.get(("wxqy_msg", from_to_key), msg_id)
        )

    def list_last_wxqy_msg(
        self,
        external_id: str,
        user_id: str,
        after_yyyy_mm_dd: str,
        limit: Optional[int] = 100,
    ) -> List[Dict[str, Any]]:
        if not external_id or not user_id:
            return []
        from_to_key = "".join(sorted([external_id, user_id]))
        filt = {"YYYYMMDD": {"$gte": after_yyyy_mm_dd}} if after_yyyy_mm_dd else {}
        items = self.store.search(
            ("wxqy_msg", from_to_key),
            filter=filt,
            limit=limit,
        )
        return self._search_to_dict_list(items)

    # ==================== 微信客服 ====================

    def get_wxkf_msg_by_msg_id(self, msg_id: str, external_id: str) -> Dict[str, Any]:
        return self._item_to_dict(self.store.get(("wxkf_msg", external_id), msg_id))

    def list_last_wxkf_msg(
        self,
        external_id: str,
        after_yyyy_mm_dd: str,
        limit: Optional[int] = 100,
    ) -> List[Dict[str, Any]]:
        if not external_id:
            return []
        filt = {"YYYYMMDD": {"$gte": after_yyyy_mm_dd}} if after_yyyy_mm_dd else {}
        items = self.store.search(
            ("wxkf_msg", external_id),
            filter=filt,
            limit=limit,
        )
        return self._search_to_dict_list(items)

    # ==================== 客户订单 ====================

    def get_wxxd_order_by_order_id(
        self, union_id: str, order_id: str
    ) -> Dict[str, Any]:
        return self._item_to_dict(self.store.get(("wxxd_order", union_id), order_id))

    def list_wxxd_order_by_union_id(
        self, union_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not union_id:
            return []
        items = self.store.search(("wxxd_order", union_id), limit=limit)
        return self._search_to_dict_list(items)

    def list_all_wxxd_order(
        self, after_yyyy_mm_dd: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        filt = {"YYYYMMDD": {"$gte": after_yyyy_mm_dd}} if after_yyyy_mm_dd else {}
        items = self.store.search(("wxxd_order",), filter=filt, limit=limit)
        return self._search_to_dict_list(items)

    # ==================== 全局状态 / 通用 ====================

    def get_wecom_global_state(self, key: str) -> Any:
        return self._item_to_dict(self.store.get(("wecom_global_state",), key))

    def search_items(
        self,
        namespace: List[str],
        filter: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        items = self.store.search(tuple(namespace), filter=filter or {}, limit=limit)
        return self._search_to_dict_list(items)

    def list_all_namespace(self, limit: int = 100) -> list:
        return self.store.list_namespaces(limit=limit)


def create_wecom_store_api(
    database_uri: Optional[str] = None,
    *,
    url: Optional[str] = None,
    user_id: Optional[str] = None,
    password: Optional[str] = None,
) -> WecomStoreAPI:
    """创建 Store 客户端。

    新用法：``create_wecom_store_api(database_uri=...)`` 或配置 ``DATABASE_URI``。

    旧参数 ``url`` / ``user_id`` / ``password`` 已废弃，保留仅为兼容旧调用。
    """
    if url or user_id or password:
        import warnings

        warnings.warn(
            "WECOM_SERVER_URL / WECOM_USER_ID / WECOM_PASSWORD 已废弃，"
            "请改用 DATABASE_URI 直连 PostgresStore。",
            DeprecationWarning,
            stacklevel=2,
        )
    return WecomStoreAPI(database_uri=database_uri)
