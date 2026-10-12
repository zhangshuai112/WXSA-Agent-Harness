# 导入操作系统模块，用于环境变量和路径操作
import os
# 导入系统模块，用于路径操作
import sys
# 导入时间模块，用于时间操作（虽然导入了但可能未使用）
import time
# 导入类型提示模块，用于类型注解（List、Dict、Any、Optional 类型）
from typing import List, Dict, Any, Optional
# 导入 HTTP 请求库，用于发送 HTTP 请求（虽然导入了但可能未使用）
import requests
# 导入 JSON 处理模块，用于解析和生成 JSON 数据（虽然导入了但可能未使用）
import json

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 导入存储 API 客户端类，用于将会话存档消息数据写入 LangGraph Store
from wechat_sync.wecom_store_api import create_wecom_store_api
# 导入企业微信会话存档 API 函数，用于获取加密的会话消息并解密
from wechat_client.wechat_msgaudit_api import get_msg_list
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录企业微信会话存档消息同步相关的日志信息
logger = setup_logging("wxwork_msgaudit_sync")

# 同步 seq 值的全局状态键名（用于在 LangGraph Store 中存储上次同步的消息序列号）
SYNC_SEQ_KEY = "wxwork_msgaudit_last_seq"  # 同步seq值，保存在wecom_server中
# 同步标志的全局状态键名（用于标记是否有新消息需要同步）
SYNC_FLAG_KEY = "wxwork_msgaudit_sync_flag"  # 同步标志，保存在wecom_server中
# 同步标志值：1 表示有新消息需要同步
SYNC_FLAG_VALUE = 1  # 同步标志值，1表示有新消息需要同步
# 同步标志值：0 表示没有新消息需要同步
SYNC_FLAG_VALUE_RESET = 0  # 同步标志值，0表示没有新消息需要同步

# 企业微信会话存档消息同步服务类，负责从企业微信会话存档 API 获取消息并同步到 LangGraph Store
class WxWorkMsgAuditSync:
    """企业微信会话存档消息同步服务
    
    主要功能：
    - 同步企业微信会话存档消息（员工与客户的对话记录）
    - 管理同步序列号（seq），支持增量同步
    - 管理同步标志（sync_flag），用于标记是否有新消息需要同步
    """
    
    # 初始化方法，创建同步服务实例
    def __init__(self):
        """
        初始化同步服务，创建存储 API 客户端实例
        
        注意：会话存档 API 使用 C 语言 SDK，需要在独立进程中运行（由 get_msg_list 函数处理）
        """
        # 创建存储 API 客户端实例（用于将会话存档消息数据写入 LangGraph Store）
        # 从环境变量中读取服务器地址、用户ID和密码
        self.wecom_store_api = create_wecom_store_api()
    
    def get_last_seq(self) -> int:
        """
        从全局状态中获取上次同步的seq值
        
        Returns:
            int: 上次同步的seq值，如果没有则返回0
        """
        try:
            value = self.wecom_store_api.get_wecom_global_state(SYNC_SEQ_KEY)
            if value and isinstance(value, dict):
                return value.get("seq", 0)
            return 0
        except Exception as e:
            logger.error(f"获取上次同步seq失败: {e}")
            return 0
    
    def save_last_seq(self, seq: int) -> None:
        """
        保存最新的seq值到全局状态
        
        Args:
            seq: 要保存的seq值
        """
        try:
            value = {"seq": seq}
            self.wecom_store_api.upsert_wecom_global_state(SYNC_SEQ_KEY, value)
            logger.info(f"保存最新seq: {seq}")
        except Exception as e:
            logger.error(f"保存seq失败: {e}")
    
    def get_sync_flag(self) -> int:
        """
        获取同步标志
        
        Returns:
            int: 同步标志值，1表示有新消息需要同步，其他值表示没有新消息需要同步
        """
        try:
            value = self.wecom_store_api.get_wecom_global_state(SYNC_FLAG_KEY)
            if value and isinstance(value, dict):
                return value.get("sync_flag", 0)
            return 0
        except Exception as e:
            logger.error(f"获取同步标志失败: {e}")
            return 0
    
    def save_sync_flag(self, flag: int) -> None:
        """
        保存同步标志
        
        Args:
            flag: 要保存的同步标志值
        """
        try:
            value = {"sync_flag": flag}
            self.wecom_store_api.upsert_wecom_global_state(SYNC_FLAG_KEY, value)
            logger.info(f"保存最新同步标志: {flag}")
        except Exception as e:
            logger.error(f"保存同步标志失败: {e}")
    
    def is_valid_message(self, msg: Dict[str, Any]) -> bool:
        """
        检查消息是否符合处理条件
        
        Args:
            msg: 消息数据
            
        Returns:
            bool: 是否符合条件
        """
        # 检查action字段是否为send
        if msg.get('action') != 'send':
            return False
        
        # 检查msgtype字段是否为text
        if msg.get('msgtype') != 'text':
            return False
        
        # 检查tolist字段是否为长度为1的数组
        tolist = msg.get('tolist', [])
        if not isinstance(tolist, list) or len(tolist) != 1:
            return False
        
        # 检查必要字段是否存在
        required_fields = ['msgid', 'from', 'msgtime', 'text', 'seq']
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
            from_id = msg.get('from', '')
            to_id = msg.get('tolist', [])[0]  # tolist长度已经验证为1
            msg_time = msg.get('msgtime', 0)
            content = msg.get('text', {}).get('content', '')
            seq = msg.get('seq', 0)
            
            # 转换msgtime（毫秒转秒）
            if msg_time > 0:
                msg_time = int(msg_time / 1000)
            
            # 写入到WecomStoreAPI
            self.wecom_store_api.upsert_wxqy_msg(
                msg_id=msg_id,
                from_id=from_id,
                to_id=to_id,
                msg_time=msg_time,
                content=content,
                seq=seq
            )
            
            return True
            
        except Exception as e:
            logger.error(f"处理消息失败 {msg.get('msgid', '')}: {e}")
            return False
    
    def sync_messages(self, limit: int = 1000) -> Dict[str, Any]:
        """
        同步企业微信会话存档消息
        
        Args:
            limit: 每次获取的消息数量限制
            
        Returns:
            dict: 同步结果统计
        """
        logger.info("开始同步企业微信会话存档消息...")
        
        try:
            # 获取上次同步的seq值
            start_seq = self.get_last_seq()
            logger.info(f"从seq {start_seq} 开始同步消息...")
            
            # 获取消息列表
            msg_list = get_msg_list(start_seq=start_seq, limit=limit)
            logger.info(f"获取到 {len(msg_list)} 条消息")
            
            # 统计信息
            total_messages = len(msg_list)
            valid_messages = 0
            processed_messages = 0
            error_messages = 0
            max_seq = start_seq
            
            # 处理每条消息
            for msg in msg_list:
                current_seq = msg.get('seq', 0)
                if current_seq > max_seq:
                    max_seq = current_seq
                
                # 检查消息是否符合条件
                if not self.is_valid_message(msg):
                    continue
                
                valid_messages += 1
                
                # 处理消息
                if self.process_message(msg):
                    processed_messages += 1
                else:
                    error_messages += 1
            
            # 保存最新的seq值
            if max_seq > start_seq:
                self.save_last_seq(max_seq)
            
            result = {
                'start_seq': start_seq,
                'max_seq': max_seq,
                'total_messages': total_messages,
                'valid_messages': valid_messages,
                'processed_messages': processed_messages,
                'error_messages': error_messages,
                'sync_time': time.time()
            }
            
            logger.info(f"消息同步完成: 总计 {total_messages} 条，"
                  f"符合条件 {valid_messages} 条，"
                  f"成功处理 {processed_messages} 条，"
                  f"失败 {error_messages} 条")
            
            return result
            
        except Exception as e:
            error_msg = f"同步企业微信会话存档消息失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
    def reset_seq(self) -> None:
        """
        重置seq值为0（重新开始同步）
        """
        try:
            self.save_last_seq(0)
            logger.info("seq值已重置为0")
        except Exception as e:
            logger.error(f"重置seq失败: {e}")
    
    def get_sync_status(self) -> Dict[str, Any]:
        """
        获取同步状态信息
        
        Returns:
            dict: 同步状态信息
        """
        try:
            last_seq = self.get_last_seq()
            sync_flag = self.get_sync_flag()
            return {
                'seq_key': SYNC_SEQ_KEY,
                'seq_value': last_seq,
                'sync_flag_key': SYNC_FLAG_KEY,
                'sync_flag_value': sync_flag,
            }
        except Exception as e:
            return {
                'seq_key': SYNC_SEQ_KEY,
                'sync_flag_key': SYNC_FLAG_KEY,
                'status': 'error',
                'error': str(e)
            }

