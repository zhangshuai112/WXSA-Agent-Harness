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

# 导入企业微信外部联系人数据同步服务类，用于同步标签数据
from wechat_sync.wechat_work_sync import WechatWorkSync
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录标签配置变更通知处理相关的日志信息
logger = setup_logging("wxwork_tag_setting_handler")

# 标签配置变更通知处理器类，用于处理企业微信标签配置变更通知
class ExternalTagSettingHandler:
    """标签配置变更通知处理器
    
    功能：当企业微信标签配置发生变更（如创建标签、删除标签、修改标签名称等）时，触发此处理器
    处理流程：
    1. 接收企业微信推送的标签配置变更通知
    2. 调用同步服务，同步所有标签数据
    3. 将标签配置数据写入 LangGraph Store
    """
    
    # 初始化方法，创建处理器实例
    def __init__(self):
        """
        初始化处理器，创建同步服务实例
        """
        # 创建企业微信外部联系人数据同步服务实例（用于同步标签数据）
        self.sync_service = WechatWorkSync()
    
    # 处理标签配置变更通知的方法
    def handle(self, msg_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理标签配置变更通知
        
        触发场景：当企业微信标签配置发生变更时（如创建、删除、修改标签），
                  企业微信会推送通知，此方法会被调用来处理通知。
        
        Args:
            msg_info (Dict[str, Any]): 解析后的消息信息，包含以下字段：
                - ChangeType: 变更类型（如 create、update、delete、shuffle 等）
                - Id: 标签ID（某些变更类型可能包含）
                - 其他字段...
            
        Returns:
            Dict[str, Any]: 处理结果，包含：
                - success: 是否处理成功
                - message: 处理结果消息
                - sync_result: 同步结果统计
        """
        try:
            logger.info("处理标签配置变更通知...")
            
            # 无消息过滤条件，直接处理（标签变更时，同步所有标签配置）
            logger.info("同步标签配置数据...")
            
            # 调用同步服务，同步标签数据
            # sync_tags 会从企业微信 API 获取所有标签数据（企业标签和策略标签），并写入 LangGraph Store
            sync_result = self.sync_service.sync_tags()
            
            # 返回成功结果，包含同步结果统计
            return {
                'success': True,
                'message': '标签配置数据同步完成',
                'sync_result': sync_result  # 包含 success_count、error_count 等统计信息
            }
            
        except Exception as e:
            # 如果处理过程中发生异常，记录错误并返回失败结果
            error_msg = f"处理标签配置变更通知失败: {e}"
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
        handler = ExternalTagSettingHandler()
        
        print("标签配置变更通知处理器测试")
        print("=" * 50)
        
        # 模拟消息信息
        msg_info = {
            'msg_source': 'wecom',
            'MsgType': 'event',
            'Event': 'change_external_tag',
            'ChangeType': 'shuffle',
            'Id': 'etE8gRKQAAmsAFqc4NCOLaxSyPYyvxUw',
            'ToUserName': 'ww7ca9ef3dc03a24ce',
            'FromUserName': 'sys',
            'CreateTime': '1752372097'
        }
        
        print("测试处理标签配置变更通知...")
        result = handler.handle(msg_info)
        print(f"处理结果: {result}")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
