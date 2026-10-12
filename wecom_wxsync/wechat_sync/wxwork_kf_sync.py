# 导入操作系统模块，用于环境变量和路径操作
import os
# 导入系统模块，用于路径操作
import sys
# 导入时间模块，用于时间操作（虽然导入了但可能未使用）
import time
# 导入类型提示模块，用于类型注解（List、Dict、Any、Optional 类型）
from typing import List, Dict, Any, Optional

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 导入存储 API 客户端类，用于将客服消息数据写入 LangGraph Store
from wechat_sync.wecom_store_api import create_wecom_store_api
# 导入企业微信 API 客户端类，用于调用企业微信 API 获取客服消息
from wechat_client.wechat_work_api import WechatWorkAPI
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录企业微信客服消息同步相关的日志信息
logger = setup_logging("wxwork_kf_sync")

# 企业微信客服消息同步服务类，负责从企业微信 API 获取客服消息并同步到 LangGraph Store
class WxWorkKFSync:
    """企业微信客服消息同步服务
    
    主要功能：
    - 同步客服消息（客户与客服的对话记录）
    - 管理同步游标（cursor），支持增量同步
    - 自动将会话分配给人工客服（当会话状态为未处理或智能助手接待时）
    """
    
    # 初始化方法，创建同步服务实例
    def __init__(self):
        """
        初始化同步服务，创建必要的 API 客户端实例
        """
        # 创建企业微信 API 客户端实例（用于调用企业微信 API获取数据）
        self.wechat_work_api = WechatWorkAPI()
        # 创建存储 API 客户端实例（用于将客服消息数据写入 LangGraph Store）
        # 从环境变量中读取服务器地址、用户ID和密码
        self.wecom_store_api = create_wecom_store_api()
        # cursor 键的前缀（用于在全局状态中存储不同客服账号的同步游标）
        # 格式：wxwork_kf_cursor_{open_kfid}
        self.cursor_key_prefix = "wxwork_kf_cursor"
    
    def get_cursor_key(self, open_kfid: str) -> str:
        """
        生成cursor存储的key
        
        Args:
            open_kfid: 客服账号ID
            
        Returns:
            str: cursor存储的key
        """
        if open_kfid:
            return f"{self.cursor_key_prefix}_{open_kfid}"
        else:
            return f"{self.cursor_key_prefix}_default"
    
    def get_last_cursor(self, open_kfid: str = "") -> str:
        """
        从全局状态中获取上次同步的cursor
        
        Args:
            open_kfid: 客服账号ID
            
        Returns:
            str: 上次同步的cursor，如果没有则返回空字符串
        """
        try:
            cursor_key = self.get_cursor_key(open_kfid)
            result = self.wecom_store_api.get_wecom_global_state(cursor_key)
            if result and isinstance(result, dict):
                return result.get("cursor", "")
            return ""
        except Exception as e:
            logger.error(f"获取上次同步cursor失败: {e}")
            return ""
    
    def save_last_cursor(self, cursor: str, open_kfid: str = "") -> None:
        """
        保存最新的cursor到全局状态
        
        Args:
            cursor: 要保存的cursor值
            open_kfid: 客服账号ID
        """
        try:
            cursor_key = self.get_cursor_key(open_kfid)
            value = {"cursor": cursor}
            self.wecom_store_api.upsert_wecom_global_state(cursor_key, value)
            logger.info(f"保存最新cursor: {cursor[:20]}...")
        except Exception as e:
            logger.error(f"保存cursor失败: {e}")
    
    def is_valid_message(self, msg: Dict[str, Any]) -> bool:
        """
        检查消息是否符合处理条件
        
        Args:
            msg: 消息数据
            
        Returns:
            bool: 是否符合条件
        """
        # 检查origin字段：仅当 origin = 3（客户发送）或者5（客服发送） 时有效
        origin = msg.get('origin', 0)
        if origin not in [3, 5]:
            return False
        
        # 检查msgtype字段：仅当 msgtype = "text" 时有效
        msgtype = msg.get('msgtype', '')
        if msgtype != 'text':
            return False
        
        # 检查必要字段是否存在
        required_fields = ['msgid', 'external_userid', 'send_time']
        for field in required_fields:
            if field not in msg:
                return False
        
        # 检查text字段是否包含content
        text_content = msg.get('text', {})
        if not isinstance(text_content, dict) or 'content' not in text_content:
            return False
        
        return True
    
    def process_message(self, msg: Dict[str, Any]) -> bool:
        """
        处理单条消息
        
        Args:
            msg: 消息数据
            
        Returns:
            bool: 处理是否成功
        """
        try:
            # 提取字段
            msg_id = msg.get('msgid', '')
            external_id = msg.get('external_userid', '')
            open_kfid = msg.get('open_kfid', '')
            servicer_userid = msg.get('servicer_userid', '')
            msg_time = msg.get('send_time', 0)
            origin = msg.get('origin', 0)
            msgtype = msg.get('msgtype', '')
            content = msg.get('text', {}).get('content', '')
                        
            # 写入到WecomStoreAPI
            self.wecom_store_api.upsert_wxkf_msg(
                msg_id=msg_id,
                external_id=external_id,
                open_kfid=open_kfid,
                servicer_userid=servicer_userid,
                msg_time=msg_time,
                origin=origin,
                msgtype=msgtype,
                content=content
            )

            kf_state = self.wechat_work_api.get_kf_state(open_kfid, external_id)
            if kf_state == 0 or kf_state == 1:
                self.wechat_work_api.trans_kf_state_to_human(open_kfid, external_id)
            
            return True
            
        except Exception as e:
            logger.error(f"处理消息失败 {msg.get('msgid', '')}: {e}")
            return False
    
    def sync_messages(self, open_kfid: str) -> Dict[str, Any]:
        """
        同步企业微信客服消息
        
        Args:
            open_kfid: 指定拉取某个客服账号的消息
            
        Returns:
            dict: 同步结果统计
        """
        logger.info(f"开始同步企业微信客服消息，open_kfid: {open_kfid or 'default'}...")
        
        try:
            # 获取上次同步的cursor值
            cursor = self.get_last_cursor(open_kfid)
            logger.info(f"从cursor {cursor[:20] if cursor else 'empty'}... 开始同步消息")
            
            # 获取消息列表
            msg_list, next_cursor = self.wechat_work_api.get_kf_messages(
                open_kfid=open_kfid,
                cursor=cursor
            )
            
            if msg_list is None:
                logger.error("获取客服消息失败")
                return {
                    'open_kfid': open_kfid,
                    'start_cursor': cursor,
                    'next_cursor': '',
                    'total_messages': 0,
                    'valid_messages': 0,
                    'processed_messages': 0,
                    'error_messages': 0,
                    'sync_time': time.time()
                }
            
            logger.info(f"获取到 {len(msg_list)} 条消息")
            
            # 统计信息
            total_messages = len(msg_list)
            valid_messages = 0
            processed_messages = 0
            error_messages = 0
            
            # 处理每条消息
            for msg in msg_list:
                # 检查消息是否符合条件
                if not self.is_valid_message(msg):
                    logger.error(f"消息不符合条件: {msg} ")
                    continue
                
                valid_messages += 1
                
                # 处理消息
                if self.process_message(msg):
                    processed_messages += 1
                else:
                    error_messages += 1
            
            # 保存最新的cursor值
            if next_cursor:
                self.save_last_cursor(next_cursor, open_kfid)
            
            result = {
                'open_kfid': open_kfid,
                'start_cursor': cursor,
                'next_cursor': next_cursor,
                'total_messages': total_messages,
                'valid_messages': valid_messages,
                'processed_messages': processed_messages,
                'error_messages': error_messages,
                'sync_time': time.time()
            }
            
            logger.info(f"客服消息同步完成: 总计 {total_messages} 条，"
                  f"符合条件 {valid_messages} 条，"
                  f"成功处理 {processed_messages} 条，"
                  f"失败 {error_messages} 条")
            
            return result
            
        except Exception as e:
            error_msg = f"同步企业微信客服消息失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def reset_cursor(self, open_kfid: str = "") -> None:
        """
        重置cursor值为空（重新开始同步）
        
        Args:
            open_kfid: 客服账号ID
        """
        try:
            self.save_last_cursor("", open_kfid)
            logger.info(f"cursor值已重置为空，open_kfid: {open_kfid or 'default'}")
        except Exception as e:
            logger.error(f"重置cursor失败: {e}")
    
    def get_sync_status(self, open_kfid: str = "") -> Dict[str, Any]:
        """
        获取同步状态信息
        
        Args:
            open_kfid: 客服账号ID
            
        Returns:
            dict: 同步状态信息
        """
        try:
            last_cursor = self.get_last_cursor(open_kfid)
            cursor_key = self.get_cursor_key(open_kfid)
            
            return {
                'open_kfid': open_kfid or 'default',
                'last_cursor': last_cursor,
                'cursor_key': cursor_key,
                'status': 'ready'
            }
        except Exception as e:
            return {
                'open_kfid': open_kfid or 'default',
                'last_cursor': '',
                'cursor_key': self.get_cursor_key(open_kfid),
                'status': 'error',
                'error': str(e)
            }

def main():
    """测试函数"""
    try:
        # 初始化同步服务
        sync_service = WxWorkKFSync()
        
        print("企业微信客服消息同步测试")
        print("=" * 50)
        
        # 显示当前同步状态
        print("1. 当前同步状态:")
        status = sync_service.get_sync_status("wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw")
        print(f"状态: {status}")
        
        #sync_service.reset_cursor(open_kfid='wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw')
        # 测试同步消息
        print("\n2. 测试同步消息...")
        result = sync_service.sync_messages("wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw")
        print(f"同步结果: {result}")
        
        print("\n可用的其他功能:")
        print("- sync_service.reset_cursor(open_kfid='')  # 重置cursor从头开始")
        print("- sync_service.get_sync_status(open_kfid='')  # 获取同步状态")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
