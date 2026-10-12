# 导入操作系统和系统相关模块，用于路径操作
import os,sys
# 将项目根目录添加到 Python 模块搜索路径的最前面
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# 导入 LangGraph 的存储配置函数，用于获取 LangGraph Store 实例
from langgraph.config import get_store
# 导入调试装饰器，用于在方法执行前后记录调试信息

# 导入类型提示模块，用于类型注解
from typing import List, Dict, Any, Optional
# 导入 LangGraph Store 的基础类型：SearchItem（搜索结果项）和 Item（存储项）
from langgraph.store.base import BaseStore, SearchItem, Item

# 存储客户端类，封装了对 LangGraph Store 的访问操作
class StoreClient:
    # 初始化方法，创建存储客户端实例
    def __init__(self, store: Optional[BaseStore] = None):
        # 不在模块导入阶段调用 get_store()。LangGraph Store 只在图运行时
        # 上下文中可用；显式传入 store 则可用于后台任务和单元测试。
        self._store = store

    @property
    def store(self) -> BaseStore:
        """业务数据统一走 config.STORE（PostgresStore），与 wecom_admin / wecom_test 一致。"""
        if self._store is not None:
            return self._store
        from config import STORE

        return STORE

    # ==================== 辅助工具 ====================
    # 将 LangGraph Store 的 Item 对象转换为字典的工具方法
    def item2dict(self, item: Item) -> Dict[str, Any]:
        """将 Item 对象转换为字典

        Args:
            item (Item): LangGraph Store 的 Item 对象

        Returns:
            Dict[str, Any]: 字典格式的数据，如果 item 为空则返回空字典
        """
        # 如果 item 为空，返回空字典
        if not item:
            return {}
        # 如果 item.value 是字典类型，返回其副本（避免修改原值）
        if isinstance(item.value, dict):
            return item.value.copy()  ## 避免影响原值
        # 如果 item.value 不是字典，直接返回原值
        return item.value

    # 将 SearchItem 列表转换为字典列表的工具方法
    def search_items_to_dict_list(self, searchitems: List[SearchItem]) -> List[Dict[str, Any]]:
        """将 SearchItem 列表转换为字典列表

        Args:
            searchitems (List[SearchItem]): LangGraph Store 的 SearchItem 列表

        Returns:
            List[Dict[str, Any]]: 字典列表，如果 searchitems 为空则返回空列表
        """
        # 如果 searchitems 为空，返回空列表
        if not searchitems:
            return []
        # 使用列表推导式，将每个 SearchItem 转换为字典
        return [self.item2dict(item) for item in searchitems]


    # ==================== 通用方法 ====================
    # 调试装饰器：在方法执行前后记录调试信息

    # 通用的获取存储项的方法
    def get_item(self, namespace: tuple, key: str) -> Dict[str, Any]:
        """根据命名空间和键获取存储项

        Args:
            namespace (tuple): 命名空间，用于组织数据（如 ("employee",) 表示员工数据）
            key (str): 存储项的键（唯一标识符）

        Returns:
            Dict[str, Any]: 存储项的字典格式数据，如果不存在则返回空字典
        """
        # 从存储中获取指定命名空间和键的项
        item = self.store.get(namespace, key)
        # 将 Item 对象转换为字典并返回
        return self.item2dict(item)

    # 调试装饰器：在方法执行前后记录调试信息

    # 获取所有命名空间的方法
    def get_all_namespaces(self, limit: int = 100) -> list:
        """获取所有命名空间列表

        Args:
            limit (int): 返回的最大命名空间数量，默认为 100

        Returns:
            list: 命名空间列表
        """
        # 从存储中获取所有命名空间列表
        return self.store.list_namespaces(limit=limit)

    # ==================== 员工信息 ====================

    # 调试装饰器：在方法执行前后记录调试信息

    # 根据员工 user_id 获取员工信息
    def get_employee_by_user_id(self, user_id: str) -> Dict[str, Any]:
        """根据员工 user_id 获取员工信息

        Args:
            user_id (str): 员工的企业微信 user_id

        Returns:
            Dict[str, Any]: 员工信息的字典格式数据，如果不存在则返回空字典
        """
        # 如果 user_id 为空，返回空字典
        if not user_id:
            return {}
        # 从存储中获取员工信息（命名空间为 ("employee",)，键为 user_id）
        item = self.store.get(("employee",), user_id)
        # 将 Item 对象转换为字典并返回
        return self.item2dict(item)

    # 调试装饰器：在方法执行前后记录调试信息

    # 获取所有员工信息列表
    def list_all_employee(self) -> List[Dict[str, Any]]:
        """获取所有员工信息列表

        Returns:
            List[Dict[str, Any]]: 员工信息字典列表
        """
        # 设置命名空间为员工数据命名空间
        namespace = ("employee",)
        # 在指定命名空间中搜索所有项（不设置过滤条件，返回所有员工）
        search_result = self.store.search(namespace)
        # 将 SearchItem 列表转换为字典列表并返回
        return self.search_items_to_dict_list(search_result)

    # ==================== 标签信息 ====================

    # 调试装饰器：在方法执行前后记录调试信息

    # 根据标签 ID 获取标签设置信息
    def get_tags_setting_by_tag_id(self, tag_id: str) -> Dict[str, Any]:
        """根据标签 ID 获取标签设置信息

        Args:
            tag_id (str): 标签 ID

        Returns:
            Dict[str, Any]: 标签设置的字典格式数据，如果不存在则返回空字典
        """
        # 如果 tag_id 为空，返回空字典
        if not tag_id:
            return {}
        # 从存储中获取标签设置信息（命名空间为 ("tags_setting",)，键为 tag_id）
        item = self.store.get(("tags_setting",), tag_id)
        # 将 Item 对象转换为字典并返回
        return self.item2dict(item)

    # 调试装饰器：在方法执行前后记录调试信息

    # 获取所有标签设置列表（仅返回未删除的标签）
    def list_all_tags_setting(self) -> List[Dict[str, Any]]:
        """获取所有标签设置列表（仅返回未删除的标签）

        Returns:
            List[Dict[str, Any]]: 标签设置字典列表（仅包含 deleted=False 的标签）
        """
        # 设置命名空间为标签设置数据命名空间
        namespace = ("tags_setting",)
        # 设置过滤条件：只返回 deleted 字段为 False 的标签（未删除的标签）
        filter = {"deleted": False}
        # 在指定命名空间中搜索符合条件的项
        search_result = self.store.search(namespace, filter=filter)
        # 将 SearchItem 列表转换为字典列表并返回
        return self.search_items_to_dict_list(search_result)


    # ==================== 外部客户信息 ====================
    # 调试装饰器：在方法执行前后记录调试信息

    # 根据客户 external_id 和员工 follow_user_id 获取外部客户信息
    def get_external_user_by_external_id(self, external_id: str, follow_user_id: str) -> Dict[str, Any]:
        """根据external_id获取外部客户信息

        Args:
            external_id (str): 客户的企业微信外部用户 ID
            follow_user_id (str): 负责跟进该客户的员工 user_id

        Returns:
            Dict[str, Any]: 客户信息的字典格式数据，如果不存在则返回空字典
        """

        # 验证必要参数是否为空
        if not external_id or not follow_user_id:
            # 如果参数为空，返回空字典
            return {}

        # 构建命名空间：("external_user", follow_user_id)
        # 这样可以将不同员工负责的客户数据分开存储
        namespace = ("external_user", follow_user_id)
        # 设置键为客户的 external_id
        key = external_id
        # 从存储中获取客户信息
        item = self.store.get(namespace, key)
        # 将 Item 对象转换为字典并返回
        return self.item2dict(item)

    # 调试装饰器：在方法执行前后记录调试信息

    # 根据客户 external_id 获取客户的所有标签详细信息
    def get_external_user_tag_by_external_id(self, external_id: str, follow_user_id: str) -> List[Dict[str, Any]]:
        """根据external_id和follow_user_id获取客户标签

        Args:
            external_id (str): 客户的企业微信外部用户 ID
            follow_user_id (str): 负责跟进该客户的员工 user_id

        Returns:
            List[Dict[str, Any]]: 客户标签详细信息列表（包含标签 ID 和标签名称等）
        """

        # 首先获取客户信息
        external_user = self.get_external_user_by_external_id(external_id, follow_user_id)

        # 从客户信息中提取标签 ID 列表（如果不存在则使用空列表）
        tag_ids = external_user.get("tags", [])

        # 初始化标签详细信息列表
        tag_details = []

        # 遍历标签 ID 列表
        for tag_id in tag_ids:
            # 根据标签 ID 获取标签的详细信息（包含标签名称等）
            tag = self.get_tags_setting_by_tag_id(tag_id)
            # 如果标签存在（未删除），则添加到列表中
            if tag:
                tag_details.append(tag)

        # 返回标签详细信息列表
        return tag_details

    # 调试装饰器：在方法执行前后记录调试信息

    # 根据客户 external_id 获取客户画像（profile）
    def get_profile_by_external_id(self, external_id: str, follow_user_id: str) -> Dict[str, Any]:
        """根据external_id和follow_user_id获取客户profile（客户画像）

        Args:
            external_id (str): 客户的企业微信外部用户 ID
            follow_user_id (str): 负责跟进该客户的员工 user_id

        Returns:
            Dict[str, Any]: 客户画像的字典格式数据，如果不存在则返回空字典
        """

        # 验证必要参数是否为空
        if not external_id or not follow_user_id:
            # 如果参数为空，返回空字典
            return {}

        # 构建命名空间：("external_user_profile", follow_user_id)
        # 这样可以将不同员工负责的客户画像数据分开存储
        namespace = ("external_user_profile", follow_user_id)
        # 设置键为客户的 external_id
        key = external_id
        # 从存储中获取客户画像
        item = self.store.get(namespace, key)
        # 将 Item 对象转换为字典并返回
        return self.item2dict(item)

    # 调试装饰器：在方法执行前后记录调试信息

    # 更新或插入客户画像（profile）
    def upsert_external_user_profile(self, external_id: str, follow_user_id: str, profile: Dict[str, Any]) -> bool:
        """更新外部客户信息（客户画像）

        Args:
            external_id (str): 客户的企业微信外部用户 ID
            follow_user_id (str): 负责跟进该客户的员工 user_id
            profile (Dict[str, Any]): 客户画像的字典格式数据

        Returns:
            bool: 更新是否成功（True 表示成功，False 表示失败）
        """

        # 验证必要参数是否为空
        if not external_id or not follow_user_id:
            # 如果参数为空，返回 False 表示更新失败
            return False

        # 构建命名空间：("external_user_profile", follow_user_id)
        namespace = ("external_user_profile", follow_user_id)
        # 设置键为客户的 external_id
        key = external_id
        # 将客户画像数据写入存储（如果已存在则更新，不存在则插入）
        self.store.put(namespace, key, profile)

        # 返回 True 表示更新成功
        return True

    # ==================== 聊天消息信息 ====================
    # 调试装饰器：在方法执行前后记录调试信息

    # 获取企业微信聊天消息列表（员工与客户的对话记录）
    def list_last_wxqy_msg(self, external_id: str, follow_user_id: str, after_yyyy_mm_dd: Optional[str] = None, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
        """获取近期聊天消息内容信息（员工与客户），支持过滤条件

        Args:
            external_id (str): 客户的企业微信外部用户 ID
            follow_user_id (str): 负责跟进该客户的员工 user_id
            after_yyyy_mm_dd (Optional[str]): 可选，过滤条件：只返回此日期之后的消息（格式：YYYYMMDD）
            limit (Optional[int]): 可选，返回的最大消息数量，默认为 100

        Returns:
            List[Dict[str, Any]]: 聊天消息字典列表
        """

        # 验证必要参数是否为空
        if not external_id or not follow_user_id:
            # 如果参数为空，返回空列表
            return []

        # 构建排序后的键：将 external_id 和 follow_user_id 排序后拼接
        # 这样可以确保无论谁先谁后，都能找到同一个对话的消息
        from_to_sorted_key = "".join(sorted([external_id, follow_user_id]))
        # 构建命名空间：("wxqy_msg", from_to_sorted_key)
        # wxqy_msg 表示企业微信消息（WeChat Work Message）
        namespace = ("wxqy_msg", from_to_sorted_key)
        # 如果指定了日期过滤条件
        if after_yyyy_mm_dd:
            # 设置过滤条件：只返回 YYYYMMDD 字段大于等于指定日期的消息
            # $gte 表示大于等于（greater than or equal）
            filter = {"YYYYMMDD": {"$gte": after_yyyy_mm_dd}}
        else:
            # 如果没有指定日期过滤条件，不设置过滤条件（返回所有消息）
            filter = {}
        # 在指定命名空间中搜索符合条件的消息
        search_result = self.store.search(namespace, filter=filter, limit=limit)
        # 将 SearchItem 列表转换为字典列表并返回
        return self.search_items_to_dict_list(search_result)


    # ==================== 微信客服信息 ====================
    # 调试装饰器：在方法执行前后记录调试信息

    # 获取微信客服消息列表（客户与客服的对话记录）
    def list_last_wxkf_msg(self, external_id: str, after_yyyy_mm_dd: Optional[str] = None, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
        """获取近期微信客服信息（微信客服与客户），支持过滤条件

        Args:
            external_id (str): 客户的企业微信外部用户 ID
            after_yyyy_mm_dd (Optional[str]): 可选，过滤条件：只返回此日期之后的消息（格式：YYYYMMDD）
            limit (Optional[int]): 可选，返回的最大消息数量，默认为 100

        Returns:
            List[Dict[str, Any]]: 客服消息字典列表
        """

        # 验证必要参数是否为空
        if not external_id:
            # 如果参数为空，返回空列表
            return []

        # 构建命名空间：("wxkf_msg", external_id)
        # wxkf_msg 表示微信客服消息（WeChat KF Message）
        namespace = ("wxkf_msg", external_id)
        # 如果指定了日期过滤条件
        if after_yyyy_mm_dd:
            # 设置过滤条件：只返回 YYYYMMDD 字段大于等于指定日期的消息
            filter = {"YYYYMMDD": {"$gte": after_yyyy_mm_dd}}
        else:
            # 如果没有指定日期过滤条件，不设置过滤条件（返回所有消息）
            filter = {}
        # 在指定命名空间中搜索符合条件的消息
        search_result = self.store.search(namespace, filter=filter, limit=limit)
        # 将 SearchItem 列表转换为字典列表并返回
        return self.search_items_to_dict_list(search_result)


    # ==================== 客户订单信息 ====================
    # 调试装饰器：在方法执行前后记录调试信息

    # 根据客户 union_id 获取客户订单信息列表
    def list_wxxd_order_by_union_id(self, union_id: str, after_yyyy_mm_dd: Optional[str] = None, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
        """根据union_id获取客户订单信息列表

        Args:
            union_id (str): 客户的微信 union_id（用于跨应用识别同一用户）
            after_yyyy_mm_dd (Optional[str]): 可选，过滤条件：只返回此日期之后的订单（格式：YYYYMMDD）
            limit (Optional[int]): 可选，返回的最大订单数量，默认为 100

        Returns:
            List[Dict[str, Any]]: 订单信息字典列表
        """

        # 验证必要参数是否为空
        if not union_id:
            # 如果参数为空，返回空列表
            return []

        # 构建命名空间：("wxxd_order", union_id)
        # wxxd_order 表示微信小店订单（WeChat Shop Order）
        namespace = ("wxxd_order", union_id)

        # 如果指定了日期过滤条件
        if after_yyyy_mm_dd:
            # 设置过滤条件：只返回 YYYYMMDD 字段大于等于指定日期的订单
            filter = {"YYYYMMDD": {"$gte": after_yyyy_mm_dd}}
        else:
            # 如果没有指定日期过滤条件，不设置过滤条件（返回所有订单）
            filter = {}

        # 在指定命名空间中搜索符合条件的订单
        search_result = self.store.search(namespace, filter=filter, limit=limit)
        # 将 SearchItem 列表转换为字典列表并返回
        return self.search_items_to_dict_list(search_result)
