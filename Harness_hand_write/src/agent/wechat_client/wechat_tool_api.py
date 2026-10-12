## 设置客户标签
## 设置日程
## 自建应用消息通知（人工确认机制）
##
import json
# 导入系统相关模块，用于路径操作
import sys
# 导入操作系统相关模块，用于环境变量和路径操作
import os
# 将项目根目录添加到 Python 模块搜索路径中，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入时间模块，用于时间戳操作和 token 过期时间管理
import time
# 导入 HTTP 请求库，用于调用企业微信 API
import requests
# 导入 dotenv 模块，用于从 .env 文件加载环境变量
from dotenv import load_dotenv
# 导入类型提示模块，用于类型注解（List 类型）
from typing import List
# 导入日志工具函数，用于记录日志
from utils.agent_logger import get_logger
# 导入日期时间转换工具函数，用于将日期时间字符串转换为时间戳
from utils.datetime_string import datetime2timestamp


# 导入线程模块，用于实现线程安全的单例模式
import threading
# 导入类型提示模块，用于类型注解（Optional 类型，表示可能为 None）
from typing import Optional

# 加载环境变量（从 .env 文件读取配置信息）
load_dotenv()

# 创建日志记录器，用于记录企业微信工具相关的日志信息
logger = get_logger("wechat_tool")

