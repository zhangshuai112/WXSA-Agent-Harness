"""企业微信客服发送窗口与配额预检。

规则（微信客服主动回复限制）：
- 仅当客户主动发消息后的 48 小时内可回复
- 同一窗口内客服最多发送 5 条消息

数据来源：PostgresStore 命名空间 ("wxkf_msg", external_id)
- origin == 3：客户发送
- origin == 5：客服发送
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

# 客户主动联系后的可回复窗口与条数上限
KF_REPLY_WINDOW_SECONDS = 48 * 3600
KF_REPLY_MAX_OUTBOUND = 5

ORIGIN_CUSTOMER = 3
ORIGIN_KF = 5


class _WxkfMsgStore(Protocol):
    def list_last_wxkf_msg(
        self,
        external_id: str,
        after_yyyy_mm_dd: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> List[Dict[str, Any]]: ...


def _default_store_client() -> Any:
    from store.store_client import StoreClient

    return StoreClient()


def _parse_msg_time(raw: Any) -> Optional[float]:
    """将 Store 中的 msg_time 转为 UTC epoch 秒。"""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        # 毫秒时间戳兼容
        value = float(raw)
        if value > 1e12:
            value = value / 1000.0
        return value
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.isdigit():
            return _parse_msg_time(int(text))
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                # Store 展示多为东八区墙钟；按 Asia/Shanghai 解析更稳妥。
                try:
                    import pytz

                    dt = pytz.timezone("Asia/Shanghai").localize(dt)
                    return dt.timestamp()
                except Exception:
                    return dt.replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
    return None


def _filter_msgs(
    msgs: List[Dict[str, Any]],
    *,
    open_kfid: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not open_kfid:
        return list(msgs)
    return [
        m
        for m in msgs
        if not m.get("open_kfid") or str(m.get("open_kfid")) == str(open_kfid)
    ]


def evaluate_kf_send_window(
    external_id: str,
    *,
    open_kfid: Optional[str] = None,
    store_client: Optional[_WxkfMsgStore] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """评估当前是否允许发送客服消息。

    Returns:
        success=True 时含窗口与配额信息；success=False 时含 error_code / error。
    """
    if not external_id:
        return {
            "success": False,
            "error_code": "KF_MISSING_EXTERNAL_ID",
            "error": "缺少 external_id，无法校验客服会话窗口",
        }

    client = store_client or _default_store_client()
    now_ts = now if now is not None else time.time()
    # 不按日期截断：需要找到「最近一次客户主动消息」以区分无消息 vs 窗口过期
    msgs = _filter_msgs(
        client.list_last_wxkf_msg(external_id, limit=200),
        open_kfid=open_kfid,
    )

    customer_times: List[float] = []
    for msg in msgs:
        if int(msg.get("origin") or 0) != ORIGIN_CUSTOMER:
            continue
        ts = _parse_msg_time(msg.get("msg_time"))
        if ts is not None:
            customer_times.append(ts)

    if not customer_times:
        return {
            "success": False,
            "error_code": "KF_NO_CUSTOMER_MESSAGE",
            "error": (
                "未找到客户主动发送的客服消息，无法开启 48 小时回复窗口；"
                "请等待客户联系客服后再发送"
            ),
            "window_hours": 48,
            "max_outbound": KF_REPLY_MAX_OUTBOUND,
        }

    last_customer_ts = max(customer_times)
    elapsed = now_ts - last_customer_ts
    if elapsed > KF_REPLY_WINDOW_SECONDS:
        return {
            "success": False,
            "error_code": "KF_WINDOW_EXPIRED",
            "error": (
                f"距客户上次主动消息已超过 48 小时"
                f"（约 {elapsed / 3600:.1f} 小时），不能再发送客服消息"
            ),
            "window_hours": 48,
            "last_customer_msg_time": last_customer_ts,
            "elapsed_hours": round(elapsed / 3600, 2),
            "max_outbound": KF_REPLY_MAX_OUTBOUND,
        }

    window_start = last_customer_ts
    outbound = 0
    for msg in msgs:
        if int(msg.get("origin") or 0) != ORIGIN_KF:
            continue
        ts = _parse_msg_time(msg.get("msg_time"))
        if ts is None:
            continue
        if window_start <= ts <= now_ts:
            outbound += 1

    remaining = KF_REPLY_MAX_OUTBOUND - outbound
    if remaining <= 0:
        return {
            "success": False,
            "error_code": "KF_QUOTA_EXCEEDED",
            "error": (
                f"当前 48 小时窗口内客服已发送 {outbound} 条，"
                f"已达上限 {KF_REPLY_MAX_OUTBOUND} 条，不能继续发送"
            ),
            "window_hours": 48,
            "last_customer_msg_time": last_customer_ts,
            "outbound_used": outbound,
            "outbound_remaining": 0,
            "max_outbound": KF_REPLY_MAX_OUTBOUND,
        }

    return {
        "success": True,
        "window_hours": 48,
        "last_customer_msg_time": last_customer_ts,
        "elapsed_hours": round(elapsed / 3600, 2),
        "window_remaining_hours": round(
            (KF_REPLY_WINDOW_SECONDS - elapsed) / 3600, 2
        ),
        "outbound_used": outbound,
        "outbound_remaining": remaining,
        "max_outbound": KF_REPLY_MAX_OUTBOUND,
    }


def record_kf_outbound_message(
    *,
    external_id: str,
    open_kfid: str,
    content: str,
    msg_id: Optional[str] = None,
    msg_time: Optional[float] = None,
    store_client: Optional[Any] = None,
) -> None:
    """发送成功后写入 Store，保证配额统计不依赖企微回灌延迟。"""
    if not external_id:
        return
    client = store_client or _default_store_client()
    ts = int(msg_time if msg_time is not None else time.time())
    key = msg_id or f"local_kf_{uuid.uuid4().hex}"
    yyyymmdd = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")
    try:
        # 与 sync 写入保持同一时区字段习惯：用东八区日期更贴近业务日
        try:
            import pytz

            yyyymmdd = (
                datetime.fromtimestamp(ts, tz=timezone.utc)
                .astimezone(pytz.timezone("Asia/Shanghai"))
                .strftime("%Y%m%d")
            )
        except Exception:
            pass
        client.store.put(
            ("wxkf_msg", external_id),
            key,
            {
                "msg_id": key,
                "external_id": external_id,
                "open_kfid": open_kfid,
                "servicer_userid": "",
                "YYYYMMDD": yyyymmdd,
                "msg_time": ts,
                "origin": ORIGIN_KF,
                "msg_type": "text",
                "content": content,
                "source": "send_wecom_kf_message",
            },
        )
    except Exception:
        # 记账失败不回滚已发送；下次仍可能被企微同步补上
        pass
