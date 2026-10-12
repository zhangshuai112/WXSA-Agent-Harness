# 导入操作系统模块，用于路径操作（虽然导入了但可能未使用）
import os
# 导入系统模块，用于路径操作
import sys
# 导入类型提示模块，用于类型注解（Dict、Any 类型）
from typing import Dict, Any

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入微信小店订单同步服务类，用于同步订单数据
from wechat_sync.wechat_shop_sync import WechatShopSync
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录微信小店通知处理相关的日志信息
logger = setup_logging("wechat_shop_handler")

# 微信小店通知处理器类，用于处理微信小店订单通知
class WeChatShopHandler:
    """微信小店通知处理器
    
    功能：当微信小店有新订单产生时，触发此处理器
    处理流程：
    1. 接收微信小店推送的订单通知
    2. 调用同步服务，同步订单数据
    3. 将订单数据写入 LangGraph Store
    """
    
    # 初始化方法，创建处理器实例
    def __init__(self):
        """
        初始化处理器，创建同步服务实例
        """
        # 创建微信小店订单同步服务实例（用于同步订单数据）
        self.sync_service = WechatShopSync()
    
    # 处理微信小店通知的方法
    def handle(self, msg_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理微信小店通知
        
        触发场景：当微信小店有新订单产生时（channels_ec_order_new 事件），
                  微信小店会推送通知，此方法会被调用来处理通知。
        
        Args:
            msg_info (Dict[str, Any]): 解析后的消息信息，包含以下字段：
                - Event: 事件类型（channels_ec_order_new）
                - order_info: 订单信息（包含 order_id）
                - 其他字段...
            
        Returns:
            Dict[str, Any]: 处理结果，包含：
                - success: 是否处理成功
                - message: 处理结果消息
                - sync_result: 同步结果统计
        """
        try:
            logger.info("处理微信小店通知...")
            
            # 无消息过滤条件，直接处理（订单通知时，同步所有新订单）
            logger.info("同步微信小店订单...")
            
            # 调用同步服务，同步订单数据
            # sync_orders 会从微信小店 API 获取新订单，并写入 LangGraph Store
            sync_result = self.sync_service.sync_orders()
            
            # 返回成功结果，包含同步结果统计
            return {
                'success': True,
                'message': '微信小店订单同步完成',
                'sync_result': sync_result  # 包含 total_orders、processed_orders、error_orders 等统计信息
            }
            
        except Exception as e:
            # 如果处理过程中发生异常，记录错误并返回失败结果
            error_msg = f"处理微信小店通知失败: {e}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }


def main():
    """测试函数"""
    try:
        # 初始化处理器
        handler = WeChatShopHandler()
        
        print("微信小店通知处理器测试")
        print("=" * 50)
        
        # 模拟消息信息
        msg_info = {
            'msg_source': 'wxxd',
            'CreateTime': 1752471174,
            'Event': 'channels_ec_order_new',
            'FromUserName': 'oaznn7JsSvZ-3prthpwkLts_vLR8',
            'MsgType': 'event',
            'ToUserName': 'gh_55bc28346bc8',
            'order_info': {
                'order_id': 3729486243659133696
            }
        }
        
        print("测试处理微信小店通知...")
        result = handler.handle(msg_info)
        print(f"处理结果: {result}")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