# 企业微信 API 服务类，封装了企业微信的各种 API 调用功能
class WxWorkAPI:
    """企业微信API服务类"""
    
    # 类变量：存储单例实例，使用 Optional 类型表示可能为 None
    _instance: Optional['WxWorkAPI'] = None
    # 类变量：线程锁，用于实现线程安全的单例模式（防止多线程环境下创建多个实例）
    _lock = threading.Lock()
    
    # 重写 __new__ 方法，实现单例模式
    def __new__(cls):
        """单例模式实现"""
        # 第一次检查：如果实例不存在，才进入同步块（提高性能，避免每次都加锁）
        if cls._instance is None:
            # 使用线程锁确保线程安全（防止多线程同时创建实例）
            with cls._lock:
                # 第二次检查：双重检查锁定模式（Double-Checked Locking）
                # 确保即使多个线程同时通过第一次检查，也只有一个线程能创建实例
                if cls._instance is None:
                    # 调用父类的 __new__ 方法创建实例
                    cls._instance = super().__new__(cls)
        # 返回单例实例
        return cls._instance


    # 初始化方法，设置企业微信 API 所需的配置信息
    def __init__(self):
        """初始化WxWorkAPI"""
        # 检查实例是否已经初始化过（防止单例模式下多次初始化）
        if hasattr(self, '_initialized'):
            # 如果已经初始化，直接返回，不重复初始化
            return
        
        # 标记实例已初始化，防止重复初始化
        self._initialized = True
        # 从环境变量中获取企业微信的企业 ID（corp_id）
        self.corp_id = os.getenv('WXWORK_CORP_ID')
        # 从环境变量中获取企业微信的应用 ID（agentid）
        self.app_id = os.getenv('WXWORK_APP_ID')
        # 从环境变量中获取企业微信的应用密钥（用于获取 access_token）
        self.app_secret = os.getenv('WXWORK_APP_SECRET')
        # 初始化 access_token 为 None（首次使用时需要获取）
        self.access_token = None
        # 初始化 token 过期时间戳为 0（表示 token 尚未获取或已过期）
        self.token_expires_time = 0
        
        # 验证必要的配置信息是否存在
        if not self.corp_id or not self.app_id or not self.app_secret:
            # 如果缺少配置信息，抛出异常，提示用户设置环境变量
            raise ValueError("请在环境变量中设置WXWORK_CORP_ID和WXWORK_APP_SECRET")
    
    # 获取企业微信 access_token 的方法（access_token 是调用企业微信 API 的凭证）
    def get_access_token(self):
        """获取access_token"""
        # 检查 token 是否过期（提前5分钟刷新，确保 token 在使用时不会过期）
        # time.time(): 获取当前时间戳（秒）
        # self.token_expires_time - 300: token 过期时间减去 300 秒（5分钟）
        if self.access_token and time.time() < (self.token_expires_time - 300):
            # 如果 token 存在且未过期，直接返回缓存的 token（避免频繁请求）
            return self.access_token
        
        # 企业微信获取 access_token 的 API 地址
        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        # 构建请求参数：企业 ID 和应用密钥
        params = {
            'corpid': self.corp_id,        # 企业 ID
            'corpsecret': self.app_secret  # 应用密钥
        }
        
        # 使用 try-except 捕获请求异常
        try:
            # 发送 GET 请求获取 access_token，设置超时时间为 30 秒
            response = requests.get(url, params=params, timeout=30)
            # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
            response.raise_for_status()
            
            # 将响应内容解析为 JSON 格式
            data = response.json()
            
            # 检查企业微信 API 返回的错误码（errcode == 0 表示成功）
            if data.get('errcode') == 0:
                # 保存获取到的 access_token
                self.access_token = data['access_token']
                # 计算 token 的过期时间戳（当前时间 + 有效期，默认 7200 秒即 2 小时）
                self.token_expires_time = time.time() + data.get('expires_in', 7200)
                # 记录成功日志，包含 token 的有效期信息
                logger.info(f"获取access_token成功，有效期：{data.get('expires_in', 7200)}秒")
                # 返回 access_token
                return self.access_token
            else:
                # 如果 API 返回错误，提取错误信息
                errmsg = data.get('errmsg', '未知错误')  # 错误消息，如果不存在则使用默认值
                errcode = data.get('errcode', 'unknown')  # 错误码，如果不存在则使用默认值
                # 构建错误消息字符串
                error_msg = f"获取access_token失败: {errmsg} (错误码: {errcode})"
                # 记录错误日志
                logger.error(error_msg)
                # 抛出异常，中断执行
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            error_msg = f"请求access_token失败: {e}"
            # 记录错误日志
            logger.error(error_msg)
            # 抛出异常，中断执行
            raise Exception(error_msg)

    #发送客服消息
    def send_kf_message(self, customer_id: str, open_kfid: str, content: str) -> dict:
        """发送客服消息
        Args:
            customer_id: 客户的id
            open_kfid: 企业微信客服的id
            content: 发送的内容
        """
        if not customer_id or not open_kfid or not content:
            raise ValueError("customer_id, open_kfid and content are required")

        access_token = self.get_access_token()
        url = "https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg"
        payload = {
            "touser": customer_id,
            "open_kfid": open_kfid,
            "msgtype": "text",
            "text": {
                "content": content
            }
        }
        try:
            response = requests.post(
                url,
                params={"access_token": access_token},
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as exc:
            logger.error("Failed to send WeCom customer-service message: %s", exc)
            raise RuntimeError("Failed to send WeCom customer-service message") from exc

        if result.get("errcode") != 0:
            error_msg = result.get("errmsg", "unknown error")
            logger.error("WeCom customer-service message rejected: %s", error_msg)
            raise RuntimeError(
                f"WeCom customer-service message rejected: {error_msg} "
                f"(errcode={result.get('errcode')})"
            )
        return result

    # 创建企业微信日程的方法
    def create_schedule(self, user_id: str, title: str, start_time: str, duration_minutes: int = 30) -> bool: 
        """创建日程
        
        Args:
            user_id (str): 员工的企业微信 user_id
            title (str): 日程标题
            start_time (str): 日程开始时间，格式为 "YYYY-MM-DD HH:MM:SS"
            duration_minutes (int): 日程持续时间（分钟），默认为 30 分钟
            
        Returns:
            bool: 创建日程是否成功（True 表示成功）
        """

        # 验证必要参数是否为空
        if not user_id or not title or not start_time:
            # 如果参数为空，抛出异常
            raise ValueError("user_id, title, start_time不能为空")

        # 将开始时间字符串转换为时间戳（秒）
        start_time_timestamp = datetime2timestamp(start_time)

        # 计算结束时间戳（开始时间戳 + 持续时间（秒））
        # duration_minutes * 60: 将分钟转换为秒
        end_time_timestamp = start_time_timestamp + duration_minutes * 60



        # 获取 access_token（调用企业微信 API 的凭证）
        access_token = self.get_access_token()
        
        # 企业微信创建日程的 API 地址
        url = f"https://qyapi.weixin.qq.com/cgi-bin/oa/schedule/add"
        # 构建请求参数：access_token
        params = {
            'access_token': access_token
        }

        ''' 日程数据格式示例（企业微信 API 要求的格式）
        {
            "schedule": {
                "admins": [                    # 日程管理员列表（可以管理日程的人员）
                    "ChengJianZhang"
                ],
                "summary": "告知客户白酒到货",  # 日程标题/摘要
                "start_time": 1752836258,       # 开始时间（时间戳，秒）
                "end_time": 1752839258,         # 结束时间（时间戳，秒）
                "attendees": [                 # 日程参与者列表
                    {
                        "userid": "ChengJianZhang"
                    }
                ]
            }
        }
        '''
        # 构建请求体数据，符合企业微信 API 格式要求
        data = {
            'schedule': {
                'admins': [user_id],           # 日程管理员：当前员工
                'summary': title,              # 日程标题
                'start_time': start_time_timestamp,  # 开始时间戳（秒）
                'end_time': end_time_timestamp,       # 结束时间戳（秒）
                'attendees': [                 # 参与者列表
                    {
                        'userid': user_id      # 参与者：当前员工
                    }
                ]
            }
        }
        
        # 设置 HTTP 请求头，指定内容类型为 JSON
        headers = {
            'Content-Type': 'application/json'
        }
        
        # 使用 try-except 捕获请求异常
        try:
            # 发送 POST 请求创建日程
            # json=data: 自动将字典序列化为 JSON 并设置 Content-Type
            # timeout=30: 设置超时时间为 30 秒
            response = requests.post(url, params=params, json=data, headers=headers, timeout=30)
            # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
            response.raise_for_status()
            
            # 将响应内容解析为 JSON 格式
            result = response.json()
            
            # 检查企业微信 API 返回的错误码（errcode == 0 表示成功）
            if result.get('errcode') == 0:
                # 创建成功，返回 True
                return True
            else:
                # 如果 API 返回错误，提取错误信息
                errmsg = result.get('errmsg', '未知错误')  # 错误消息
                errcode = result.get('errcode', 'unknown')  # 错误码
                # 构建错误消息字符串
                error_msg = f"创建日程失败: {errmsg} (错误码: {errcode})"
                # 记录错误日志
                logger.error(error_msg)
                # 抛出异常，中断执行
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            error_msg = f"请求创建日程失败: {e}"
            # 记录错误日志
            logger.error(error_msg)
            # 抛出异常，中断执行
            raise Exception(error_msg)


    # 向指定员工发送企业微信消息通知的方法
    def notify_user(self, user_id: str, content: str, title: str = '企微运营 Harness 操作确认', msgtype: str = 'text') -> bool:
        """通知指定员工

        Args:
            user_id (str): 员工的企业微信 user_id
            content (str): 通知内容
            title (str): 通知标题（仅用于 textcard 类型），默认为 '企微运营 Harness 操作确认'
            msgtype (str): 消息类型，'text' 表示文本消息，'textcard' 表示卡片消息，默认为 'text'

        Returns:
            bool: 通知是否成功（True 表示成功）
        """

        # 验证必要参数是否为空
        if not user_id or not content:
            # 如果参数为空，抛出异常
            raise ValueError("user_id, content不能为空")

        # 验证消息类型是否有效
        if msgtype not in ['text', 'textcard']:
            # 如果消息类型无效，抛出异常
            raise ValueError("msgtype must be 'text' or 'textcard'")

        # 获取 access_token（调用企业微信 API 的凭证）
        access_token = self.get_access_token()

        # 企业微信发送消息的 API 地址
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send"

        # 构建请求参数
        params = {
            'access_token': access_token,  # API 访问凭证
            'debug': 1                      # 调试模式（1 表示开启，用于测试）
        }

        '''  消息体数据格式示例（企业微信 API 要求的格式）
        文本类型（text）
        {
            "touser": "ChengJianZhang",      # 接收消息的员工 user_id
            "msgtype": "text",                # 消息类型：文本消息
            "agentid": 1000004,              # 应用 ID（agentid）
            "text": {
                "content": "消息内容"        # 文本消息内容
            },
            "safe": 1,                        # 是否保密消息（1 表示保密）
            "enable_id_trans": 1,            # 是否开启 userid 转译（1 表示开启）
            "enable_duplicate_check": 1,     # 是否开启重复消息检查（1 表示开启）
            "duplicate_check_interval": 300   # 重复消息检查时间间隔（秒）
        }

        卡片类型（textcard）
        {
            "touser": "ChengJianZhang",      # 接收消息的员工 user_id
            "msgtype": "textcard",           # 消息类型：卡片消息
            "agentid": 1000004,              # 应用 ID（agentid）
            "textcard": {
                "title": "卡片标题",         # 卡片标题
                "description": "卡片描述",   # 卡片描述（支持 HTML）
                "url": "URL",                # 点击卡片跳转的 URL
                "btntxt": "详情"             # 按钮文字
            },
            "enable_id_trans": 1,            # 是否开启 userid 转译
            "enable_duplicate_check": 1,     # 是否开启重复消息检查
            "duplicate_check_interval": 300   # 重复消息检查时间间隔（秒）
        }
        '''

        # 构建文本消息的请求体数据
        data_text = {
            'touser': user_id,                # 接收消息的员工 user_id
            'msgtype': 'text',                # 消息类型：文本消息
            'agentid': self.app_id,           # 应用 ID（从环境变量获取）
            'text': {
                'content': content           # 文本消息内容
            },
            'safe': 1,                        # 是否保密消息（1 表示保密）
            'enable_id_trans': 1,            # 是否开启 userid 转译（1 表示开启）
            'enable_duplicate_check': 1,     # 是否开启重复消息检查（1 表示开启）
            'duplicate_check_interval': 300   # 重复消息检查时间间隔（300 秒）
        }

        # 构建卡片消息的请求体数据
        data_card = {
            'touser': user_id,                # 接收消息的员工 user_id
            'msgtype': 'textcard',            # 消息类型：卡片消息
            'agentid': self.app_id,           # 应用 ID（从环境变量获取）
            'textcard': {
                'title': title,              # 卡片标题
                'description': content,       # 卡片描述（使用 content 作为描述）
                'url': 'URL'                  # 点击卡片跳转的 URL（固定值，实际使用时需要替换）
            },
            'enable_id_trans': 1,            # 是否开启 userid 转译
            'enable_duplicate_check': 1,     # 是否开启重复消息检查
            'duplicate_check_interval': 300   # 重复消息检查时间间隔（300 秒）
        }

        # 根据消息类型选择对应的数据格式
        if msgtype == 'text':
            # 如果消息类型是文本，使用文本消息数据
            data = data_text
        elif msgtype == 'textcard':
            # 如果消息类型是卡片，使用卡片消息数据
            data = data_card
        else:
            # 如果消息类型无效，记录错误日志并抛出异常
            logger.error(f"Invalid msgtype: {msgtype}")
            raise ValueError("msgtype must be 'text' or 'textcard'")

        # 设置 HTTP 请求头，指定内容类型为 JSON
        headers = {
            'Content-Type': 'application/json'
        }

        # 使用 try-except 捕获请求异常
        try:
            # 发送 POST 请求发送消息
            # json=data: 自动将字典序列化为 JSON 并设置 Content-Type
            # timeout=30: 设置超时时间为 30 秒
            response = requests.post(url, params=params, json=data, headers=headers, timeout=30)
            # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
            response.raise_for_status()
            
            # 将响应内容解析为 JSON 格式
            result = response.json()
            
            # 检查企业微信 API 返回的错误码（errcode == 0 表示成功）
            if result.get('errcode') == 0:
                # 发送成功，返回 True
                return True
            else:
                # 如果 API 返回错误，提取错误信息
                errcode = result.get('errcode', 'unknown')  # 错误码
                errmsg = result.get('errmsg', '未知错误')     # 错误消息
                # 构建错误消息字符串
                error_msg = f"发送通知失败: {errmsg} (错误码: {errcode})"
                # 记录错误日志
                logger.error(error_msg)
                # 抛出异常，中断执行
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            error_msg = f"请求发送通知失败: {e}"
            # 记录错误日志
            logger.error(error_msg)
            # 抛出异常，中断执行
            raise Exception(error_msg)


    # 更新指定员工的客户标签的方法（可以添加或删除标签）
    def update_customer_tag(self, user_id: str, external_id: str, tag_ids_add: List[str] = [], tag_ids_remove: List[str] = []) -> bool:
        """更新指定员工的客户标签， tag_ids_add和tag_ids_remove 都为空时返回成功。
        
        Args:
            user_id (str): 员工的企业微信 user_id（负责跟进该客户的员工）
            external_id (str): 外部联系人 ID（客户的企业微信外部用户 ID）
            tag_ids_add (List[str]): 需要添加的标签 ID 列表，默认为空列表
            tag_ids_remove (List[str]): 需要删除的标签 ID 列表，默认为空列表
            
        Returns:
            bool: 更新是否成功（True 表示成功）
        """

        # 验证必要参数是否为空
        if not user_id or not external_id:
            # 如果参数为空，记录错误日志并抛出异常
            logger.error("user_id, external_id不能为空")
            raise ValueError("user_id, external_id不能为空")

        # 验证是否有需要更新的标签（至少有一个列表不为空）
        if not tag_ids_add and not tag_ids_remove:
            # 如果两个列表都为空，记录错误日志并抛出异常（避免无意义的 API 调用）
            logger.error("tag_ids_add和tag_ids_removed都为空，默认返回成功")
            raise ValueError("tag_ids_add和tag_ids_removed都为空，默认返回成功")

        # 获取 access_token（调用企业微信 API 的凭证）
        access_token = self.get_access_token()
        
        # 企业微信更新客户标签的 API 地址
        url = f"https://qyapi.weixin.qq.com/cgi-bin/externalcontact/mark_tag"
        # 构建请求参数：access_token
        params = {
            'access_token': access_token
        }
        
        ''' 请求体数据格式示例（企业微信 API 要求的格式）
        {
            "userid": "zhangsan",                    # 员工的企业微信 user_id
            "external_userid": "woAJ2GCAAAd1...",    # 外部联系人 ID（客户 ID）
            "add_tag": ["TAGID1","TAGID2"],          # 需要添加的标签 ID 列表
            "remove_tag": ["TAGID3","TAGID4"]        # 需要删除的标签 ID 列表
        }
        '''

        # 构建请求体数据，符合企业微信 API 格式要求
        data = {
            'userid': user_id,              # 员工的企业微信 user_id
            'external_userid': external_id, # 外部联系人 ID（客户 ID）
            'add_tag': tag_ids_add,         # 需要添加的标签 ID 列表
            'remove_tag': tag_ids_remove     # 需要删除的标签 ID 列表
        }
        
        # 设置 HTTP 请求头，指定内容类型为 JSON
        headers = {
            'Content-Type': 'application/json'
        }
        
        # 使用 try-except 捕获请求异常
        try:
            # 发送 POST 请求更新客户标签
            # json=data: 自动将字典序列化为 JSON 并设置 Content-Type
            # timeout=30: 设置超时时间为 30 秒
            response = requests.post(url, params=params, json=data, headers=headers, timeout=30)
            # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
            response.raise_for_status()
            
            # 将响应内容解析为 JSON 格式
            result = response.json()
            
            # 检查企业微信 API 返回的错误码（errcode == 0 表示成功）
            if result.get('errcode') == 0:
                # 更新成功，返回 True
                return True
            else:
                # 如果 API 返回错误，提取错误信息
                errmsg = result.get('errmsg', '未知错误')  # 错误消息
                errcode = result.get('errcode', 'unknown')  # 错误码
                # 构建错误消息字符串
                error_msg = f"更新客户标签失败: {errmsg} (错误码: {errcode})"
                # 记录错误日志
                logger.error(error_msg)
                # 抛出异常，中断执行
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            error_msg = f"请求更新客户标签失败: {e}"
            # 记录错误日志
            logger.error(error_msg)
            # 抛出异常，中断执行
            raise Exception(error_msg)


    # 获取指定员工信息的方法（主要是获取员工姓名）
    def get_user_info(self, user_id) -> None:
        """获取指定员工的姓名
        
        Args:
            user_id (str): 员工的企业微信 user_id
            
        Returns:
            dict: 包含员工信息，格式如 {"user_id": "zhangsan", "name": "张三"}
        """
        # 获取 access_token（调用企业微信 API 的凭证）
        access_token = self.get_access_token()
        
        # 企业微信获取员工信息的 API 地址
        url = f"https://qyapi.weixin.qq.com/cgi-bin/user/get"
        # 构建请求参数
        params = {
            'access_token': access_token,  # API 访问凭证
            'userid': user_id              # 员工的企业微信 user_id
        }
        
        # 使用 try-except 捕获请求异常
        try:
            # 发送 GET 请求获取员工信息，设置超时时间为 30 秒
            response = requests.get(url, params=params, timeout=30)
            # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
            response.raise_for_status()
            
            # 将响应内容解析为 JSON 格式
            result = response.json()
            
            # 检查企业微信 API 返回的错误码（errcode == 0 表示成功）
            if result.get('errcode') == 0:
                # 提取并返回员工信息（只返回 user_id 和 name）
                return {
                    "user_id": result.get('userid', ''),  # 员工的企业微信 user_id
                    "name": result.get('name', '')         # 员工姓名
                }
            else:
                # 如果 API 返回错误，提取错误信息
                errcode = result.get('errcode', 'unknown')  # 错误码
                errmsg = result.get('errmsg', '未知错误')    # 错误消息
                # 构建错误消息字符串
                error_msg = f"获取员工信息失败: {errmsg} (错误码: {errcode})"
                # 记录错误日志
                logger.error(error_msg)
                # 抛出异常，中断执行
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            error_msg = f"请求员工信息失败: {e}"
            # 记录错误日志
            logger.error(error_msg)
            # 抛出异常，中断执行
            raise Exception(error_msg)



# 测试函数：用于测试企业微信 API 的各项功能
def main():
    """测试函数"""
    # 使用 try-except 捕获测试过程中的异常
    try:
        # 初始化企业微信 API 客户端（单例模式，多次调用返回同一个实例）
        api = WxWorkAPI()
        
        # 打印测试提示信息
        print("企业微信API测试")
        print("请确保已在.env文件中设置正确的WXWORK_CORP_ID和WXWORK_APP_SECRET")
        print("=" * 50)  # 打印分隔线
        
        # 测试 1：获取 access_token
        print("1. 测试获取access_token...")
        # 调用获取 access_token 的方法
        token = api.get_access_token()
        # 打印 access_token 的前 20 个字符（避免完整 token 泄露）
        print(f"Access Token: {token[:20]}...")
        
        # 测试 2：获取员工信息
        print("2. 测试获取员工信息...")
        # 调用获取员工信息的方法，传入测试用的 user_id
        user_info = api.get_user_info('ChengJianZhang')
        # 打印员工信息
        print(f"员工信息: {user_info}")
        
        # 测试 3：创建日程
        print("3. 测试创建日程...")
        # 调用创建日程的方法
        # 参数：员工 ID、日程标题、开始时间、持续时间（分钟）
        schedule_info = api.create_schedule('ChengJianZhang', '告知客户白酒到货', '2025-09-15 17:00:00', 30)
        # 打印创建结果
        print(f"日程信息: {schedule_info}")

        # 测试 4：发送通知
        print("4. 测试发送通知...")
        # 调用发送通知的方法
        notify_info = api.notify_user(
           user_id='ChengJianZhang',  # 接收通知的员工 ID
           msgtype='text',            # 消息类型：文本消息
           title='企微运营 Harness 操作确认',     # 通知标题（用于 textcard 类型）
           content='$userName=ChengJianZhang$，您好，我为您的客户创建了新的企业标签，您可以打开应用查看确认。')  # 通知内容
        # 打印发送结果
        print(f"通知信息: {notify_info}")
        
        # 测试 5：更新客户标签（已注释，需要真实的 external_id 和 tag_id 才能测试）
        # print("5. 测试更新客户标签...")
        # # 调用更新客户标签的方法
        # update_info = api.update_customer_tag(
        #     user_id='ChengJianZhang',  # 员工 ID
        #     external_id='wmE8gRKQAANU9ioysMc87Qd83d9bcO6g',  # 客户的外部联系人 ID
        #     tag_ids_remove=['stE8gRKQAADGVLGdmyeAyART92z5BPdQ', 'stE8gRKQAAnI1bwMxf_tvALaL5tubl8A'],  # 要删除的标签 ID 列表
        #     tag_ids_add=['etE8gRKQAAs5EIsdA7PTiTsn8GoUSkqg', 'etE8gRKQAAFomsLb5ePOTLlSb_p-Y9mA'])  # 要添加的标签 ID 列表
        # # 打印更新结果
        # print(f"更新客户标签信息: {update_info}")

    except Exception as e:
        # 如果测试过程中发生异常，打印错误信息
        print(f"测试失败: {e}")


# 如果直接运行此文件（而不是作为模块导入），则执行测试函数
if __name__ == "__main__":
    main()
