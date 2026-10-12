"""对 Langfuse Dataset 跑真实主 Agent 测评（经 langgraph dev）。

用法（先启动 Agent，再跑本脚本）::

    cd Harness_hand_write
    langgraph dev --port 2024 --allow-blocking

    # 另开终端
    python tests/langfuse_run_eval.py --dataset test_wecom_agent

说明：
- 不要用 Langfuse UI 的「via User Interface」实验（那只测 Prompt，不跑完整 Agent）
- 本脚本会：拉取 Dataset → 逐条调用真实 Agent → 写入 Dataset Run → 本地路由打分
- UI 里挂的 LLM Judge（如 subagent_routing）若已绑定 Dataset runs，也会自动打分
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")


KNOWN_SUBAGENTS = (
    "get-customer-datas-agent",
    "wx-employee-chat-suggestion-agent",
    "update-customer-tags-or-profile-agent",
    "update-employee-schedule-agent",
)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"raw": value}
        except json.JSONDecodeError:
            return {"raw": value}
    return {"raw": value}


def _message_content(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content or "")


def _extract_final_text(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        messages = result.get("messages") or []
        for message in reversed(messages):
            msg_type = (
                message.get("type")
                if isinstance(message, dict)
                else getattr(message, "type", None)
            )
            role = (
                message.get("role")
                if isinstance(message, dict)
                else getattr(message, "role", None)
            )
            if msg_type in {"ai", "AIMessage"} or role == "assistant":
                text = _message_content(message)
                if text.strip():
                    return text
        return json.dumps(result, ensure_ascii=False, default=str)
    return str(result)


def _detect_subagents(text: str) -> list[str]:
    lowered = text.lower()
    found = [name for name in KNOWN_SUBAGENTS if name.lower() in lowered]
    return found


def subagent_routing_evaluator(*, input, output, expected_output, metadata, **kwargs):
    """本地确定性路由评估（0/1），与 Dataset expectedOutput.should_call_subagent 对齐。"""
    from langfuse import Evaluation

    expected = _as_dict(expected_output)
    want = expected.get("should_call_subagent")
    out_text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    found = _detect_subagents(out_text)

    if want in (None, "", "null"):
        ok = len(found) == 0
        comment = (
            "期望不委派子 Agent；"
            + ("实际未检测到业务子 Agent" if ok else f"实际检测到: {found}")
        )
        return Evaluation(name="subagent_routing_local", value=1.0 if ok else 0.0, comment=comment)

    ok = want in found
    comment = f"期望委派 {want}；实际检测到: {found or '无'}"
    return Evaluation(name="subagent_routing_local", value=1.0 if ok else 0.0, comment=comment)


async def _run_one_agent(
    *,
    item_input: dict[str, Any],
    langgraph_url: str,
    assistant_id: str,
) -> dict[str, Any]:
    from langgraph_sdk import get_client

    question = str(item_input.get("question") or item_input.get("raw") or "").strip()
    if not question:
        raise ValueError(f"dataset item.input 缺少 question: {item_input!r}")

    user_id = str(item_input.get("user_id") or os.getenv("USERID") or "eval-user")
    external_id = str(item_input.get("external_id") or "")
    follow_user_id = str(
        item_input.get("follow_user_id") or os.getenv("FOLLOW_USER_ID") or user_id
    )
    open_kfid = str(item_input.get("open_kfid") or os.getenv("OPEN_KFID") or "")

    context = {
        "user_id": user_id,
        "username": user_id,
        "external_id": external_id,
        "follow_user_id": follow_user_id,
    }
    if open_kfid:
        context["open_kfid"] = open_kfid

    client = get_client(url=langgraph_url)
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    result = await client.runs.wait(
        thread_id,
        assistant_id,
        input={"messages": [{"role": "human", "content": question}]},
        config={
            "configurable": {
                "user_id": user_id,
                "thread_id": thread_id,
            }
        },
        context=context,
    )

    final_text = _extract_final_text(result)
    blob = final_text + "\n" + json.dumps(result, ensure_ascii=False, default=str)
    return {
        "answer": final_text,
        "detected_subagents": _detect_subagents(blob),
        "thread_id": thread_id,
        "raw_result_type": type(result).__name__,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Langfuse Dataset × 真实 Agent 测评")
    parser.add_argument(
        "--dataset",
        default=os.getenv("LANGFUSE_EVAL_DATASET", "test_wecom_agent"),
        help="Langfuse 数据集名称",
    )
    parser.add_argument(
        "--langgraph-url",
        default=os.getenv("LANGGRAPH_URL", "http://127.0.0.1:2024"),
        help="langgraph dev 地址",
    )
    parser.add_argument(
        "--assistant-id",
        default=os.getenv("LANGGRAPH_ASSISTANT_ID", "agent"),
        help="langgraph.json 中的 graph 名",
    )
    parser.add_argument(
        "--name",
        default="",
        help="实验 run 名称（默认自动生成）",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="并发数；沙箱场景建议保持 1",
    )
    args = parser.parse_args()

    from agent.observability.langfuse_tracing import prepare_langfuse_env
    from langfuse import get_client

    prepare_langfuse_env()
    langfuse = get_client()
    dataset = langfuse.get_dataset(args.dataset)

    run_name = args.name or f"wecom-real-agent-{uuid.uuid4().hex[:8]}"

    async def task(*, item, **kwargs):
        item_input = _as_dict(item.input)
        return await _run_one_agent(
            item_input=item_input,
            langgraph_url=args.langgraph_url,
            assistant_id=args.assistant_id,
        )

    print(f"Dataset: {args.dataset}")
    print(f"LangGraph: {args.langgraph_url} / assistant={args.assistant_id}")
    print(f"Run name: {run_name}")
    print("开始测评（请确保 langgraph dev 已启动，且 OpenSandbox 可用）...")

    result = dataset.run_experiment(
        name=run_name,
        description="真实主 Agent 路由/行为回归（经 langgraph SDK）",
        task=task,
        evaluators=[subagent_routing_evaluator],
        max_concurrency=args.max_concurrency,
    )
    langfuse.flush()

    print("\n=== 结果 ===")
    try:
        print(result.format())
    except Exception:
        print(result)

    print(
        f"\n请到 Langfuse UI → Datasets → {args.dataset} → Runs 查看本次实验。"
        "若已配置 Dataset-run 规则，subagent_routing 等 LLM Judge 也会写入分数。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
