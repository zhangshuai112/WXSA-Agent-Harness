# 导入操作系统模块，用于路径操作
import os
# 导入系统模块，用于路径操作
import sys
# 导入 JSON 处理模块，用于解析和生成 JSON 数据
import json
# 导入 XML 解析模块，用于解析 XML 格式的消息（企业微信使用 XML 格式）
import xml.etree.ElementTree as ET
# 导入类型提示模块，用于类型注解（Dict、Any、List、Callable、Optional 类型）
from typing import Dict, Any, List, Callable, Optional
# 导入数据类装饰器，用于简化类的定义
from dataclasses import dataclass

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入各种消息处理器类（每个处理器负责处理特定类型的消息）
from wechat_notify_handler.wxwork_externalcontact_handler import ExternalContactHandler  # 外部联系人变更处理器
from wechat_notify_handler.wxwork_tag_setting_handler import ExternalTagSettingHandler    # 标签配置变更处理器
from wechat_notify_handler.wxwork_msgaudit_handler import MsgAuditHandler                # 会话存档通知处理器
from wechat_notify_handler.wxwork_kf_handler import KfMsgHandler                         # 客服消息处理器
from wechat_notify_handler.wechat_shop_handler import WeChatShopHandler                  # 微信小店订单处理器
from wechat_notify_handler.notify_feishu_handler import NotifyFeishuHandler              # 飞书通知处理器（用于发送通知到飞书）
from wechat_notify_handler.notify_wxwork_handler import NotifyWxworkHandler              # 企业微信通知处理器（用于发送通知到企业微信）

# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录消息通知处理相关的日志信息
logger = setup_logging("notify_handler")

# 数据类：定义处理器注册条件（用于匹配消息和处理器）
@dataclass
class HandlerCondition:
    """Handler注册条件
    
    用于指定在什么条件下使用哪个处理器处理消息
    """
    msg_source: str  # 消息来源："wecom"（企业微信）或 "wxxd"（微信小店）
    msg_type: str    # 消息类型："event"（事件消息）等
    event: str       # 具体事件类型，如 "change_external_contact"（外部联系人变更）


class NotifyHandlerRegistry:
    """消息通知处理器注册中心
    
    作用：
    - 维护一个“条件 → 处理器实例”的列表（self.handlers）
    - 提供 register() 注册处理器
    - 提供 find_handlers() 按消息内容匹配出应该执行哪些处理器
    """
    
    def __init__(self):
        # handlers 列表中的每一项都是一个三元组：
        # (condition, handler_class, handler_instance)
        # 其中：
        #   condition:       HandlerCondition 条件对象
        #   handler_class:   处理器类（如 ExternalContactHandler）
        #   handler_instance:处理器实例（已经 new 出来的对象）
        self.handlers: List[tuple] = []
    
    def register(self, condition: HandlerCondition, handler_classes: List[Any]):
        """
        注册处理器
        
        Args:
            condition:       处理器匹配条件（来源 + 消息类型 + 事件）
            handler_classes: 需要在该条件下生效的处理器类列表
        """

        # 遍历传入的每一个处理器类
        for handler_class in handler_classes:
            # 创建该处理器的实例
            handler_instance = handler_class()
            # 把 (条件, 类, 实例) 这三个信息一起保存下来，后续按条件匹配使用
            self.handlers.append((condition, handler_class, handler_instance))
            # 打一条日志，方便排查：哪个条件注册了哪个处理器
            logger.info(f"注册处理器: {handler_class.__name__} -> {condition}")
    
    def find_handlers(self, msg_info: Dict[str, Any]) -> List[Any]:
        """
        根据消息信息查找匹配的处理器
        
        Args:
            msg_info: 解析后的消息信息（例如包含 msg_source / MsgType / Event 等字段）
            
        Returns:
            List[Any]: 匹配的处理器实例列表
        """
        matched_handlers: List[Any] = []
        
        # 遍历所有已注册的 (condition, handler_class, handler_instance)
        for condition, handler_class, handler_instance in self.handlers:
            # 检查消息来源是否匹配（比如 wecom / wxxd）
            if condition.msg_source != msg_info.get('msg_source'):
                # 不匹配则跳过当前处理器
                continue
                
            # 检查消息类型是否匹配（一般为 "event"）
            if condition.msg_type != msg_info.get('MsgType'):
                continue
                
            # 检查事件名称是否匹配（如 change_external_contact / kf_msg_or_event 等）
            if condition.event != msg_info.get('Event'):
                continue
                            
            # 三个条件都满足，则认为该处理器需要参与处理这条消息
            matched_handlers.append(handler_instance)
            logger.info(f"匹配到处理器: {handler_class.__name__}")
        
        # 返回所有符合条件的处理器实例
        return matched_handlers


