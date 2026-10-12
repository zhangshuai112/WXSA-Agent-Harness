# 导入操作系统和系统相关模块，用于路径操作
import os,sys

import asyncio
from langchain_core.tools import tool

# 将项目根目录添加到 Python 模块搜索路径的最前面
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# 导入类型提示模块，用于类型注解
from typing import List, Dict, Any
# 导入日期时间模块，用于处理日期和时间计算
from datetime import datetime, timedelta
# 导入数据模型类（第一组）：客户信息、标签信息、聊天记录、客服聊天记录、员工信息
from state.wecom_models import CustomerInfo, TagInfo, ChatHistory, KFChatHistory, EmployeeInfo
# 导入数据模型类（第二组）：订单信息、订单历史、标签设置、聊天消息、客户画像、客户标签
from state.wecom_models import OrderInfo, OrderHistory, TagSetting, ChatMessage, CustomerProfile, CustomerTags
# 导入存储客户端类，用于访问 LangGraph Store
from store.store_client import StoreClient
# 导入日志工具函数，用于记录日志
from utils.agent_logger import get_logger
# 导入调试装饰器，用于在方法执行前后记录调试信息
# 导入时间戳转换工具函数，用于将时间戳转换为日期时间字符串
from utils.datetime_string import timestamp2datetime

# 创建存储客户端实例（单例模式，用于访问 LangGraph Store）
store_client = StoreClient()

# 创建日志记录器，用于记录存储工具相关的日志信息
logger = get_logger("store_tool")

# 调试装饰器：在方法执行前后记录调试信息

def _sync_get_employee_info(user_id: str) -> EmployeeInfo:
    """根据企业微信 user_id 获取员工信息。
    
    Args:
        user_id (str): 员工的企业微信 user_id
        
    Returns:
        员工信息对象，包含 user_id 和 name，如果获取失败则返回空对象。
    """

    # 创建空的员工信息对象
    employee_info = EmployeeInfo()
    # 从存储中获取员工信息（通过 user_id 查询）
    employee = store_client.get_employee_by_user_id(user_id)

    # 如果获取失败（返回空字典或 None）
    if not employee:
        # 记录错误日志
        logger.error(f"获取员工信息失败: {user_id}")
        # 返回空的员工信息对象
        return employee_info

    # 从字典中提取员工 user_id，如果不存在则使用空字符串
    employee_info.user_id = employee.get("user_id", "")
    # 从字典中提取员工姓名，如果不存在则使用空字符串
    employee_info.name = employee.get("name", "")

    # 返回填充好的员工信息对象
    return employee_info


# 调试装饰器：在方法执行前后记录调试信息

@tool(
    "get_employee_info",
    description=(
        "根据企业微信 user_id 获取员工信息。"
        "返回员工的 user_id 和姓名。"
        "如果查询不到员工，则返回空的员工信息对象。"
    ),
)
async def get_employee_info(user_id: str) -> EmployeeInfo:
    """根据企业微信 user_id 获取员工信息。
    
    Args:
        user_id (str): 员工的企业微信 user_id
        
    Returns:
        员工信息对象，包含 user_id 和 name，如果获取失败则返回空对象。
    """

    return await asyncio.to_thread(_sync_get_employee_info, user_id)

def _sync_get_customer_info(external_id: str, follow_user_id: str) -> CustomerInfo:
    """获取客户信息
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        
    Returns:
        CustomerInfo: 客户信息对象，如果获取失败则返回空对象
    """
    
    # 创建空的客户信息对象
    customer_info = CustomerInfo()
    
    # 验证必要参数是否为空
    if not external_id or not follow_user_id:
        # 如果参数缺失，记录错误日志
        logger.error(f"获取客户时，参数缺失: {external_id}, {follow_user_id}")
        # 返回空的客户信息对象
        return customer_info
    
    # 从存储中获取客户信息（通过 external_id 和 follow_user_id 查询）
    external_user = store_client.get_external_user_by_external_id(external_id, follow_user_id)

    # 如果获取失败（返回空字典或 None）
    if not external_user:
        # 记录错误日志
        logger.error(f"获取客户信息失败: {external_id} {follow_user_id}")
        # 返回空的客户信息对象
        return customer_info

    # 从字典中提取客户 external_id
    customer_info.external_id = external_user.get("external_id")
    # 从字典中提取客户 union_id（微信跨应用识别同一用户的 ID）
    customer_info.union_id = external_user.get("union_id")
    # 从字典中提取负责跟进该客户的员工 user_id
    customer_info.follow_user_id = external_user.get("follow_user_id")
    
    # 获取客户昵称：优先使用备注名（remark_name），如果没有则使用名称（name），都没有则使用空字符串
    customer_info.nick_name = external_user.get("remark_name", external_user.get("name", ""))

    # 返回填充好的客户信息对象
    return customer_info