def send_to_feishu(text_content):
    """
    发送消息到飞书
    """
    feishu_url = os.getenv("FEISHU_WEBHOOK_URL")

    if not feishu_url:
        logger.error("飞书URL未配置")
        return

    if isinstance(text_content, dict):
        text_content = json.dumps(text_content)

    # 构造飞书消息格式
    payload = {
        "msg_type": "text",
        "content": {
            "text": text_content
        }
    }
    logger.info(f"发送飞书消息: {payload}")
    # 发送POST请求
    headers = {
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(
            feishu_url,
            json=payload, 
            headers=headers,
            timeout=10
        )
        if response.status_code != 200:
            logger.error(f"发送飞书消息失败: {response.status_code}")
            return False
        logger.info(f"发送飞书消息成功: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"发送飞书消息失败: {e}")
        return False

def keep_sync_messages():
    """
    保持同步企业微信会话存档消息
    """
    sync_service = WxWorkMsgAuditSync()

    while True:
        sync_flag = sync_service.get_sync_flag()

        if sync_flag == SYNC_FLAG_VALUE_RESET: # 如果没有消息需要同步，则等待30秒
            time.sleep(30)
            continue
        elif sync_flag == SYNC_FLAG_VALUE: # 如果有消息需要同步，则同步消息
            sync_service.save_sync_flag(SYNC_FLAG_VALUE_RESET)
            sync_result = sync_service.sync_messages(limit=100)
            send_to_feishu(f"企业微信会话存档消息同步完成: {sync_result}, 同步标志: {sync_flag}")
            continue
        else: # 如果同步标志为其他值，则重置同步标志并等待30秒
            sync_service.save_sync_flag(SYNC_FLAG_VALUE_RESET)
            time.sleep(30)
            continue



    

def test():
    """测试函数"""
    try:
        # 初始化同步服务
        sync_service = WxWorkMsgAuditSync()
        
        print("企业微信会话存档消息同步测试")
        print("=" * 50)
        
        # 显示当前同步状态
        print("1. 当前同步状态:")
        status = sync_service.get_sync_status()
        print(f"状态: {status}")
        
        # 测试同步消息
        print("\n2. 测试同步消息...")
        result = sync_service.sync_messages(limit=100)
        print(f"同步结果: {result}")


        # 显示当前同步状态
        print("3. 当前同步状态:")
        status = sync_service.get_sync_status()
        print(f"状态: {status}")
                
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    keep_sync_messages()
    #test()