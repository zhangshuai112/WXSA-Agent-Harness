"""将 Demo 场景写入 LangGraph PostgresStore。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langgraph.store.postgres import PostgresStore
from psycopg_pool import ConnectionPool

from scenario.demo_data import DemoScenario, get_default_scenario

load_dotenv()
_shared_env = Path(__file__).resolve().parents[2] / "Harness_hand_write" / ".env"
if _shared_env.exists():
    load_dotenv(_shared_env, override=False)


class StoreSeeder:
    def __init__(self, database_uri: Optional[str] = None) -> None:
        uri = database_uri or os.getenv("DATABASE_URI") or os.getenv("POSTGRES_URI_CUSTOM")
        if not uri:
            raise ValueError("缺少 DATABASE_URI，请在 .env 或 Harness_hand_write/.env 中配置")
        self._pool = ConnectionPool(
            conninfo=uri,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        self.store = PostgresStore(self._pool)
        self.store.setup()

    def seed(self, scenario: DemoScenario, *, clear_existing: bool = False) -> Dict[str, int]:
        if clear_existing:
            self._clear_scenario(scenario)

        counts = {
            "employees": 0,
            "tags_setting": 0,
            "customers": 0,
            "profiles": 0,
            "wxqy_messages": 0,
            "wxkf_messages": 0,
            "orders": 0,
        }

        self.store.put(
            ("employee",),
            scenario.employee_user_id,
            {"user_id": scenario.employee_user_id, "name": scenario.employee_name},
        )
        counts["employees"] += 1

        for tag in scenario.tags_setting:
            tag_id = tag["tag_id"]
            self.store.put(("tags_setting",), tag_id, tag)
            counts["tags_setting"] += 1

        customer = {
            "external_id": scenario.external_id,
            "union_id": scenario.union_id,
            "follow_user_id": scenario.employee_user_id,
            "name": scenario.customer_name,
            "remark_name": scenario.customer_remark,
            "tags": list(scenario.tag_ids),
        }
        self.store.put(
            ("external_user", scenario.employee_user_id),
            scenario.external_id,
            customer,
        )
        counts["customers"] += 1

        profile = {"profile_items": list(scenario.profile_items)}
        self.store.put(
            ("external_user_profile", scenario.employee_user_id),
            scenario.external_id,
            profile,
        )
        counts["profiles"] += 1

        wxqy_key = "".join(sorted([scenario.external_id, scenario.employee_user_id]))
        for msg in scenario.wxqy_messages:
            self.store.put(("wxqy_msg", wxqy_key), msg["msg_id"], msg)
            counts["wxqy_messages"] += 1

        for msg in scenario.wxkf_messages:
            self.store.put(("wxkf_msg", scenario.external_id), msg["msg_id"], msg)
            counts["wxkf_messages"] += 1

        for order in scenario.orders:
            self.store.put(("wxxd_order", scenario.union_id), order["order_id"], order)
            counts["orders"] += 1

        return counts

    def _clear_scenario(self, scenario: DemoScenario) -> None:
        """尽力删除本场景相关 key（PostgresStore 无 bulk delete 时使用）。"""
        try:
            self.store.delete(("employee",), scenario.employee_user_id)
        except Exception:
            pass

        for tag in scenario.tags_setting:
            try:
                self.store.delete(("tags_setting",), tag["tag_id"])
            except Exception:
                pass

        try:
            self.store.delete(
                ("external_user", scenario.employee_user_id),
                scenario.external_id,
            )
        except Exception:
            pass

        try:
            self.store.delete(
                ("external_user_profile", scenario.employee_user_id),
                scenario.external_id,
            )
        except Exception:
            pass

        wxqy_key = "".join(sorted([scenario.external_id, scenario.employee_user_id]))
        for msg in scenario.wxqy_messages:
            try:
                self.store.delete(("wxqy_msg", wxqy_key), msg["msg_id"])
            except Exception:
                pass

        for msg in scenario.wxkf_messages:
            try:
                self.store.delete(("wxkf_msg", scenario.external_id), msg["msg_id"])
            except Exception:
                pass

        for order in scenario.orders:
            try:
                self.store.delete(("wxxd_order", scenario.union_id), order["order_id"])
            except Exception:
                pass

    def verify(self, scenario: DemoScenario) -> Dict[str, Any]:
        wxqy_key = "".join(sorted([scenario.external_id, scenario.employee_user_id]))
        employee = self.store.get(("employee",), scenario.employee_user_id)
        customer = self.store.get(
            ("external_user", scenario.employee_user_id),
            scenario.external_id,
        )
        profile = self.store.get(
            ("external_user_profile", scenario.employee_user_id),
            scenario.external_id,
        )
        tags = self.store.search(("tags_setting",), filter={"deleted": False})
        chats = self.store.search(("wxqy_msg", wxqy_key))
        kf = self.store.search(("wxkf_msg", scenario.external_id))
        orders = self.store.search(("wxxd_order", scenario.union_id))

        return {
            "employee": getattr(employee, "value", None),
            "customer": getattr(customer, "value", None),
            "profile": getattr(profile, "value", None),
            "tag_count": len(tags or []),
            "chat_count": len(chats or []),
            "kf_count": len(kf or []),
            "order_count": len(orders or []),
        }


def seed_demo_scenario(
    *,
    database_uri: Optional[str] = None,
    clear_existing: bool = False,
    **scenario_kwargs: Any,
) -> tuple[DemoScenario, Dict[str, int]]:
    scenario = get_default_scenario(**scenario_kwargs)
    seeder = StoreSeeder(database_uri=database_uri)
    counts = seeder.seed(scenario, clear_existing=clear_existing)
    return scenario, counts