# 调试装饰器：在方法执行前后记录调试信息

@tool(
    "get_customer_info",
    description=(
        "根据企业微信 external_id 和 follow_user_id 获取客户信息。"
        "返回客户的 external_id、union_id、跟进员工 user_id 和客户名称。"
        "如果查询不到客户，则返回空的客户信息对象。"
    ),
)
async def get_customer_info(external_id: str, follow_user_id: str) -> CustomerInfo:
    """获取客户信息
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        
    Returns:
        CustomerInfo: 客户信息对象，如果获取失败则返回空对象
    """
    
    return await asyncio.to_thread(_sync_get_customer_info, external_id, follow_user_id)

def _sync_get_customer_tags(external_id: str, follow_user_id: str) -> CustomerTags:
    """获取客户标签
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        
    Returns:
        CustomerTags: 客户标签对象，包含该客户的所有标签列表
    """
    
    # 从存储中获取客户标签列表（通过 external_id 和 follow_user_id 查询）
    external_user_tags = store_client.get_external_user_tag_by_external_id(external_id, follow_user_id)

    # 创建空的客户标签对象
    customer_tags = CustomerTags()
    # 遍历获取到的标签列表
    for tag in external_user_tags:
        # 从字典中提取标签 ID 和标签名称，创建 TagInfo 对象
        tag_info = TagInfo(tag_id=tag.get("tag_id"), tag_name=tag.get("tag_name"))
        # 将标签信息添加到客户标签列表中
        customer_tags.customer_tags.append(tag_info)
    # 返回填充好的客户标签对象
    return customer_tags

# 调试装饰器：在方法执行前后记录调试信息

@tool(
    "get_customer_tags",
    description=(
        "根据企业微信 external_id 和 follow_user_id 获取客户标签。"
        "返回该客户关联的全部标签 ID 和标签名称。"
    ),
)
async def get_customer_tags(external_id: str, follow_user_id: str) -> CustomerTags:
    """获取客户标签
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        
    Returns:
        CustomerTags: 客户标签对象，包含该客户的所有标签列表
    """
    
    return await asyncio.to_thread(_sync_get_customer_tags, external_id, follow_user_id)

def _sync_get_customer_profile(external_id: str, follow_user_id: str) -> CustomerProfile:
    """获取客户profile（客户画像）
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        
    Returns:
        CustomerProfile: 客户画像对象，如果获取失败则返回空对象
    """
    
    # 从存储中获取客户画像字典（通过 external_id 和 follow_user_id 查询）
    profile_dict = store_client.get_profile_by_external_id(external_id, follow_user_id)

    # 如果获取失败（返回空字典或 None）
    if not profile_dict:
        # 返回空的客户画像对象
        return CustomerProfile()
    
    # 使用 try-except 捕获数据验证异常
    try:
        # 使用 Pydantic 的 model_validate 方法将字典转换为 CustomerProfile 对象
        # 这会自动进行数据验证和类型转换
        return CustomerProfile.model_validate(profile_dict)
    except Exception as e:
        # 如果验证失败，记录错误日志
        logger.error(f"获取客户profile失败: {e}")
        # 返回空的客户画像对象
        return CustomerProfile()
    
# 调试装饰器：在方法执行前后记录调试信息

@tool(
    "get_customer_profile",
    description=(
        "根据企业微信 external_id 和 follow_user_id 获取客户画像。"
        "返回客户画像信息；如果查询不到或数据校验失败，则返回空的客户画像对象。"
    ),
)
async def get_customer_profile(external_id: str, follow_user_id: str) -> CustomerProfile:
    """获取客户profile（客户画像）
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        
    Returns:
        CustomerProfile: 客户画像对象，如果获取失败则返回空对象
    """
    
    return await asyncio.to_thread(_sync_get_customer_profile, external_id, follow_user_id)

