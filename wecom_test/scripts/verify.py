#!/usr/bin/env python
"""验证 Store 数据能否被 agent StoreClient 正确读取。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT.parent / "Harness_hand_write" / "src" / "agent"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from scenario.demo_data import get_default_scenario
from seed_store.seeder import StoreSeeder


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify demo data in PostgresStore")
    parser.add_argument("--database-uri", default=None)
    parser.add_argument("--employee-user-id", default="demo_employee")
    parser.add_argument("--external-id", default="wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg")
    parser.add_argument("--use-store-client", action="store_true", help="用 agent StoreClient 读")
    args = parser.parse_args()

    scenario = get_default_scenario(
        employee_user_id=args.employee_user_id,
        external_id=args.external_id,
    )

    seeder = StoreSeeder(database_uri=args.database_uri)
    raw = seeder.verify(scenario)
    print("=== PostgresStore 直读 ===")
    print(json.dumps(raw, ensure_ascii=False, indent=2, default=str))

    if args.use_store_client:
        from store.store_client import StoreClient

        client = StoreClient(store=seeder.store)
        ext = scenario.external_id
        emp = scenario.employee_user_id
        print("\n=== StoreClient 读 ===")
        print(
            "customer:",
            json.dumps(
                client.get_external_user_by_external_id(ext, emp),
                ensure_ascii=False,
                indent=2,
            ),
        )
        print(
            "profile:",
            json.dumps(
                client.get_profile_by_external_id(ext, emp),
                ensure_ascii=False,
                indent=2,
            ),
        )
        print(
            "tags:",
            json.dumps(client.list_all_tags_setting(), ensure_ascii=False, indent=2),
        )
        chats = client.list_last_wxqy_msg(ext, emp)
        print("chat (last 3):", json.dumps(chats[-3:], ensure_ascii=False, indent=2))
        print(
            "orders:",
            json.dumps(
                client.list_wxxd_order_by_union_id(scenario.union_id),
                ensure_ascii=False,
                indent=2,
            ),
        )

    ok = raw.get("customer") and raw.get("chat_count", 0) > 0
    print("\n结果:", "PASS" if ok else "FAIL（请先运行 scripts/seed.py）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
