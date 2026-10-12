"""企微运营 Harness 酒类销售 Demo 场景数据。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def _yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


@dataclass
class DemoScenario:
    """一套完整的企业微信测试场景。"""

    employee_user_id: str
    employee_name: str
    external_id: str
    union_id: str
    customer_name: str
    customer_remark: str
    open_kfid: str = "wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw"
    tag_ids: List[str] = field(default_factory=list)
    profile_items: List[Dict[str, str]] = field(default_factory=list)
    tags_setting: List[Dict[str, Any]] = field(default_factory=list)
    wxqy_messages: List[Dict[str, Any]] = field(default_factory=list)
    wxkf_messages: List[Dict[str, Any]] = field(default_factory=list)
    orders: List[Dict[str, Any]] = field(default_factory=list)


def get_default_scenario(
    *,
    employee_user_id: str = "demo_employee",
    employee_name: str = "程建章",
    external_id: str = "wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg",
    union_id: str = "oDemoUnionId_ZhangBoss_001",
) -> DemoScenario:
    """构建默认 Demo：员工程建章跟进客户张总，筹备酒席买酒。"""
    now = datetime.now()
    tag_ids = ["tag_high_value", "tag_banquet", "tag_maotai_fan"]

    tags_setting = [
        {
            "tag_id": "tag_high_value",
            "tag_name": "高价值客户",
            "deleted": False,
            "strategy_id": 1,
            "group_id": "group_sales",
        },
        {
            "tag_id": "tag_banquet",
            "tag_name": "宴席场景",
            "deleted": False,
            "strategy_id": 1,
            "group_id": "group_scene",
        },
        {
            "tag_id": "tag_maotai_fan",
            "tag_name": "茅台爱好者",
            "deleted": False,
            "strategy_id": 1,
            "group_id": "group_preference",
        },
        {
            "tag_id": "tag_price_sensitive",
            "tag_name": "价格敏感",
            "deleted": False,
            "strategy_id": 1,
            "group_id": "group_preference",
        },
        {
            "tag_id": "tag_chdeleted",
            "tag_name": "已废弃标签",
            "deleted": True,
            "strategy_id": 1,
            "group_id": "group_legacy",
        },
    ]

    profile_items = [
        {"item_name": "姓名", "item_value": "张建国"},
        {"item_name": "年龄", "item_value": "52"},
        {"item_name": "性别", "item_value": "男"},
        {"item_name": "职业", "item_value": "建筑工程承包商"},
        {"item_name": "兴趣爱好", "item_value": "钓鱼、商务宴请"},
        {"item_name": "饮酒频率", "item_value": "每周2-3次"},
        {"item_name": "饮酒场景", "item_value": "商务宴请、家庭聚会、庆功宴"},
        {"item_name": "常喝的酒的种类", "item_value": "酱香型白酒"},
        {"item_name": "喜欢的酒的品牌", "item_value": "茅台、习酒"},
        {"item_name": "消费场景", "item_value": "儿子婚礼酒席、项目庆功"},
        {"item_name": "每次消费的大致金额", "item_value": "3000-8000元"},
        {"item_name": "购买渠道", "item_value": "线下专卖店、企业团购"},
    ]

    wxqy_messages = [
        _wxqy_msg(
            msg_id="wxqy_001",
            from_id=employee_user_id,
            content="张总您好，听说您儿子马上要办婚礼了，恭喜恭喜！",
            when=now - timedelta(days=3, hours=2),
        ),
        _wxqy_msg(
            msg_id="wxqy_002",
            from_id=external_id,
            content="是啊，正打算办酒席，大概30桌左右。",
            when=now - timedelta(days=3, hours=1, minutes=40),
        ),
        _wxqy_msg(
            msg_id="wxqy_003",
            from_id=employee_user_id,
            content="30桌的话，建议茅台+红标习酒搭配，既有面子又控制预算。",
            when=now - timedelta(days=2, hours=5),
        ),
        _wxqy_msg(
            msg_id="wxqy_004",
            from_id=external_id,
            content="茅台可以，习酒上次喝过觉得不错。你们能送货吗？",
            when=now - timedelta(days=2, hours=4, minutes=30),
        ),
        _wxqy_msg(
            msg_id="wxqy_005",
            from_id=employee_user_id,
            content="可以的，市区免费配送。我帮您做个详细方案？",
            when=now - timedelta(days=1, hours=3),
        ),
        _wxqy_msg(
            msg_id="wxqy_006",
            from_id=external_id,
            content="正想办个酒席庆祝一下。明天上午10点左右，我去你那里商量筹办酒席的事。",
            when=now - timedelta(minutes=35),
        ),
    ]

    wxkf_messages = [
        _wxkf_msg(
            msg_id="wxkf_001",
            external_id=external_id,
            origin=3,
            content="你好，我想咨询一下婚宴用酒有什么推荐？",
            when=now - timedelta(days=5, hours=6),
        ),
        _wxkf_msg(
            msg_id="wxkf_002",
            external_id=external_id,
            origin=5,
            content="您好！婚宴推荐茅台飞天53度或茅台1935，寓意喜庆；预算有限可选习酒窖藏1988。",
            when=now - timedelta(days=5, hours=5, minutes=55),
        ),
        _wxkf_msg(
            msg_id="wxkf_003",
            external_id=external_id,
            origin=3,
            content="30桌大概需要多少瓶？有没有团购价？",
            when=now - timedelta(days=5, hours=5, minutes=40),
        ),
        _wxkf_msg(
            msg_id="wxkf_004",
            external_id=external_id,
            origin=5,
            content="30桌建议备60-70瓶，我们可安排专属销售程经理与您对接，提供团购方案。",
            when=now - timedelta(days=5, hours=5, minutes=30),
        ),
    ]

    orders = [
        _order(
            order_id="order_20250801_001",
            products=["茅台飞天53度 500ml x2", "习酒窖藏1988 500ml x6"],
            when=now - timedelta(days=25),
        ),
        _order(
            order_id="order_20250815_002",
            products=["茅台1935 500ml x4"],
            when=now - timedelta(days=10),
        ),
    ]

    return DemoScenario(
        employee_user_id=employee_user_id,
        employee_name=employee_name,
        external_id=external_id,
        union_id=union_id,
        customer_name="张建国",
        customer_remark="张总-婚宴客户",
        tag_ids=tag_ids,
        profile_items=profile_items,
        tags_setting=tags_setting,
        wxqy_messages=wxqy_messages,
        wxkf_messages=wxkf_messages,
        orders=orders,
    )


def _wxqy_msg(*, msg_id: str, from_id: str, content: str, when: datetime) -> Dict[str, Any]:
    return {
        "msg_id": msg_id,
        "from_id": from_id,
        "content": content,
        "msg_time": _ts(when),
        "YYYYMMDD": _yyyymmdd(when),
    }


def _wxkf_msg(
    *, msg_id: str, external_id: str, origin: int, content: str, when: datetime
) -> Dict[str, Any]:
    return {
        "msg_id": msg_id,
        "external_id": external_id,
        "origin": origin,
        "content": content,
        "msg_time": _ts(when),
        "YYYYMMDD": _yyyymmdd(when),
    }


def _order(*, order_id: str, products: List[str], when: datetime) -> Dict[str, Any]:
    return {
        "order_id": order_id,
        "order_products": products,
        "order_create_time": _ts(when),
        "YYYYMMDD": _yyyymmdd(when),
    }
