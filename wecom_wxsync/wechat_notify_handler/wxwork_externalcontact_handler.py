"""企业微信外部联系人通知处理器

本模块负责处理企业微信“外部联系人变更”回调事件：
- 上层（wx_notify_app.py）负责接收、验签、解密回调消息
- notify_handler.py 负责解析 XML/JSON 并路由到本处理器
- 本处理器调用 WechatWorkSync，将外部联系人数据同步到 LangGraph Store
"""

# 导入操作系统模块，用于路径操作（例如拼接/获取上级目录）
import os
# 导入系统模块，用于修改模块搜索路径等
import sys
# 导入类型提示模块中的 Dict 和 Any，用于类型注解，提升可读性和开发体验
from typing import Dict, Any

# 将项目根目录添加到 Python 模块搜索路径中，
# 这样就可以使用 wechat_sync.xxx 的形式导入同一项目下的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取所在目录，连续两次 dirname 表示往上两级目录（到项目根）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 从 wechat_sync.wechat_work_sync 模块导入企业微信外部联系人数据同步服务类
# 该类负责：
# - 调用企业微信 API 拉取指定员工的外部联系人列表
# - 将外部联系人数据写入 LangGraph Store
from wechat_sync.wechat_work_sync import WechatWorkSync
# 导入日志配置函数，用于初始化 logger
from logger.logging import setup_logging

# 创建一个专用的日志记录器，名称为 "wxwork_externalcontact_handler"
# 之后本模块中的日志都会通过这个 logger 输出，便于排查问题
logger = setup_logging("wxwork_externalcontact_handler")


class ExternalContactHandler:
    """外部联系人通知处理器

    处理的场景：
    - 企业微信中外部联系人发生变更（新增、删除、更新等）时
    - 企业微信会推送一条“change_external_contact”事件
    - 上层解析后将消息交给本处理器的 handle 方法

    本处理器的职责：
    1. 从回调消息中提取员工 UserID
    2. 调用 WechatWorkSync.sync_external_contacts_by_user(user_id)
       从企业微信同步该员工的所有外部联系人数据
    3. 将客户数据写入 LangGraph Store（在同步服务内部完成）
    """

    def __init__(self):
        """
        初始化处理器实例：
        - 创建一个 WechatWorkSync 实例，后续所有同步操作都通过它来执行
        """
        # 创建企业微信外部联系人数据同步服务实例
        # WechatWorkSync 内部会组合 WechatWorkAPI（调用企业微信）和 WecomStoreAPI（写 Store）
        self.sync_service = WechatWorkSync()

    def handle(self, msg_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理一条“外部联系人变更”通知

        Args:
            msg_info (Dict[str, Any]): 解析后的消息信息字典，通常包含：
                - msg_source: 消息来源（例如 "wecom"）
                - MsgType:   消息类型（一般为 "event"）
                - Event:     事件类型（此处为 "change_external_contact"）
                - ChangeType:具体的变更类型（如 add_external_contact 等）
                - UserID:    员工ID（必填，用于确定同步哪个员工名下的客户）
                - ExternalUserID: 外部联系人ID（可选）
                - 其他：ToUserName、FromUserName、CreateTime、State 等辅助字段

        Returns:
            Dict[str, Any]: 处理结果，格式示例：
                {
                    'success': True,
                    'message': '外部联系人数据同步完成',
                    'user_id': 'ChengJianZhang',
                    'sync_result': {...}  # 同步统计结果
                }
        """
        try:
            # 打日志：开始处理一条外部联系人变更通知
            logger.info("处理外部联系人通知...")

            # 从消息中获取员工 ID（UserID 是同步的关键字段）
            user_id = msg_info.get('UserID', '')
            # 如果消息中没有带 UserID，则无法知道该同步哪个员工名下的客户
            if not user_id:
                # 直接返回失败信息，不再尝试同步
                return {
                    'success': False,
                    'message': '缺少必要参数 UserID'
                }

            # 打日志：标记即将同步哪个员工的外部联系人数据
            logger.info(f"同步员工 {user_id} 的外部联系人数据...")

            # 调用同步服务：
            # - 从企业微信 API 分页拉取该员工的外部联系人列表
            # - 将每一个外部联系人记录写入 LangGraph Store
            # - 返回一个统计信息字典（包括总数、成功数、失败数等）
            sync_result = self.sync_service.sync_external_contacts_by_user(user_id)

            # 打日志：同步结束，增加一条明显分隔便于在日志中定位
            logger.info(f"同步员工 {user_id} 的外部联系人数据完成=======================")

            # 同步成功时，返回包含统计信息的成功结果
            return {
                'success': True,
                'message': '外部联系人数据同步完成',
                'user_id': user_id,
                # sync_result 通常包含：
                # - total_contacts: 总处理外部联系人数
                # - success_count:  成功写入 Store 的数量
                # - error_count:    写入失败的数量
                # - 其他用于观测的字段
                'sync_result': sync_result
            }

        except Exception as e:
            # 捕获处理过程中的任何异常（网络问题、数据问题等）
            error_msg = f"处理外部联系人通知失败: {e}"
            # 打错误日志，方便线上排查
            logger.error(error_msg)
            # 返回失败结果，并附带错误信息
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }


def main():
    """本模块的自测入口函数（用于本地调试，不在生产环境调用）"""
    try:
        # 初始化处理器实例
        handler = ExternalContactHandler()

        print("外部联系人通知处理器测试")
        print("=" * 50)

        # 构造一条模拟的回调消息字典，用于本地测试 handle 逻辑
        msg_info = {
            'msg_source': 'wecom',                     # 模拟来源：企业微信
            'MsgType': 'event',                        # 消息类型：事件
            'Event': 'change_external_contact',        # 事件类型：外部联系人变更
            'ChangeType': 'add_external_contact',      # 变更子类型：添加外部联系人
            'UserID': 'ChengJianZhang',                # 测试用员工ID
            'ExternalUserID': 'woAJ2GCAAAXtWyujaWJDDGi0mAAAA',  # 测试用外部联系人ID
            'ToUserName': 'toUser',                    # 模拟接收方
            'FromUserName': 'sys',                     # 模拟发送方
            'CreateTime': '1403610513',                # 模拟创建时间
            'State': 'teststate',                      # 自定义 state（测试值）
            'WelcomeCode': 'WELCOMECODE'               # 欢迎语 code（测试值）
        }

        print("测试处理外部联系人通知...")
        # 调用处理方法，获取处理结果
        result = handler.handle(msg_info)
        # 将结果打印到控制台，方便观察
        print(f"处理结果: {result}")

    except Exception as e:
        # 如果测试过程中发生异常，在控制台打印错误信息
        print(f"测试失败: {e}")


if __name__ == "__main__":
    # 只有直接运行本文件时（python wxwork_externalcontact_handler.py）才会执行 main()
    main()

