  # 导入操作系统模块，用于环境变量和路径操作
import os
# 导入 JSON 处理模块，用于解析和生成 JSON 数据
import json
# 导入时间模块，用于时间戳操作和 token 过期时间管理
import time
# 导入 HTTP 请求库，用于调用微信小店 API
import requests
# 导入类型提示模块，用于类型注解（List、Dict、Any 类型）
from typing import List, Dict, Any
# 导入 dotenv 模块，用于从 .env 文件加载环境变量
from dotenv import load_dotenv
# 导入格式化打印模块，用于美化输出（调试用）
import pprint
# 导入系统模块，用于路径操作
import sys
# 将项目根目录添加到 Python 模块搜索路径中，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录微信小店 API 相关的日志信息
logger = setup_logging("wechat_shop_api")

# 加载环境变量（从 .env 文件读取配置信息，如 WXXD_APP_ID、WXXD_APP_SECRET 等）
load_dotenv()

# 微信视频号小店 API 服务类，封装了微信小店的各种 API 调用功能
class WechatShopAPI:
    """微信视频号小店API服务类
    
    提供以下功能：
    - 获取 access_token（API 访问凭证）
    - 获取订单列表（支持分页）
    - 获取订单详情
    """
    
    # 初始化方法，设置微信小店 API 所需的配置信息
    def __init__(self):
        """初始化 WechatShopAPI 实例"""
        # 从环境变量中获取微信小店的 AppID（应用ID）
        self.app_id = os.getenv('WXXD_APP_ID')
        # 从环境变量中获取微信小店的 AppSecret（应用密钥，用于获取 access_token）
        self.app_secret = os.getenv('WXXD_APP_SECRET')
        # 初始化 access_token 为 None（首次使用时需要获取）
        self.access_token = None
        # 初始化 token 过期时间戳为 0（表示 token 尚未获取或已过期）
        self.token_expires_time = 0
        
        # 验证必要的配置信息是否存在
        if not self.app_id or not self.app_secret:
            # 如果缺少配置信息，抛出异常，提示用户设置环境变量
            raise ValueError("请在环境变量中设置APP_ID和APP_SECRET")
    
    # 获取微信小店 access_token 的方法（access_token 是调用微信小店 API 的凭证）
    def get_access_token(self):
        """获取access_token（API 访问凭证）
        
        Returns:
            str: access_token 字符串，用于后续 API 调用
            
        Raises:
            Exception: 如果获取 token 失败，抛出异常
        """
        # 检查 token 是否过期（提前5分钟刷新，确保 token 在使用时不会过期）
        # time.time(): 获取当前时间戳（秒）
        # self.token_expires_time - 300: token 过期时间减去 300 秒（5分钟）
        if self.access_token and time.time() < (self.token_expires_time - 300):
            # 如果 token 存在且未过期，直接返回缓存的 token（避免频繁请求）
            return self.access_token
        
        # 微信获取 access_token 的 API 地址（使用标准的微信 access_token 接口）
        url = "https://api.weixin.qq.com/cgi-bin/token"
        # 构建请求参数：授权类型、AppID 和应用密钥
        params = {
            'grant_type': 'client_credential',  # 授权类型：客户端凭证模式
            'appid': self.app_id,                # 应用ID
            'secret': self.app_secret            # 应用密钥
        }
        
        # 使用 try-except 捕获请求异常
        try:
            # 发送 GET 请求获取 access_token，设置超时时间为 30 秒
            response = requests.get(url, params=params, timeout=30)
            # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
            response.raise_for_status()
            
            # 将响应内容解析为 JSON 格式
            data = response.json()
            
            # 检查响应中是否包含 access_token（微信 API 成功时直接返回 access_token 字段）
            if 'access_token' in data:
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
                errmsg = data.get('errmsg', '未知错误')  # 错误消息
                errcode = data.get('errcode', 'unknown')  # 错误码
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
    

    # 获取订单列表的方法（支持按时间范围查询和分页）
    def get_order_list(self, start_create_time: int, end_create_time: int) -> List[Dict[str, Any]]:
        """获取订单列表（支持分页，自动获取所有订单的详情）
        
        Args:
            start_create_time (int): 订单创建开始时间戳（秒）
            end_create_time (int): 订单创建结束时间戳（秒）
            
        Returns:
            List[Dict[str, Any]]: 订单详情列表（每个订单是一个字典，包含完整的订单信息）
        """
        # 获取 access_token（调用微信小店 API 的凭证）
        access_token = self.get_access_token()
        # 微信小店获取订单列表的 API 地址
        url = f"https://api.weixin.qq.com/channels/ec/order/list/get"

        # 初始化变量：订单ID列表、分页游标、是否还有更多数据
        order_list = []          # 订单ID列表（从API获取的是订单ID，需要再调用详情接口获取完整信息）
        next_key = ""            # 分页游标（用于获取下一页数据）
        has_more = True          # 是否还有更多数据（用于控制循环）
        
        # 构建请求体数据
        data = {
            "create_time_range": {        # 订单创建时间范围
                "start_time": start_create_time,  # 开始时间戳
                "end_time": end_create_time      # 结束时间戳
            },
            "page_size": 100,             # 每页返回的订单数量（最大100）
            "next_key": next_key          # 分页游标（第一次请求传空字符串）
        }
        # 构建请求参数
        params = {
            "access_token": access_token  # API 访问凭证
        }
        
        # 循环获取所有分页的订单ID（直到没有更多数据）
        while has_more:
            try:
                # 更新请求体中的 next_key（用于获取下一页数据）
                data["next_key"] = next_key
                # 发送 POST 请求获取订单列表，设置超时时间为 30 秒
                response = requests.post(url, json=data, params=params, timeout=30)

                # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
                response.raise_for_status()
                # 将响应内容解析为 JSON 格式
                result = response.json()
                
                # 检查微信 API 返回的错误码（errcode == 0 表示成功）
                if result.get('errcode') == 0:
                    # 将当前页的订单ID列表添加到总列表中
                    order_list.extend(result.get('order_id_list', []))
                    # 获取下一页的游标（用于下次请求）
                    next_key = result.get('next_key', "")
                    # 判断是否还有更多数据
                    has_more = result.get('has_more', False)
                else:
                    # 如果 API 返回错误，停止循环
                    has_more = False
                    # 记录错误日志
                    logger.error(f"获取订单列表失败: {result} ")
            except Exception as e:
                # 捕获异常，停止循环
                logger.error(f"获取订单列表异常: {e}")
                has_more = False

        # 初始化订单详情列表（用于存储完整的订单信息）
        order_detail_list = []

        # 记录获取到的订单ID列表（用于调试）
        logger.info(f"获取订单列表: {order_list} ")

        # 遍历订单ID列表，调用详情接口获取每个订单的完整信息
        for order_id in order_list:
            # 获取订单详情（调用 get_order_detail 方法）
            order_detail = self.get_order_detail(order_id)
            # 将订单详情添加到列表中
            order_detail_list.append(order_detail)

        # 返回订单详情列表
        return order_detail_list
    


    # 获取订单详情的方法
    def get_order_detail(self, order_id: str) -> Dict[str, Any]:
        """获取订单详情
        
        Args:
            order_id (str): 订单ID
            
        Returns:
            Dict[str, Any]: 订单详情字典，包含订单的所有信息（商品、价格、状态等）
            
        Raises:
            Exception: 如果获取订单详情失败，抛出异常
        """
        # 获取 access_token（调用微信小店 API 的凭证）
        access_token = self.get_access_token()
        
        # 微信视频号小店获取订单详情的 API 地址
        url = f"https://api.weixin.qq.com/channels/ec/order/get"
        
        # 构建请求体数据
        data = {
            "order_id": order_id  # 订单ID
        }
        # 构建请求参数
        params = {
            "access_token": access_token  # API 访问凭证
        }
        
        # 使用 try-except 捕获请求异常
        try:
            # 发送 POST 请求获取订单详情，设置超时时间为 30 秒
            response = requests.post(url, json=data, params=params, timeout=30)
            # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
            response.raise_for_status()
            
            # 将响应内容解析为 JSON 格式
            result = response.json()
            
            # 检查微信 API 返回的错误码（errcode == 0 表示成功）
            if result.get('errcode') == 0:
                # 返回订单详情（从响应的 order 字段中提取）
                return result.get('order', {})
            else:
                # 如果 API 返回错误，提取错误信息
                errmsg = result.get('errmsg', '未知错误')  # 错误消息
                errcode = result.get('errcode', 'unknown')  # 错误码
                # 构建错误消息字符串
                error_msg = f"获取订单详情失败: {errmsg} (错误码: {errcode})"
                # 记录错误日志
                logger.error(error_msg)
                # 抛出异常，中断执行
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            error_msg = f"请求订单详情失败: {e}"
            # 记录错误日志
            logger.error(error_msg)
            # 抛出异常，中断执行
            raise Exception(error_msg)
        
if __name__ == "__main__":
    api = WechatShopAPI()
    start_create_time = int(time.mktime(time.strptime("2025-07-01 00:00:00", "%Y-%m-%d %H:%M:%S")))
    end_create_time = start_create_time + 24 * 3600
    order_list = api.get_order_list(start_create_time, end_create_time)

    for order in order_list:
        pprint.pprint(order)
        logger.info("-" * 100)