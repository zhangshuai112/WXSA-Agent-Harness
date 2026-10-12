# 导入 HTTP 请求库，用于发送 HTTP 请求到飞书 Webhook
import requests
# 导入 JSON 处理模块，用于序列化消息数据
import json
# 导入类型提示模块，用于类型注解（Dict、Any 类型）
from typing import Dict, Any
# 导入操作系统模块，用于环境变量和路径操作
import os
# 导入系统模块，用于路径操作
import sys
# 导入 dotenv 模块，用于从 .env 文件加载环境变量
from dotenv import load_dotenv

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 加载环境变量（从 .env 文件读取配置信息）
load_dotenv()

# 创建日志记录器，用于记录飞书通知处理相关的日志信息
logger = setup_logging("notify_feishu_handler")

# 飞书通知处理器类，用于将消息通知发送到飞书
class NotifyFeishuHandler:
    """飞书通知处理器
    
    功能：将处理后的消息信息发送到飞书（通过 Webhook），用于监控和通知
    用途：通常与其他处理器组合使用，在业务处理完成后发送通知到飞书群
    """
    
    # 初始化方法，创建处理器实例
    def __init__(self):
        """初始化处理器，读取飞书 Webhook 配置"""
        # 从环境变量中读取飞书 Webhook URL（用于发送消息到飞书群）
        self.feishu_webhook_url = os.getenv('FEISHU_WEBHOOK_URL')
    
    # 发送飞书通知的方法
    def handle(self, msg_info: Dict[str, Any]) -> Dict[str, Any]:
        """发送飞书通知（将消息信息发送到飞书群）
        
        Args:
            msg_info (Dict[str, Any]): 要发送的消息信息（通常是从其他处理器传递过来的处理结果）
            
        Returns:
            bool: 发送是否成功（True 表示成功，False 表示失败）
        """
        try:
            logger.info(f"发送飞书通知: {msg_info}")

            # 验证飞书 Webhook URL 是否配置
            if not self.feishu_webhook_url:
                logger.error("飞书webhook url未配置")
                return False

            # 构造飞书消息格式（飞书 Webhook 要求的格式）
            payload = {
                "msg_type": "text",  # 消息类型：文本消息
                "content": {
                    # 消息内容：将 msg_info 转换为格式化的 JSON 字符串
                    "text": json.dumps(msg_info, ensure_ascii=False, indent=2)
                }
            }
            
            # 设置 HTTP 请求头，指定内容类型为 JSON
            headers = {
                'Content-Type': 'application/json'
            }
            
            # 发送 POST 请求到飞书 Webhook
            response = requests.post(
                self.feishu_webhook_url,  # 飞书 Webhook URL
                json=payload,              # 请求体（自动序列化为 JSON）
                headers=headers,           # 请求头
                timeout=10                 # 超时时间（10秒）
            )
            
            # 检查 HTTP 响应状态码
            if response.status_code == 200:
                # 将响应内容解析为 JSON 格式
                result = response.json()
                # 检查飞书 API 返回的错误码（code == 0 表示成功）
                if result.get('code') == 0:
                    logger.info(f"消息发送到飞书成功: {result}")
                    return True
                else:
                    logger.error(f"消息发送到飞书失败: {result}")
                    return False
            else:
                logger.error(f"消息发送到飞书失败: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            logger.error(f"消息发送到飞书失败: {e}")
            return False
        except Exception as e:
            # 捕获其他异常
            logger.error(f"消息发送到飞书失败: {e}")
            return False




def main():
    """测试函数"""
    try:
        # 初始化处理器
        handler = NotifyFeishuHandler()
        
        print("飞书通知处理器测试")
        print("=" * 50)

        # 测试发送飞书通知
        print("1. 测试发送飞书通知...")
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

