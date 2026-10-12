#!/usr/bin/env python
"""验证 wecom_wxsync 能否连接 PostgresStore 并读写同步游标。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wechat_sync.wecom_store_api import create_wecom_store_api


def main() -> int:
    api = create_wecom_store_api()
    test_key = "wxsync_smoke_test"
    api.upsert_wecom_global_state(test_key, {"ok": True, "source": "verify_store.py"})
    value = api.get_wecom_global_state(test_key)
    if value.get("ok") is True:
        print("PASS: PostgresStore 读写正常")
        return 0
    print("FAIL:", value)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