class MessageParser:
    """消息解析器"""
    
    @staticmethod
    def parse_xml_message(xml_content: str) -> Dict[str, Any]:
        """
        解析XML格式的消息（企业微信）
        
        Args:
            xml_content: XML消息内容
            
        Returns:
            Dict[str, Any]: 解析后的消息字段
        """
        try:
            # 解析XML
            root = ET.fromstring(xml_content)
            
            # 提取基本字段，构造成一个统一的字典 result，后续用于路由匹配
            result = {
                'msg_source': 'wecom',                      # 消息来源标记为企业微信
                'MsgType': root.findtext('MsgType', ''),    # 消息类型（如 event）
                'Event': root.findtext('Event', ''),        # 事件类型（如 change_external_contact）
                'ChangeType': root.findtext('ChangeType', ''),  # 变更子类型（如 add_external_contact）
                'ToUserName': root.findtext('ToUserName', ''),  # 接收方（一般是企业ID或应用ID）
                'FromUserName': root.findtext('FromUserName', ''),  # 发送方（系统标识）
                'CreateTime': root.findtext('CreateTime', ''),      # 消息创建时间（时间戳）
                'UserID': root.findtext('UserID', ''),              # 员工ID（企业内部用户）
                'ExternalUserID': root.findtext('ExternalUserID', ''),  # 外部联系人ID
                'OpenKfId': root.findtext('OpenKfId', ''),          # 客服账号ID
                'AgentID': root.findtext('AgentID', ''),            # 应用ID
                'Id': root.findtext('Id', ''),                      # 事件唯一ID
                'Token': root.findtext('Token', ''),                # 事件Token（部分事件携带）
                'State': root.findtext('State', ''),                # 自定义 state（如拉客户时自带）
                'WelcomeCode': root.findtext('WelcomeCode', '')     # 欢迎语 code（用于发送欢迎消息）
            }
            
            # 移除空字段
            result = {k: v for k, v in result.items() if v}
            
            return result
            
        except ET.ParseError as e:
            logger.error(f"XML解析失败: {e}")
            raise ValueError(f"无效的XML格式: {e}")
    
    @staticmethod
    def parse_json_message(json_content: str) -> Dict[str, Any]:
        """
        解析JSON格式的消息（微信小店）
        
        Args:
            json_content: JSON消息内容
            
        Returns:
            Dict[str, Any]: 解析后的消息字段
        """
        try:
            # 解析JSON
            data = json.loads(json_content)
            
            # 提取基本字段并添加msg_source
            # result = data.copy()
            result = {
                'msg_source': 'wxxd',
                'MsgType': data.get('MsgType', ''),
                'Event': data.get('Event', ''),
                'ToUserName': data.get('ToUserName', ''),
                'FromUserName': data.get('FromUserName', ''),
                'CreateTime': data.get('CreateTime', ''),
                'order_info': data.get('order_info', {}) # 订单信息
            }

            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            raise ValueError(f"无效的JSON格式: {e}")
    
    @staticmethod
    def determine_message_format(msg_content: str) -> str:
        """
        判断消息格式
        
        Args:
            msg_content: 消息内容
            
        Returns:
            str: 'xml' 或 'json'
        """
        msg_content = msg_content.strip()
        
        # 检查是否为XML格式
        if msg_content.startswith('<') and msg_content.endswith('>'):
            return 'xml'
        
        # 检查是否为JSON格式
        if (msg_content.startswith('{') and msg_content.endswith('}')) or \
           (msg_content.startswith('[') and msg_content.endswith(']')):
            return 'json'
        
        raise ValueError(f"无法识别的消息格式")
    
    @staticmethod
    def parse_message(msg_content: str) -> Dict[str, Any]:
        """
        解析消息内容
        
        Args:
            msg_content: 消息内容
            
        Returns:
            Dict[str, Any]: 解析后的消息信息
        """
        # 判断消息格式
        msg_format = MessageParser.determine_message_format(msg_content)
        
        # 根据格式调用相应的解析方法
        if msg_format == 'xml':
            return MessageParser.parse_xml_message(msg_content)
        elif msg_format == 'json':
            return MessageParser.parse_json_message(msg_content)
        else:
            raise ValueError(f"不支持的消息格式: {msg_format}")


