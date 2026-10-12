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

# 导入企业微信会话存档消息同步服务类和同步标志常量
from wechat_sync.wxwork_msgaudit_sync import WxWorkMsgAuditSync, SYNC_FLAG_VALUE
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录会话存档通知处理相关的日志信息
logger = setup_logging("wxwork_msgaudit_handler")

# 会话存档通知处理器类，用于处理企业微信会话存档通知
class MsgAuditHandler:
    """会话存档通知处理器
    
    功能：当企业微信会话存档有新消息需要同步时，触发此处理器
    处理流程：
    1. 接收企业微信推送的会话存档通知
    2. 设置同步标志，标记有新消息需要同步
    3. 实际的同步工作由独立的同步服务进程完成（因为会话存档 SDK 使用 C 语言库）
    """
    
    # 初始化方法，创建处理器实例
    def __init__(self):
        """
        初始化处理器，创建同步服务实例
        """
        # 创建企业微信会话存档消息同步服务实例（用于管理同步标志）
        self.sync_service = WxWorkMsgAuditSync()
    
    # 处理会话存档通知的方法
    def handle(self, msg_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理会话存档通知
        
        触发场景：当企业微信会话存档有新消息需要同步时，企业微信会推送通知，
                  此方法会被调用来设置同步标志。
        
        注意：实际的同步工作不在通知处理时执行，而是由独立的同步服务进程完成
              （因为会话存档 SDK 使用 C 语言库，需要在独立进程中运行）
        
        Args:
            msg_info (Dict[str, Any]): 解析后的消息信息，包含以下字段：
                - Event: 事件类型（msgaudit_notify）
                - AgentID: 应用ID
                - 其他字段...
            
        Returns:
            Dict[str, Any]: 处理结果，包含：
                - success: 是否处理成功
                - message: 处理结果消息
                - sync_result: 同步标志信息
        """
        try:
            logger.info("处理会话存档通知...")
            
            # 无消息过滤条件，直接处理（所有会话存档通知都触发同步标志设置）
            logger.info("同步会话存档消息...")

            # 调用处理接口：设置同步标志，标记有新消息需要同步
            # 注意：实际的消息同步由独立的同步服务进程完成，这里只设置标志
            #sync_result = self.sync_service.sync_messages()  # 注释掉，不在通知处理时同步
            # 保存同步标志，标记有新消息需要同步（值为 1）
            self.sync_service.save_sync_flag(SYNC_FLAG_VALUE)

            # 获取当前同步标志（用于确认是否设置成功）
            sync_flag = self.sync_service.get_sync_flag()
            sync_result = {"sync_flag": sync_flag}

            # 返回成功结果（说明同步标志已设置，同步服务进程会检测到标志并执行同步）
            return {
                'success': True,
                'message': '会话存档消息标志已保存，正在同步消息...',
                'sync_result': sync_result
            }
            
        except Exception as e:
            # 如果处理过程中发生异常，记录错误并返回失败结果
            error_msg = f"处理会话存档通知失败: {e}"
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
        handler = MsgAuditHandler()
        
        print("会话存档通知处理器测试")
        print("=" * 50)
        
        # 模拟消息信息
        msg_info = {
            'msg_source': 'wecom',
            'MsgType': 'event',
            'Event': 'msgaudit_notify',
            'ToUserName': 'ww7ca9ef3dc03a24ce',
            'FromUserName': 'sys',
            'CreateTime': '1629101687',
            'AgentID': '2000004'
        }
        
        print("测试处理会话存档通知...")
        result = handler.handle(msg_info)
        print(f"处理结果: {result}")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
