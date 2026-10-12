# 导入操作系统模块，用于环境变量和路径操作
import os
# 导入系统模块，用于路径操作
import sys
# 导入时间模块，用于时间戳操作
import time
# 导入类型提示模块，用于类型注解（List、Dict、Any 类型）
from typing import List, Dict, Any

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 导入存储 API 客户端类，用于将订单数据写入 LangGraph Store
from wechat_sync.wecom_store_api import create_wecom_store_api
# 导入微信小店 API 客户端类，用于调用微信小店 API 获取订单数据
from wechat_client.wechat_shop_api import WechatShopAPI
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录微信小店订单同步相关的日志信息
logger = setup_logging("wechat_shop_sync")

# 微信小店订单同步服务类，负责从微信小店 API 获取订单数据并同步到 LangGraph Store
class WechatShopSync:
    """微信小店订单同步服务
    
    主要功能：
    - 从微信小店 API 获取订单列表
    - 将订单数据同步到 LangGraph Store
    - 管理同步时间戳（记录上次同步时间，避免重复同步）
    - 支持增量同步（只同步新订单）
    """
    
    # 初始化方法，创建同步服务实例
    def __init__(self):
        """
        初始化同步服务，创建必要的 API 客户端实例
        """
        # 创建微信小店 API 客户端实例（用于调用微信小店 API）
        self.wechat_shop_api = WechatShopAPI()
        # 创建存储 API 客户端实例（用于将订单数据写入 LangGraph Store）
        # 从环境变量中读取服务器地址、用户ID和密码
        self.wecom_store_api = create_wecom_store_api()
        # 全局状态键名，用于存储上次同步时间（存储在 LangGraph Store 的全局状态中）
        self.start_time_key = "wechat_shop_last_sync_time"
    
    def get_last_sync_time(self) -> int:
        """
        从全局状态中获取上次同步的时间
        
        Returns:
            int: 上次同步的时间戳，如果没有则返回7天前的时间
        """
        current_time = int(time.time())
        try:
            result = self.wecom_store_api.get_wecom_global_state(self.start_time_key)
            if result and isinstance(result, dict):
                return result.get("last_sync_time", 0)
            return current_time - 7 * 24 * 3600
        except Exception as e:
            logger.error(f"获取上次同步时间失败: {e}")
            return current_time - 7 * 24 * 3600
    
    def save_last_sync_time(self, last_sync_time: int) -> None:
        """
        保存最新的同步时间到全局状态
        
        Args:
            sync_time: 要保存的同步时间戳
        """
        try:
            value = {"last_sync_time": last_sync_time}
            self.wecom_store_api.upsert_wecom_global_state(self.start_time_key, value)
            logger.info(f"保存最新同步时间: {last_sync_time}")
        except Exception as e:
            logger.error(f"保存同步时间失败: {e}")
    
    def calculate_sync_time_range(self) -> tuple:
        """
        计算同步时间范围
        
        Returns:
            tuple: (start_create_time, end_create_time)
        """
        # 获取上次同步时间作为开始时间
        start_create_time = self.get_last_sync_time()
        
        # 计算结束时间：min(now, start_create_time + 5 days)
        now = int(time.time())
        max_end_time = start_create_time + 7 * 24 * 3600  # 7天后
        end_create_time = min(now, max_end_time)
        
        logger.info(f"同步时间范围: {start_create_time} 到 {end_create_time}")
        
        return start_create_time, end_create_time
    
    def extract_order_products(self, order: Dict[str, Any]) -> List[str]:
        """
        提取订单商品名称列表
        
        Args:
            order: 订单对象
            
        Returns:
            List[str]: 商品名称列表
        """
        try:
            order_detail = order.get('order_detail', {})
            product_infos = order_detail.get('product_infos', [])
            
            products = []
            for product_info in product_infos:
                title = product_info.get('title', '')
                if title:
                    products.append(title)
            
            return products
        except Exception as e:
            logger.error(f"提取商品信息失败: {e}")
            return []
    
    def extract_order_price(self, order: Dict[str, Any]) -> float:
        """
        提取订单价格
        
        Args:
            order: 订单对象
            
        Returns:
            float: 订单价格
        """
        try:
            order_detail = order.get('order_detail', {})
            price_info = order_detail.get('price_info', {})
            order_price = price_info.get('order_price', 0)
            
            # 转换为浮点数（价格通常以分为单位，需要转换为元）
            if isinstance(order_price, (int, str)):
                return float(order_price) / 100.0
            return float(order_price)
        except Exception as e:
            logger.error(f"提取订单价格失败: {e}")
            return 0.0
    
    def process_order(self, order: Dict[str, Any]) -> bool:
        """
        处理单个订单
        
        Args:
            order: 订单数据
            
        Returns:
            bool: 处理是否成功
        """
        try:
            # 提取必要字段
            order_id = order.get('order_id', '')
            open_id = order.get('openid', '')
            union_id = order.get('unionid', '')
            order_status = order.get('status',0)
            order_create_time = order.get('create_time', 0)
            
            # 检查必要字段
            if not order_id:
                logger.error(f"订单ID为空，跳过处理")
                return False
            
            if not union_id:
                logger.error(f"订单 {order_id} 的union_id为空，跳过处理")
                return False
            
            # 提取商品信息和价格
            order_products = self.extract_order_products(order)
            order_price = self.extract_order_price(order)
            
            # 写入到WecomStoreAPI
            self.wecom_store_api.upsert_wxxd_order(
                union_id=union_id,
                order_id=order_id,
                open_id=open_id,
                order_status=order_status,
                order_products=order_products,
                order_price=order_price,
                order_create_time=order_create_time,
                order_raw_info=order  # 完整的原始order对象
            )
            
            logger.info(f"订单 {order_id} 处理成功")
            return True
            
        except Exception as e:
            logger.error(f"处理订单失败 {order.get('order_id', '')}: {e}")
            return False
    
    def sync_orders(self) -> Dict[str, Any]:
        """
        同步微信小店订单
        
        Returns:
            dict: 同步结果统计
        """
        logger.info("开始同步微信小店订单...")
        
        try:
            # 计算同步时间范围
            start_create_time, end_create_time = self.calculate_sync_time_range()
            
            # 如果开始时间已经大于等于结束时间，说明没有需要同步的数据
            if start_create_time >= end_create_time:
                logger.info("没有需要同步的订单数据")
                return {
                    'start_create_time': start_create_time,
                    'end_create_time': end_create_time,
                    'total_orders': 0,
                    'processed_orders': 0,
                    'error_orders': 0,
                    'sync_time': time.time()
                }
            
            # 获取订单列表
            order_list = self.wechat_shop_api.get_order_list(
                start_create_time=start_create_time,
                end_create_time=end_create_time
            )
            
            logger.info(f"获取到 {len(order_list)} 个订单")
            
            # 统计信息
            total_orders = len(order_list)
            processed_orders = 0
            error_orders = 0
            
            # 处理每个订单
            for order in order_list:
                if self.process_order(order):
                    processed_orders += 1
                else:
                    error_orders += 1
            
            # 更新同步时间（使用end_create_time作为下次的start_create_time）
            self.save_last_sync_time(end_create_time)
            
            result = {
                'start_create_time': start_create_time,
                'end_create_time': end_create_time,
                'total_orders': total_orders,
                'processed_orders': processed_orders,
                'error_orders': error_orders,
                'sync_time': time.time()
            }
            
            logger.info(f"订单同步完成: 总计 {total_orders} 个，"
                  f"成功处理 {processed_orders} 个，"
                  f"失败 {error_orders} 个")
            
            return result
            
        except Exception as e:
            error_msg = f"同步微信小店订单失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
    def reset_sync_time(self, start_time: str) -> None:
        """
        重置同步时间（重新开始同步）
        
        Args:
            开始时间字符串: 开始时间字符串，格式为"2025-08-18 00:00:00"
        """
        try:
            reset_time = int(time.mktime(time.strptime(start_time, "%Y-%m-%d %H:%M:%S")))
            self.save_last_sync_time(reset_time)
            logger.info(f"同步时间已重置为 {start_time}")
        except Exception as e:
            logger.error(f"重置同步时间失败: {e}")
    
    def get_sync_status(self) -> Dict[str, Any]:
        """
        获取同步状态信息
        
        Returns:
            dict: 同步状态信息
        """
        try:
            last_sync_time = self.get_last_sync_time()
            start_create_time, end_create_time = self.calculate_sync_time_range()
            
            return {
                'last_sync_time': last_sync_time,
                'next_start_time': start_create_time,
                'next_end_time': end_create_time,
                'sync_key': self.start_time_key,
                'error': ""
            }
        except Exception as e:
            return {
                'last_sync_time': 0,
                'next_start_time': 0,
                'next_end_time': 0,
                'sync_key': self.start_time_key,
                'error': str(e)
            }


def main():
    """测试函数"""
    try:
        # 初始化同步服务
        sync_service = WechatShopSync()
        
        print("微信小店订单同步测试")
        print("=" * 50)
        
        # 重置同步时间
        print("0. 重置同步时间...")
        sync_service.reset_sync_time(start_time="2025-07-14 00:00:00")

        # 显示当前同步状态
        print("1. 当前同步状态:")
        status = sync_service.get_sync_status()
        print(f"状态: {status}")
        
        # 测试同步订单
        print("2. 测试同步订单...")
        result = sync_service.sync_orders()
        print(f"同步结果: {result}")
        
        # 显示当前同步状态
        print("3. 当前同步状态:")
        status = sync_service.get_sync_status()
        print(f"状态: {status}")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
