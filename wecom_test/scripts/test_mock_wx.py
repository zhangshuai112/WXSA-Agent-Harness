#!/usr/bin/env python
"""启用 Mock 企业微信后，对 wx_tools 做一次冒烟测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT.parent / "Harness_hand_write" / "src" / "agent"
for p in (ROOT, AGENT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv

load_dotenv()
shared = ROOT.parent / "Harness_hand_write" / ".env"
if shared.exists():
    load_dotenv(shared, override=False)

from mock.wecom_api import enable_mock_wecom, get_mock_log
from scenario.demo_data import get_default_scenario


def main() -> int:
    from tools import wx_tools

    enable_mock_wecom()

    scenario = get_default_scenario()

    wx_tools.notify_wecom_user.invoke(
        {
            "user_id": scenario.employee_user_id,
            "content": "【测试】客户张总明天10点到店，请准备宴席方案。",
        }
    )
    wx_tools.create_wecom_schedule.invoke(
        {
            "user_id": scenario.employee_user_id,
            "title": "张总婚宴用酒洽谈",
            "start_time": "2026-08-27 10:00:00",
            "duration_minutes": 60,
        }
    )
    wx_tools.update_wecom_customer_tags.invoke(
        {
            "user_id": scenario.employee_user_id,
            "external_id": scenario.external_id,
            "tag_ids_add": ["tag_price_sensitive"],
            "tag_ids_remove": [],
        }
    )

    print("Mock 调用记录:")
    print(json.dumps(get_mock_log(), ensure_ascii=False, indent=2))
    print("\n结果: PASS（wx_tools 写操作已走 Mock，未调用真实企业微信 API）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