class NotifyHandler:
    """消息通知处理器主类"""
    
    def __init__(self):
        self.registry = NotifyHandlerRegistry()
        self.parser = MessageParser()
        self._register_all_handlers()
    
    def _register_all_handlers(self):
        """注册所有处理器"""
        
        # 1. 外部联系人通知处理器
        self.registry.register(
            HandlerCondition(
                msg_source='wecom',
                msg_type='event',
                event='change_external_contact'
            ),
            [ExternalContactHandler, NotifyFeishuHandler, NotifyWxworkHandler]
            # [NotifyFeishuHandler, NotifyWxworkHandler]
        )
        
        # 2. 标签配置变更通知处理器
        self.registry.register(
            HandlerCondition(
                msg_source='wecom',
                msg_type='event',
                event='change_external_tag'
            ),
            [ExternalTagSettingHandler, NotifyFeishuHandler, NotifyWxworkHandler]
            # [NotifyFeishuHandler, NotifyWxworkHandler]
        )
        
        # 3. 会话存档通知处理器
        self.registry.register(
            HandlerCondition(
                msg_source='wecom',
                msg_type='event',
                event='msgaudit_notify'
            ),
            [MsgAuditHandler, NotifyFeishuHandler, NotifyWxworkHandler]
            # [NotifyFeishuHandler, NotifyWxworkHandler]
        )
        
        # 4. 客服消息处理器
        self.registry.register(
            HandlerCondition(
                msg_source='wecom',
                msg_type='event',
                event='kf_msg_or_event'
            ),
            [KfMsgHandler, NotifyFeishuHandler, NotifyWxworkHandler]
            # [NotifyFeishuHandler, NotifyWxworkHandler]
        )
        
        # 5. 小店通知处理器
        self.registry.register(
            HandlerCondition(
                msg_source='wxxd',
                msg_type='event',
                event='channels_ec_order_new'
            ),
            [WeChatShopHandler, NotifyFeishuHandler, NotifyWxworkHandler]
            # [NotifyFeishuHandler, NotifyWxworkHandler]
        )
    
    def process_message(self, msg_content: str) -> Dict[str, Any]:
        """
        处理消息通知
        
        Args:
            msg_content: 原始消息内容
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        try:
            logger.info(f"开始处理消息通知...")
            logger.info(f"消息内容: {msg_content[:200]}...")
            
            # 1. 预处理消息体msg
            msg_content = msg_content.strip()
            
            # 2. 解析消息格式并提取字段信息
            msg_info = self.parser.parse_message(msg_content)
            logger.info(f"解析后的消息信息: {msg_info}")
            
            # 3. 根据handler的注册条件，筛选出使用哪个handler进行处理
            matched_handlers = self.registry.find_handlers(msg_info)
            
            if not matched_handlers:
                logger.error("没有找到匹配的处理器")
                return {
                    'success': False,
                    'message': '没有找到匹配的处理器',
                    'msg_info': msg_info,
                    'matched_handlers': 0
                }
            
            # 4. 执行处理器
            results = []
            for handler in matched_handlers:
                try:
                    logger.info(f"执行处理器: {handler.__class__.__name__}")
                    result = handler.handle(msg_info)
                    results.append({
                        'handler': handler.__class__.__name__,
                        'success': True,
                        'result': result
                    })
                except Exception as e:
                    logger.error(f"处理器执行失败 {handler.__class__.__name__}: {e}")
                    results.append({
                        'handler': handler.__class__.__name__,
                        'success': False,
                        'error': str(e)
                    })
            
            return {
                'success': True,
                'message': '消息处理完成',
                'msg_info': msg_info,
                'matched_handlers': len(matched_handlers),
                'results': results
            }
            
        except Exception as e:
            error_msg = f"处理消息失败: {e}"
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
        handler = NotifyHandler()
        
        print("消息通知处理器测试")
        print("=" * 50)
        
        # 测试XML消息（企业微信外部联系人通知）
        print("1. 测试企业微信外部联系人通知...")
        xml_msg = """
<xml>
        <ToUserName><![CDATA[toUser]]></ToUserName>
        <FromUserName><![CDATA[sys]]></FromUserName> 
        <CreateTime>1403610513</CreateTime>
        <MsgType><![CDATA[event]]></MsgType>
        <Event><![CDATA[change_external_contact]]></Event>
        <ChangeType><![CDATA[add_external_contact]]></ChangeType>
        <UserID><![CDATA[zhangsan]]></UserID>
        <ExternalUserID><![CDATA[woAJ2GCAAAXtWyujaWJHDDGi0mAAAA]]></ExternalUserID>
        <State><![CDATA[teststate]]></State>
        <WelcomeCode><![CDATA[WELCOMECODE]]></WelcomeCode>
</xml>
"""
        
        result = handler.process_message(xml_msg)
        print(f"处理结果: {result}")
        
        # 测试JSON消息（微信小店通知）
        print("\n2. 测试微信小店订单通知...")
        json_msg = """
{
  "CreateTime": 1752471174,
  "Event": "channels_ec_order_new",
  "FromUserName": "oaznn7JsSvZ-3prthpwkLts_vLR8",
  "MsgType": "event",
  "ToUserName": "gh_55bc28346bc8",
  "order_info": {
    "order_id": 3729486243659133696
  }
}
"""
        
        result = handler.process_message(json_msg)
        print(f"处理结果: {result}")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