def _sync_update_customer_profile(external_id: str, follow_user_id: str, profile: CustomerProfile) -> bool:
    """更新客户profile（客户画像）
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        profile (CustomerProfile): 要更新的客户画像对象
        
    Returns:
        bool: 更新是否成功（True 表示成功，False 表示失败）
    """
    # 验证必要参数是否为空
    if not external_id or not follow_user_id or not profile:
        # 如果参数缺失，返回 False 表示更新失败
        return False
        
    # 调用存储客户端更新客户画像
    # profile.model_dump(): 将 Pydantic 对象转换为字典格式
    # upsert: 如果存在则更新，不存在则插入
    return store_client.upsert_external_user_profile(external_id, follow_user_id, profile.model_dump())  


# 调试装饰器：在方法执行前后记录调试信息

@tool(
    "update_customer_profile",
    description=(
        "根据企业微信 external_id 和 follow_user_id 更新客户画像。"
        "需要提供 CustomerProfile 对象，返回更新是否成功。"
    ),
)
async def update_customer_profile(external_id: str, follow_user_id: str, profile: CustomerProfile) -> bool:
    """更新客户profile（客户画像）
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        profile (CustomerProfile): 要更新的客户画像对象
        
    Returns:
        bool: 更新是否成功（True 表示成功，False 表示失败）
    """
    return await asyncio.to_thread(_sync_update_customer_profile, external_id, follow_user_id, profile)

