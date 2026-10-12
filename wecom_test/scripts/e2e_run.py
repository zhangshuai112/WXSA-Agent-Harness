#!/usr/bin/env python
"""端到端联调：PostgresStore → Admin → LangGraph → Sidebar。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import os

load_dotenv(ROOT / ".env.example", override=False)
load_dotenv(ROOT.parent / "wecom_sidebar" / ".env", override=False)
load_dotenv(ROOT.parent / "wecom_admin" / ".env", override=False)

LANGGRAPH_URL = os.getenv("LANGGRAPH_SERVER_URL", "http://127.0.0.1:2024")
SIDEBAR_URL = os.getenv("SIDEBAR_URL", "http://127.0.0.1:8000")
ADMIN_URL = os.getenv("ADMIN_URL", "http://127.0.0.1:5000")
WEB_USER = os.getenv("WEB_USER_ID", "admin")
WEB_PASS = os.getenv("WEB_PASSWORD", "123456")
ADMIN_USER = os.getenv("ADMIN_USER_ID", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "123456")
EXTERNAL_ID = os.getenv("EXTERNAL_ID", "wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg")
FOLLOW_USER_ID = os.getenv("FOLLOW_USER_ID", "demo_employee")
UNION_ID = "oDemoUnionId_ZhangBoss_001"

TIMEOUT = 180


def step(name: str, ok: bool, detail: str = "") -> None:
    mark = "OK" if ok else "FAIL"
    line = f"[{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def wait_url(url: str, path: str = "", retries: int = 15, interval: float = 2.0) -> bool:
    target = f"{url.rstrip('/')}{path}"
    for _ in range(retries):
        try:
            r = requests.get(target, timeout=5)
            if r.status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False


def check_langgraph() -> bool:
    try:
        r = requests.get(f"{LANGGRAPH_URL}/ok", timeout=5)
        ok = r.status_code == 200
        step("LangGraph Server", ok, LANGGRAPH_URL)
        return ok
    except requests.RequestException as exc:
        step("LangGraph Server", False, str(exc))
        return False


def check_sidebar_health() -> bool:
    try:
        r = requests.get(f"{SIDEBAR_URL}/api/health", timeout=5)
        ok = r.status_code == 200 and r.json().get("status") == "healthy"
        step("Sidebar API", ok, SIDEBAR_URL)
        return ok
    except requests.RequestException as exc:
        step("Sidebar API", False, str(exc))
        return False


def check_admin_data() -> bool:
    session = requests.Session()
    login = session.post(
        f"{ADMIN_URL}/login",
        data={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=10,
        allow_redirects=False,
    )
    if login.status_code not in (200, 302):
        step("Admin 登录", False, f"status={login.status_code}")
        return False
    step("Admin 登录", True)

    emp = session.get(f"{ADMIN_URL}/api/employees", timeout=10)
    if emp.status_code != 200:
        step("Admin 员工列表", False, f"status={emp.status_code}")
        return False
    employees = emp.json().get("data") or []
    step("Admin 员工列表", len(employees) >= 1, f"count={len(employees)}")

    customers = session.get(
        f"{ADMIN_URL}/api/employee_customers/{FOLLOW_USER_ID}",
        timeout=10,
    ).json()
    cust_list = customers.get("data") or []
    step("Admin 客户列表", len(cust_list) >= 1, f"count={len(cust_list)}")

    detail = session.get(
        f"{ADMIN_URL}/api/customer_detail/{FOLLOW_USER_ID}/{EXTERNAL_ID}",
        timeout=10,
    ).json()
    profile = (detail.get("data") or {}).get("profile") or {}
    profile_items = profile.get("profile_items") or []
    step("Admin 客户画像", len(profile_items) >= 1, f"items={len(profile_items)}")

    chats = session.get(
        f"{ADMIN_URL}/api/chat_records/{FOLLOW_USER_ID}/{EXTERNAL_ID}",
        timeout=10,
    ).json()
    chat_count = len(chats.get("data") or [])
    step("Admin 聊天记录", chat_count >= 1, f"count={chat_count}")

    orders = session.get(
        f"{ADMIN_URL}/api/customer_orders/{UNION_ID}",
        timeout=10,
    ).json()
    order_count = len(orders.get("data") or [])
    step("Admin 订单", order_count >= 1, f"count={order_count}")
    return all([employees, cust_list, profile_items, chat_count, order_count])


def sidebar_login() -> str | None:
    r = requests.post(
        f"{SIDEBAR_URL}/api/login",
        json={"username": WEB_USER, "password": WEB_PASS},
        timeout=15,
    )
    data = r.json()
    if not data.get("success"):
        step("Sidebar 登录", False, data.get("message", ""))
        return None
    token = data.get("token", "")
    step("Sidebar 登录", bool(token), f"user={WEB_USER}")
    return token


def sidebar_chat(token: str) -> bool:
    headers = {"Authorization": f"Bearer {token}"}
    prompt = "请根据当前客户张总的聊天记录，简要总结他最近的需求（一句话即可）。"
    print(f"\n>>> Agent 请求: {prompt}")
    print(">>> 等待 Agent 流式响应（最多 {}s）...\n".format(TIMEOUT))

    with requests.post(
        f"{SIDEBAR_URL}/api/send_message",
        headers=headers,
        json={"message": prompt},
        stream=True,
        timeout=TIMEOUT,
    ) as resp:
        if resp.status_code != 200:
            step("Sidebar 对话", False, f"status={resp.status_code} body={resp.text[:200]}")
            return False

        last_ai = ""
        events = 0
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            events += 1
            try:
                chunk = json.loads(raw[6:])
            except json.JSONDecodeError:
                continue
            if chunk.get("event") == "error":
                step("Sidebar 对话", False, str(chunk.get("data")))
                return False
            data = chunk.get("data")
            if isinstance(data, list):
                continue
            if not isinstance(data, dict):
                continue
            task = data.get("task_result") or {}
            text = task.get("task_result") or ""
            if text and text != last_ai:
                last_ai = text
                preview = text.replace("\n", " ")[:120]
                print(f"  ... AI: {preview}{'...' if len(text) > 120 else ''}")

        ok = len(last_ai.strip()) > 10
        step("Sidebar 对话", ok, f"events={events}, chars={len(last_ai)}")
        if ok:
            print("\n--- Agent 完整回复 ---")
            print(last_ai)
            print("--- end ---\n")
        return ok


def main() -> int:
    print("=" * 60)
    print("企微运营 Harness 端到端联调")
    print("=" * 60)
    print(f"LangGraph: {LANGGRAPH_URL}")
    print(f"Sidebar:   {SIDEBAR_URL}")
    print(f"Admin:     {ADMIN_URL}")
    print(f"客户:      {EXTERNAL_ID}")
    print(f"员工:      {FOLLOW_USER_ID}")
    print("=" * 60 + "\n")

    if not wait_url(ADMIN_URL, "/login", retries=10):
        step("Admin 启动", False, ADMIN_URL)
        return 1
    step("Admin 启动", True)

    results = [
        check_langgraph(),
        check_sidebar_health(),
        check_admin_data(),
    ]

    token = sidebar_login()
    if token:
        results.append(sidebar_chat(token))
    else:
        results.append(False)

    passed = sum(results)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"联调结果: {passed}/{total} 通过")
    print("=" * 60)
    if passed == total:
        print("\n浏览器访问:")
        print(f"  Sidebar: {SIDEBAR_URL}/wecom_web/login.html  ({WEB_USER}/{WEB_PASS})")
        print(f"  Admin:   {ADMIN_URL}/login  ({ADMIN_USER}/{ADMIN_PASS})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
