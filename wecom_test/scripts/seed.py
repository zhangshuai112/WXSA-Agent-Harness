#!/usr/bin/env python
"""将 Demo 场景写入 PostgresStore。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenario.demo_data import get_default_scenario
from seed_store.seeder import StoreSeeder


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed PostgresStore with WeCom demo data")
    parser.add_argument("--clear", action="store_true", help="先删除本场景已有 key 再写入")
    parser.add_argument("--database-uri", default=None, help="覆盖 DATABASE_URI")
    parser.add_argument("--employee-user-id", default="demo_employee")
    parser.add_argument("--external-id", default="wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg")
    args = parser.parse_args()

    scenario = get_default_scenario(
        employee_user_id=args.employee_user_id,
        external_id=args.external_id,
    )
    seeder = StoreSeeder(database_uri=args.database_uri)
    counts = seeder.seed(scenario, clear_existing=args.clear)

    print("Demo 场景已写入 PostgresStore:")
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print()
    print("关键 ID（供 wecom_sidebar / agent 使用）:")
    print(f"  EXTERNAL_ID={scenario.external_id}")
    print(f"  employee_user_id={scenario.employee_user_id}")
    print(f"  union_id={scenario.union_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