def _sync_get_chat_history(external_id: str, follow_user_id: str) -> ChatHistory:
    """获取员工/客户近期聊天记录
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        
    Returns:
        ChatHistory: 聊天记录对象，包含多条聊天消息
    """
    
    # 从存储中获取企业微信聊天消息列表（通过 external_id 和 follow_user_id 查询）
    msgs = store_client.list_last_wxqy_msg(external_id, follow_user_id)
    
    # 创建空的聊天记录对象
    chat_history = ChatHistory()

    # 如果获取失败（返回空列表）
    if not msgs:
        # 返回空的聊天记录对象
        return chat_history
    
    # 遍历获取到的消息列表
    for msg in msgs:
        # 从字典中提取消息发送者 ID
        from_id = msg.get("from_id")
        # 从字典中提取消息内容
        content = msg.get("content")
        # 从字典中提取消息时间戳，并转换为日期时间字符串格式
        msg_time = timestamp2datetime(msg.get("msg_time"))
        # 判断消息发送者：如果发送者是员工，则标记为"销售人员"，否则标记为"客户"
        if from_id == follow_user_id:
            sender = "销售人员"  # 消息发送者是员工
            receiver = "客户"      # 消息接收者是客户
        else:
            sender = "客户"        # 消息发送者是客户
            receiver = "销售人员"   # 消息接收者是员工
        
        # 创建 ChatMessage 对象并添加到聊天记录列表中
        chat_history.chat_msgs.append(ChatMessage(sender=sender, receiver=receiver, content=content, msg_time=msg_time))
    
    ## 增加模拟的员工回复（用于测试或演示，实际生产环境应该删除）
    # 添加一条20分钟前的员工回复消息
    chat_history.chat_msgs.append(
        ChatMessage(
            sender="销售人员",  # 发送者：销售人员
            receiver="客户",      # 接收者：客户
            content="程哥，这是您辛苦培养的成果，真是让人敬佩，后面如果需要庆祝一下，或者需要什么帮助，都可以找我。",  # 消息内容
            msg_time=(datetime.now() - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")  # 消息时间：当前时间减去20分钟
        )
    )

    # 添加一条10分钟前的客户回复消息
    chat_history.chat_msgs.append(
        ChatMessage(
            sender="客户",        # 发送者：客户
            receiver="销售人员",  # 接收者：销售人员
            content="正想办个酒席，庆祝一下。明天上午10点左右，我去你那里找你商量一下筹办酒席的事情。",  # 消息内容
            msg_time=(datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")  # 消息时间：当前时间减去10分钟
        )
    )



    # 返回填充好的聊天记录对象
    return chat_history



# 调试装饰器：在方法执行前后记录调试信息

@tool(
    "get_chat_history",
    description=(
        "根据企业微信 external_id 和 follow_user_id 获取员工与客户的近期聊天记录。"
        "返回按发送者和接收者整理的聊天历史。"
    ),
)
async def get_chat_history(external_id: str, follow_user_id: str) -> ChatHistory:
    """获取员工/客户近期聊天记录
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        follow_user_id (str): 负责跟进该客户的员工 user_id
        
    Returns:
        ChatHistory: 聊天记录对象，包含多条聊天消息
    """
    
    return await asyncio.to_thread(_sync_get_chat_history, external_id, follow_user_id)

def _sync_get_kf_history(external_id: str) -> KFChatHistory:
    """获取客户近期微信客服记录
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        
    Returns:
        KFChatHistory: 客服聊天记录对象，包含多条客服聊天消息
    """
    
    # 从存储中获取微信客服消息列表（通过 external_id 查询）
    msgs = store_client.list_last_wxkf_msg(external_id)
    
    # 创建空的客服聊天记录对象
    chat_history = KFChatHistory()
    # 如果获取失败（返回空列表）
    if not msgs:
        # 返回空的客服聊天记录对象
        return chat_history
    
    # 遍历获取到的消息列表
    for msg in msgs:
        # 从字典中提取客户 external_id（虽然参数已有，但这里从消息中再次提取）
        external_id = msg.get("external_id")
        # 从字典中提取消息内容
        content = msg.get("content")
        # 从字典中提取消息时间戳，并转换为日期时间字符串格式
        msg_time = timestamp2datetime(msg.get("msg_time"))
        
        # 从字典中提取消息来源标识（origin）
        # origin == 3: 表示消息来自客户
        # origin == 5: 表示消息来自客服
        origin = msg.get("origin")

        # 根据消息来源判断发送者和接收者
        if origin == 3:
            sender = "客户"    # 消息发送者是客户
            receiver = "客服"  # 消息接收者是客服
        elif origin == 5:
            sender = "客服"    # 消息发送者是客服
            receiver = "客户"  # 消息接收者是客户
        else:
            sender = "其他"    # 其他未知来源
            receiver = "其他"  # 其他未知接收者
        
        # 创建 ChatMessage 对象并添加到客服聊天记录列表中
        chat_history.kf_chat_msgs.append(ChatMessage(sender=sender, receiver=receiver, content=content, msg_time=msg_time))
    
    # 返回填充好的客服聊天记录对象
    return chat_history


# 调试装饰器：在方法执行前后记录调试信息

@tool(
    "get_kf_history",
    description=(
        "根据企业微信 external_id 获取客户与企业微信客服的近期聊天记录。"
        "返回按消息来源整理的客服聊天历史。"
    ),
)
async def get_kf_history(external_id: str) -> KFChatHistory:
    """获取客户近期微信客服记录
    
    Args:
        external_id (str): 客户的企业微信外部用户 ID
        
    Returns:
        KFChatHistory: 客服聊天记录对象，包含多条客服聊天消息
    """
    
    return await asyncio.to_thread(_sync_get_kf_history, external_id)

def _sync_get_order_history(union_id: str) -> OrderHistory:
    """获取客户订单信息
    
    Args:
        union_id (str): 客户的微信 union_id（用于跨应用识别同一用户）
        
    Returns:
        OrderHistory: 订单历史对象，包含客户的所有历史订单列表
    """
    
    # 从存储中获取微信小店订单列表（通过 union_id 查询）
    orders = store_client.list_wxxd_order_by_union_id(union_id)

    # 创建空的订单历史对象
    order_history = OrderHistory()
    # 如果获取失败（返回空列表）
    if not orders:
        # 返回空的订单历史对象
        return order_history
    
    # 遍历获取到的订单列表
    for order in orders:
        # 从字典中提取订单 ID
        order_id = order.get("order_id")
        # 从字典中提取订单商品列表
        order_products = order.get("order_products")
        # 从字典中提取订单创建时间戳，并转换为日期时间字符串格式
        order_create_time = timestamp2datetime(order.get("order_create_time"))
        # 创建 OrderInfo 对象并添加到订单历史列表中
        order_history.orders.append(OrderInfo(order_id=order_id, order_products=order_products, order_create_time=order_create_time))
    
    # 返回填充好的订单历史对象
    return order_history


# 调试装饰器：在方法执行前后记录调试信息

@tool(
    "get_order_history",
    description=(
        "根据微信 union_id 获取客户的订单历史。"
        "返回客户的订单列表、商品信息和订单创建时间。"
    ),
)
async def get_order_history(union_id: str) -> OrderHistory:
    """获取客户订单信息
    
    Args:
        union_id (str): 客户的微信 union_id（用于跨应用识别同一用户）
        
    Returns:
        OrderHistory: 订单历史对象，包含客户的所有历史订单列表
    """
    
    return await asyncio.to_thread(_sync_get_order_history, union_id)

def _sync_get_tag_setting() -> TagSetting:
    """获取标签设置（全局标签库）
    
    Returns:
        TagSetting: 标签设置对象，包含系统中所有可用的标签列表
    """
    # 从存储中获取所有标签设置列表
    settings = store_client.list_all_tags_setting()
    
    # 创建空的标签设置对象
    tag_setting = TagSetting()
    # 如果获取失败（返回空列表）
    if not settings:
        # 返回空的标签设置对象
        return tag_setting
    
    # 遍历获取到的标签设置列表
    for setting in settings:
        # 从字典中提取标签 ID
        tag_id = setting.get("tag_id")
        # 从字典中提取标签名称
        tag_name = setting.get("tag_name")
        # 创建 TagInfo 对象并添加到标签设置列表中
        tag_setting.tag_setting.append(TagInfo(tag_id=tag_id, tag_name=tag_name))
    
    # 返回填充好的标签设置对象
    return tag_setting


##更新客户标签（全量替换）

@tool(
    "get_tag_setting",
    description=(
        "获取系统中的全部客户标签配置。"
        "返回可用标签的 ID 和名称列表。"
    ),
)
async def get_tag_setting() -> TagSetting:
    """获取标签设置（全局标签库）
    
    Returns:
        TagSetting: 标签设置对象，包含系统中所有可用的标签列表
    """
    return await asyncio.to_thread(_sync_get_tag_setting)

def _sync_update_customer_tags(
    external_id: str,
    follow_user_id: str,
    tag_ids: List[str],
) -> bool:
    """更新客户标签。

    Args:
        external_id: 客户的企业微信 external_id。
        follow_user_id: 负责跟进客户的员工 user_id。
        tag_ids: 更新后应保留的完整标签 ID 列表。

    Returns:
        标签更新成功返回 True，否则返回 False。
    """
    if not external_id or not follow_user_id:
        logger.error("Updating customer tags requires external_id and follow_user_id")
        return False

    customer = store_client.get_external_user_by_external_id(
        external_id,
        follow_user_id,
    )
    if not customer:
        logger.error(
            "Customer not found while updating tags: %s %s",
            external_id,
            follow_user_id,
        )
        return False

    normalized_tag_ids = []
    seen_tag_ids = set()
    for tag_id in tag_ids or []:
        normalized_tag_id = str(tag_id).strip()
        if normalized_tag_id and normalized_tag_id not in seen_tag_ids:
            seen_tag_ids.add(normalized_tag_id)
            normalized_tag_ids.append(normalized_tag_id)

    customer["tags"] = normalized_tag_ids

    try:
        store_client.store.put(
            ("external_user", follow_user_id),
            external_id,
            customer,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to update customer tags: %s %s",
            external_id,
            follow_user_id,
        )
        return False

@tool(
    "update_customer_tags",
    description=(
        "更新客户标签。"
        "传入客户 external_id、负责员工 follow_user_id 和完整的 tag_ids 列表。"
        "该操作会用 tag_ids 全量替换客户当前标签，并返回是否更新成功。"
    ),
)
async def update_customer_tags(
    external_id: str,
    follow_user_id: str,
    tag_ids: List[str],
) -> bool:
    """更新客户标签。

    Args:
        external_id: 客户的企业微信 external_id。
        follow_user_id: 负责跟进客户的员工 user_id。
        tag_ids: 更新后应保留的完整标签 ID 列表。

    Returns:
        标签更新成功返回 True，否则返回 False。
    """
    return await asyncio.to_thread(_sync_update_customer_tags, external_id, follow_user_id, tag_ids)

store_tools = [
    get_employee_info,
    get_customer_info,
    get_customer_tags,
    get_customer_profile,
    update_customer_profile,
    get_chat_history,
    get_kf_history,
    get_order_history,
    get_tag_setting,
    update_customer_tags,
]
