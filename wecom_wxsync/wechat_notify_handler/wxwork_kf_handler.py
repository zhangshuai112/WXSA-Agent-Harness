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

# 导入企业微信客服消息同步服务类，用于同步客服消息数据
from wechat_sync.wxwork_kf_sync import WxWorkKFSync
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录客服消息通知处理相关的日志信息
logger = setup_logging("wxwork_kf_handler")

# 客服消息通知处理器类，用于处理企业微信客服消息通知
class KfMsgHandler:
    """客服消息通知处理器
    
    功能：当企业微信客服消息发生变化时（如收到新消息），触发此处理器
    处理流程：
    1. 接收企业微信推送的客服消息通知
    2. 调用同步服务，同步指定客服账号的消息数据
    3. 将客服消息数据写入 LangGraph Store
    """
    
    # 初始化方法，创建处理器实例
    def __init__(self):
        """
        初始化处理器，创建同步服务实例
        """
        # 创建企业微信客服消息同步服务实例（用于同步客服消息数据）
        self.sync_service = WxWorkKFSync()
    
    # 处理客服消息通知的方法
    def handle(self, msg_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理客服消息通知
        
        触发场景：当企业微信客服收到新消息时，企业微信会推送通知，此方法会被调用来处理通知。
        
        Args:
            msg_info (Dict[str, Any]): 解析后的消息信息，包含以下字段：
                - OpenKfId: 客服账号ID（必需）
                - 其他字段...
            
        Returns:
            Dict[str, Any]: 处理结果，包含：
                - success: 是否处理成功
                - message: 处理结果消息
                - open_kfid: 客服账号ID
                - sync_result: 同步结果统计
        """
        try:
            logger.info("处理客服消息通知...")
            
            # 获取参数：客服账号ID（用于标识是哪个客服账号收到了消息）
            open_kfid = msg_info.get('OpenKfId', '')
            # 验证必要参数是否存在
            if not open_kfid:
                # 如果缺少必要参数，返回失败结果
                return {
                    'success': False,
                    'message': '缺少必要参数 OpenKfId'
                }
            
            # 记录开始同步的日志
            logger.info(f"同步客服账号 {open_kfid} 的消息...")
            
            # 调用同步服务，同步指定客服账号的消息数据
            # sync_messages 会从企业微信 API 获取该客服账号的新消息，并写入 LangGraph Store
            sync_result = self.sync_service.sync_messages(open_kfid=open_kfid)
            
            # 返回成功结果，包含同步结果统计
            return {
                'success': True,
                'message': '客服消息同步完成',
                'open_kfid': open_kfid,
                'sync_result': sync_result  # 包含 total_messages、processed_messages、error_messages 等统计信息
            }
            
        except Exception as e:
            # 如果处理过程中发生异常，记录错误并返回失败结果
            error_msg = f"处理客服消息通知失败: {e}"
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
        handler = KfMsgHandler()
        
        print("客服消息通知处理器测试")
        print("=" * 50)
        
        # 模拟消息信息
        msg_info = {
            'msg_source': 'wecom',
            'MsgType': 'event',
            'Event': 'kf_msg_or_event',
            'ToUserName': 'ww7ca9ef3dc03a24ce',
            'CreateTime': '1348831860',
            'OpenKfId': 'wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw'
        }
        
        print("测试处理客服消息通知...")
        result = handler.handle(msg_info)
        print(f"处理结果: {result}")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
