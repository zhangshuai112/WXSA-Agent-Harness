"""LangGraph Agent 客户端（适配 Harness_hand_write / langgraph dev）。"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langgraph_sdk import get_client
from langgraph_sdk.schema import Assistant, Interrupt, Run, Thread

load_dotenv()
_shared_env = Path(__file__).resolve().parents[2] / "Harness_hand_write" / ".env"
if _shared_env.exists():
    load_dotenv(_shared_env, override=False)


def generate_stable_uuid(name: str) -> str:
    namespace_uuid = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    return str(uuid.uuid5(namespace_uuid, name))


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
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content)


def _is_ai_message(message: Any) -> bool:
    if isinstance(message, dict):
        msg_type = message.get("type") or message.get("role")
    else:
        msg_type = getattr(message, "type", None) or getattr(message, "role", None)
    return msg_type in {"ai", "assistant"}


class WecomAgentAPI:
    """封装 LangGraph SDK，连接 langgraph dev 本地服务。"""

    _client = None
    _connected = False

    thread_name_format = "{user_id}_{external_id}"

    async def connect(
        self,
        wecom_server_url: Optional[str] = None,
        wecom_user: Optional[str] = None,
        password: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
    ) -> bool:
        """连接 LangGraph Server。旧版 wecom_user/password 参数已废弃。"""
        _ = (wecom_user, password)
        try:
            server_url = (
                wecom_server_url
                or os.getenv("LANGGRAPH_SERVER_URL")
                or os.getenv("WECOM_SERVER_URL")
                or "http://127.0.0.1:2024"
            )
            headers: Dict[str, str] = {}
            token = api_key or os.getenv("LANGGRAPH_API_KEY") or os.getenv("LANGSMITH_API_KEY")
            if token:
                headers["Authorization"] = f"Bearer {token}"

            self._client = get_client(url=server_url, headers=headers)
            self._connected = True
            return True
        except Exception:
            self._connected = False
            self._client = None
            return False

    async def disconnect(self) -> None:
        self._client = None
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def create_assistant(
        self,
        graph_id: str,
        external_id: str,
        user_id: str,
    ) -> str:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")

        assistant_id_format = f"{graph_id}_{user_id}_{external_id}"
        assistant_id = generate_stable_uuid(assistant_id_format)

        assistant = await self._client.assistants.create(
            graph_id=graph_id,
            config={
                "configurable": {
                    "user_id": user_id,
                    "external_id": external_id,
                }
            },
            assistant_id=assistant_id,
            if_exists="do_nothing",
            name=f"WecomAgent_{assistant_id}",
        )
        return assistant["assistant_id"]

    async def delete_assistant(self, assistant_id: str) -> bool:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        try:
            await self._client.assistants.delete(assistant_id=assistant_id)
            return True
        except Exception:
            return False

    async def list_assistants(self) -> List[Assistant]:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        try:
            return await self._client.assistants.search(limit=100)
        except Exception:
            return []

    async def get_thread(self, user_id: str, external_id: str) -> Optional[Thread]:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        try:
            thread_id = await self.get_thread_id(user_id, external_id)
            return await self._client.threads.get(thread_id=thread_id)
        except Exception:
            return None

    async def get_thread_id(self, user_id: str, external_id: str) -> str:
        thread_name = self.thread_name_format.format(user_id=user_id, external_id=external_id)
        return generate_stable_uuid(thread_name)

    async def create_thread(self, user_id: str, external_id: str) -> Optional[str]:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        thread_id = await self.get_thread_id(user_id, external_id)
        try:
            thread = await self._client.threads.create(thread_id=thread_id, if_exists="do_nothing")
            return thread["thread_id"]
        except Exception:
            return None

    async def delete_thread(self, thread_id: str) -> bool:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        try:
            await self._client.threads.delete(thread_id=thread_id)
            return True
        except Exception:
            return False

    async def list_threads(self) -> List[Dict[str, Any]]:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        try:
            return await self._client.threads.search(limit=100)
        except Exception:
            return []

    async def has_interrupts(self, thread_id: str) -> bool:
        interrupts = await self.get_interrupts_from_thread(thread_id)
        return len(interrupts) > 0

    async def get_interrupts_from_thread(self, thread_id: str) -> List[Interrupt]:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        try:
            thread = await self._client.threads.get(thread_id=thread_id)
            return thread.get("interrupts", []) or []
        except Exception:
            return []

    async def create_background_run(
        self,
        thread_id: str,
        assistant_id: str,
        input: Optional[Dict[str, Any]] = None,
        *,
        context: Optional[Dict[str, Any]] = None,
        command: Optional[Dict[str, Any]] = None,
        multitask_strategy: str = "reject",
    ) -> Run:
        """在 Server 侧启动 run（与浏览器连接解耦）。

        使用 stream_resumable=True，前端稍后可通过 join_run_stream 订阅。
        multitask_strategy 默认 reject：同 thread 已有进行中的 run 时拒绝新建。
        """
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")

        kwargs: Dict[str, Any] = {
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "stream_mode": ["values", "messages", "updates"],
            "stream_subgraphs": True,
            "stream_resumable": True,
            "multitask_strategy": multitask_strategy,
        }
        if command is not None:
            kwargs["command"] = command
        elif input is not None:
            kwargs["input"] = input
        else:
            raise ValueError("create_background_run 需要 input 或 command")
        if context:
            kwargs["context"] = context
        return await self._client.runs.create(**kwargs)

    async def join_run_stream(
        self,
        thread_id: str,
        run_id: str,
        *,
        last_event_id: Optional[str] = None,
        stream_mode: Optional[List[str]] = None,
    ):
        """订阅已有 run 的事件流；断开连接默认不取消 run。"""
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")

        kwargs: Dict[str, Any] = {
            "thread_id": thread_id,
            "run_id": run_id,
            "cancel_on_disconnect": False,
            "stream_mode": stream_mode
            or ["values", "messages", "updates"],
        }
        if last_event_id:
            kwargs["last_event_id"] = last_event_id
        return self._client.runs.join_stream(**kwargs)

    async def get_run(self, thread_id: str, run_id: str) -> Run:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        return await self._client.runs.get(thread_id=thread_id, run_id=run_id)

    async def get_thread_state(self, thread_id: str) -> Dict[str, Any]:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        state = await self._client.threads.get_state(thread_id=thread_id)
        if isinstance(state, dict):
            return state
        # SDK 可能返回 pydantic/对象
        if hasattr(state, "model_dump"):
            return state.model_dump()
        if hasattr(state, "dict"):
            return state.dict()
        return dict(state) if state else {}

    async def create_stream_run(
        self,
        thread_id: str,
        assistant_id: str,
        input: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ):
        """兼容旧测试：流式启动。断开时继续跑（on_disconnect=continue）。"""
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        try:
            kwargs: Dict[str, Any] = {
                "thread_id": thread_id,
                "assistant_id": assistant_id,
                "input": input,
                "stream_mode": ["values", "messages", "updates"],
                "stream_subgraphs": True,
                "stream_resumable": True,
                "on_disconnect": "continue",
            }
            if context:
                kwargs["context"] = context
            return self._client.runs.stream(**kwargs)
        except Exception:
            return None

    async def resume_interrupt_run(
        self,
        thread_id: str,
        assistant_id: str,
        command: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ):
        """兼容旧测试：流式恢复中断。"""
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        try:
            kwargs: Dict[str, Any] = {
                "thread_id": thread_id,
                "assistant_id": assistant_id,
                "command": command,
                "stream_mode": ["values", "messages", "updates"],
                "stream_subgraphs": True,
                "stream_resumable": True,
                "on_disconnect": "continue",
            }
            if context:
                kwargs["context"] = context
            return self._client.runs.stream(**kwargs)
        except Exception:
            return None

    async def list_runs(self, thread_id: str) -> List[Run]:
        if not await self.is_connected():
            raise RuntimeError("客户端未连接，请先调用 connect()")
        return await self._client.runs.list(thread_id=thread_id, limit=100)


def run_to_dict(run: Any) -> Dict[str, Any]:
    """将 LangGraph Run 转为可 JSON 序列化的字典。"""
    if run is None:
        return {}
    if isinstance(run, dict):
        return {
            "run_id": run.get("run_id"),
            "thread_id": run.get("thread_id"),
            "status": run.get("status"),
            "assistant_id": run.get("assistant_id"),
            "created_at": str(run.get("created_at") or ""),
            "updated_at": str(run.get("updated_at") or ""),
        }
    return {
        "run_id": getattr(run, "run_id", None),
        "thread_id": getattr(run, "thread_id", None),
        "status": getattr(run, "status", None),
        "assistant_id": getattr(run, "assistant_id", None),
        "created_at": str(getattr(run, "created_at", "") or ""),
        "updated_at": str(getattr(run, "updated_at", "") or ""),
    }


def extract_task_result_from_values(values: Any) -> Optional[Dict[str, Any]]:
    """从 thread state.values 中提取可供前端展示的最终 AI 结果。"""
    if not isinstance(values, dict):
        return None
    messages = values.get("messages") or []
    for message in reversed(messages):
        if _is_ai_message(message):
            content = _message_content(message)
            if content:
                return {
                    "task_result": content,
                    "task_result_explain": "",
                    "task_result_code": 0,
                }
    return None


def build_agent_context(user_id: str, external_id: str, username: Optional[str] = None) -> Dict[str, str]:
    """构造 Deep Agent 运行时 context（ProcurementContext）。

    external_id 同时作为客服发送接口的 touser（旧称 customer_id）。
    open_kfid 来自环境变量 OPEN_KFID 或 DEFAULT_OPEN_KFID。
    """
    follow_user_id = os.getenv("FOLLOW_USER_ID") or user_id
    open_kfid = (
        (os.getenv("OPEN_KFID") or os.getenv("DEFAULT_OPEN_KFID") or "").strip()
    )
    ctx: Dict[str, str] = {
        "user_id": user_id,
        "username": username or user_id,
        "external_id": external_id,
        "follow_user_id": follow_user_id,
    }
    if open_kfid:
        ctx["open_kfid"] = open_kfid
    return ctx


def build_messages_input(text: str) -> Dict[str, Any]:
    """旧版 task_input → 新版 messages 协议。"""
    return {"messages": [{"role": "human", "content": text}]}


MENU_PROMPTS: Dict[str, str] = {
    "profile_suggestion": "请根据当前客户上下文，分析并给出客户画像更新建议。",
    "tag_suggestion": "请根据当前客户上下文，分析并给出客户标签更新建议。",
    "chat_suggestion": "请根据当前客户上下文，给出员工与客户的企业微信聊天回复建议。",
    "kf_chat_suggestion": "请根据当前客户上下文，给出企业微信客服聊天回复建议。",
    "schedule_suggestion": "请根据当前客户上下文，给出员工日程/跟进安排建议。",
}


def resolve_user_message(*, message: Optional[str], menu_id: Optional[str]) -> str:
    if menu_id:
        return MENU_PROMPTS.get(menu_id, menu_id)
    if message:
        return message.strip()
    raise ValueError("必须提供 message 或 menu_id")


def _task_result_payload(content: str) -> Dict[str, Any]:
    return {
        "task_result": content,
        "task_result_explain": "",
        "task_result_code": 0,
    }


def _extract_ai_content_from_messages(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if _is_ai_message(message):
            content = _message_content(message)
            if content:
                return content
    return ""


def _extract_ai_content_from_updates(data: Dict[str, Any]) -> str:
    """从 updates 载荷中提取 AI 文本。

    Deep Agent / LangGraph join_stream 常只推送 updates，例如::
        {"model": {"messages": [<AIMessage content='...'>]}}
    旧逻辑只把 updates 当成进度节点，导致前端永远停在「正在处理任务」。
    """
    for value in data.values():
        if isinstance(value, dict):
            content = _extract_ai_content_from_messages(value.get("messages"))
            if content:
                return content
        elif isinstance(value, list):
            content = _extract_ai_content_from_messages(value)
            if content:
                return content
    return ""


def adapt_stream_chunk(chunk: Any) -> Dict[str, Any]:
    """将 LangGraph 流式事件转换为旧版前端可识别的结构。"""
    event = getattr(chunk, "event", "unknown")
    data = getattr(chunk, "data", {})

    if event == "error":
        return {"event": "error", "data": data if isinstance(data, dict) else {"error": str(data)}}

    if event == "messages":
        # SDK 常见形态: (message_chunk, metadata) 或 [message, ...]
        message_chunk = data
        if isinstance(data, tuple) and data:
            message_chunk = data[0]
        elif isinstance(data, list) and data:
            message_chunk = data[-1]
            if isinstance(message_chunk, tuple) and message_chunk:
                message_chunk = message_chunk[0]
        content = _message_content(message_chunk)
        if content:
            return {
                "event": "values",
                "data": {"task_result": _task_result_payload(content)},
            }
        return {"event": event, "data": data}

    if event == "values" and isinstance(data, dict):
        adapted = dict(data)
        content = _extract_ai_content_from_messages(data.get("messages") or [])
        if content:
            adapted["task_result"] = _task_result_payload(content)
        return {"event": "values", "data": adapted}

    if event == "updates" and isinstance(data, dict):
        node_name = next(iter(data.keys()), "agent")
        payload: Dict[str, Any] = {
            "node_result": [
                {
                    "execute_node_name": node_name,
                    "execute_result_code": 0,
                    "execute_result_msg": f"正在执行: {node_name}",
                    "execute_exceptions": [],
                }
            ]
        }
        content = _extract_ai_content_from_updates(data)
        if content:
            payload["task_result"] = _task_result_payload(content)
        return {"event": "values", "data": payload}

    return {"event": event, "data": data}
