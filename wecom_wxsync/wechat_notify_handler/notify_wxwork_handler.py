# 导入 HTTP 请求库（虽然导入了但可能未使用，因为使用的是 wechat_work_api 的方法）
import requests
# 导入 JSON 处理模块，用于序列化消息数据
import json
# 导入系统模块，用于路径操作
import sys
# 导入类型提示模块，用于类型注解（Dict、Any 类型）
from typing import Dict, Any
# 导入操作系统模块，用于环境变量和路径操作
import os
# 导入 dotenv 模块，用于从 .env 文件加载环境变量
from dotenv import load_dotenv

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 导入企业微信 API 客户端类，用于发送通知消息
from wechat_client.wechat_work_api import WechatWorkAPI
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 加载环境变量（从 .env 文件读取配置信息）
load_dotenv()

# 创建日志记录器，用于记录企业微信通知处理相关的日志信息
logger = setup_logging("notify_wxwork_handler")

# 企业微信通知处理器类，用于将消息通知发送到企业微信
class NotifyWxworkHandler:
    """企业微信通知处理器
    
    功能：将处理后的消息信息发送到企业微信（通过企业微信 API），用于监控和通知
    用途：通常与其他处理器组合使用，在业务处理完成后发送通知到指定员工的企业微信
    """
    
    # 初始化方法，创建处理器实例
    def __init__(self):
        """初始化处理器，创建 API 客户端实例并读取配置"""
        # 创建企业微信 API 客户端实例（用于发送通知消息）
        self.wechat_work_api = WechatWorkAPI()
        # 从环境变量中读取企业微信通知接收用户的 user_id（消息会发送给这个用户）
        self.wxwork_notify_user = os.getenv('WXWORK_NOTIFY_USER')
    
    # 发送企业微信通知的方法
    def handle(self, msg_info: Dict[str, Any]) -> Dict[str, Any]:
        """发送企业微信通知（将消息信息发送到指定员工的企业微信）
        
        Args:
            msg_info (Dict[str, Any]): 要发送的消息信息（通常是从其他处理器传递过来的处理结果）
            
        Returns:
            bool: 发送是否成功（True 表示成功，False 表示失败）
        """
        try:
            logger.info(f"发送企业微信通知: {msg_info}")

            # 验证企业微信通知用户是否配置
            if not self.wxwork_notify_user:
                logger.error("企业微信通知用户未配置")
                return False

            # 调用企业微信 API 发送通知消息
            # notify_msg 方法会将消息发送到指定用户的企业微信
            # 参数：接收用户的 user_id，消息内容（将 msg_info 转换为格式化的 JSON 字符串）
            self.wechat_work_api.notify_msg(self.wxwork_notify_user, json.dumps(msg_info, ensure_ascii=False, indent=2))
            # 发送成功，返回 True
            return True
        except requests.exceptions.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            logger.error(f"消息发送到企业微信失败: {e}")
            return False
        except Exception as e:
            # 捕获其他异常
            logger.error(f"消息发送到企业微信失败: {e}")
            return False

def main():
    """测试函数"""
    try:
        # 初始化处理器
        handler = NotifyWxworkHandler()
        
        print("企业微信通知处理器测试")
        print("=" * 50)

        # 测试发送企业微信通知
        print("1. 测试发送企业微信通知...")
        msg_info = {
            'msg_source': 'wecom',
            'MsgType': 'event',
            'Event': 'change_external_contact',
            'ChangeType': 'add_external_contact',
            'UserID': 'zhangsan',
            'ExternalUserID': 'woAJ2GCAAAXtWyujaWJHDDGi0mAAAA',
            'ToUserName': 'toUser',
            'FromUserName': 'sys',
            'CreateTime': '1403610513',
            'State': 'teststate',
            'WelcomeCode': 'WELCOMECODE'
        }
        
        result = handler.handle(msg_info)
        print(f"发送结果: {result}")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()

