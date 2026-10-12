# 导入操作系统模块，用于环境变量和路径操作
import os
# 导入 JSON 处理模块，用于解析和生成 JSON 数据
import json
# 导入时间模块，用于时间戳操作和 token 过期时间管理
import time
# 导入 HTTP 请求库，用于调用企业微信 API
import requests
# 导入类型提示模块，用于类型注解（Dict、Tuple、List 类型）
from typing import Dict, Tuple, List 
# 导入 dotenv 模块，用于从 .env 文件加载环境变量
from dotenv import load_dotenv
# 导入系统模块，用于路径操作
import sys
# 将项目根目录添加到 Python 模块搜索路径中，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 加载环境变量（从 .env 文件读取配置信息，如 CORP_ID、APP_SECRET 等）
load_dotenv()

# 创建日志记录器，用于记录企业微信 API 相关的日志信息
logger = setup_logging("wechat_work_api")

# 企业微信外部联系人 API 服务类，封装了企业微信的各种 API 调用功能
class WechatWorkAPI:
    """企业微信外部联系人API服务类
    
    提供以下功能：
    - 获取 access_token（API 访问凭证）
    - 获取员工信息
    - 获取客户列表和详情
    - 获取企业标签配置
    - 读取客服消息
    - 管理客服会话状态
    - 发送通知消息
    """
    
    # 初始化方法，设置企业微信 API 所需的配置信息
    def __init__(self):
        """初始化 WechatWorkAPI 实例"""
        # 从环境变量中获取企业微信的企业 ID（corp_id）
        self.corp_id = os.getenv('CORP_ID')
        # 从环境变量中获取企业微信的应用密钥（用于获取 access_token）
        self.app_secret = os.getenv('APP_SECRET')
        # 从环境变量中获取企业微信的应用 ID（agentid）
        self.app_id = os.getenv('AGENT_ID')
        # 初始化 access_token 为 None（首次使用时需要获取）
        self.access_token = None
        # 初始化 token 过期时间戳为 0（表示 token 尚未获取或已过期）
        self.token_expires_time = 0
        
        # 验证必要的配置信息是否存在
        if not self.corp_id or not self.app_secret or not self.app_id:
            # 如果缺少配置信息，抛出异常，提示用户设置环境变量
            raise ValueError("请在环境变量中设置CORP_ID、APP_SECRET和AGENT_ID")
    
    # 获取企业微信 access_token 的方法（access_token 是调用企业微信 API 的凭证）
    def get_access_token(self):
        """获取access_token（API 访问凭证）
        
        Returns:
            str: access_token 字符串，用于后续 API 调用
            
        Raises:
            Exception: 如果获取 token 失败，抛出异常
        """
        # 检查 token 是否过期（提前5分钟刷新，确保 token 在使用时不会过期）
        # time.time(): 获取当前时间戳（秒）
        # self.token_expires_time - 300: token 过期时间减去 300 秒（5分钟）
        if self.access_token and time.time() < (self.token_expires_time - 300):
            # 如果 token 存在且未过期，直接返回缓存的 token（避免频繁请求）
            return self.access_token
        
        # 企业微信获取 access_token 的 API 地址
        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        # 构建请求参数：企业 ID 和应用密钥
        params = {
            'corpid': self.corp_id,        # 企业 ID
            'corpsecret': self.app_secret  # 应用密钥
        }
        
        # 使用 try-except 捕获请求异常
        try:
            # 发送 GET 请求获取 access_token，设置超时时间为 30 秒
            response = requests.get(url, params=params, timeout=30)
            # 检查 HTTP 状态码，如果不是 2xx，会抛出异常
            response.raise_for_status()
            
            # 将响应内容解析为 JSON 格式
            data = response.json()
            
            # 检查企业微信 API 返回的错误码（errcode == 0 表示成功）
            if data.get('errcode') == 0:
                # 保存获取到的 access_token
                self.access_token = data['access_token']
                # 计算 token 的过期时间戳（当前时间 + 有效期，默认 7200 秒即 2 小时）
                self.token_expires_time = time.time() + data.get('expires_in', 7200)
                # 记录成功日志，包含 token 的有效期信息
                logger.info(f"获取access_token成功，有效期：{data.get('expires_in', 7200)}秒")
                # 返回 access_token
                return self.access_token
            else:
                # 如果 API 返回错误，提取错误信息
                errmsg = data.get('errmsg', '未知错误')  # 错误消息，如果不存在则使用默认值
                errcode = data.get('errcode', 'unknown')  # 错误码，如果不存在则使用默认值
                # 构建错误消息字符串
                error_msg = f"获取access_token失败: {errmsg} (错误码: {errcode})"
                # 记录错误日志
                logger.error(error_msg)
                # 抛出异常，中断执行
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            # 捕获 HTTP 请求相关的异常（如网络错误、超时等）
            error_msg = f"请求access_token失败: {e}"
            # 记录错误日志
            logger.error(error_msg)
            # 抛出异常，中断执行
            raise Exception(error_msg)
    
    def get_user_info(self, userid):
        """获取指定员工的姓名
        
        Args:
            userid (str): 员工ID
            
        Returns:
            dict: 包含员工姓名的信息，格式如 {"name": "张三"}
        """
        access_token = self.get_access_token()
        
        url = f"https://qyapi.weixin.qq.com/cgi-bin/user/get"
        params = {
            'access_token': access_token,
            'userid': userid
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('errcode') == 0:
                # 只返回姓名信息
                return {
                    "name": result.get('name', '')
                }
            else:
                error_msg = f"获取员工信息失败: {result.get('errmsg', '未知错误')} (错误码: {result.get('errcode', 'unknown')})"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"请求员工信息失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_external_contact_list_by_user(self, userid, cursor="", limit=1000):
        """获取指定员工的客户详情
        
        Args:
            userid (str): 员工ID
            cursor (str): 分页游标，第一次传空字符串
            limit (int): 返回的最大记录数，最大1000
            
        Returns:
            dict: 包含客户详情列表和分页信息
        """
        access_token = self.get_access_token()
        
        url = f"https://qyapi.weixin.qq.com/cgi-bin/externalcontact/batch/get_by_user"
        
        data = {
            "userid_list": [userid],
            "cursor": cursor,
            "limit": limit
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f"{url}?access_token={access_token}",
                json=data,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('errcode') == 0:
                external_contact_list = result.get('external_contact_list', [])
                next_cursor = result.get('next_cursor', '')
                
                # 处理返回的数据，确保包含external_contact和follow_info字段
                processed_list = []
                for item in external_contact_list:
                    processed_item = {
                        'external_contact': item.get('external_contact', {}),
                        'follow_info': item.get('follow_info', {})
                    }
                    processed_list.append(processed_item)
                
                return {
                    'external_contact_list': processed_list,
                    'next_cursor': next_cursor
                }
            else:
                error_msg = f"获取客户详情失败: {result.get('errmsg', '未知错误')} (错误码: {result.get('errcode', 'unknown')})"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"请求客户详情失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_corp_tag_list(self):
        """获取企业标签配置信息
        
        Returns:
            list: 标签列表，每个标签包含group_id、group_name、strategy_id字段
        """
        access_token = self.get_access_token()
        
        url = f"https://qyapi.weixin.qq.com/cgi-bin/externalcontact/get_corp_tag_list"
        
        data = {}
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f"{url}?access_token={access_token}",
                json=data,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('errcode') == 0:
                tag_group = result.get('tag_group', [])
                
                # 提取所有标签并添加上层字段
                all_tags = []
                for group in tag_group:
                    group_id = group.get('group_id', '')
                    group_name = group.get('group_name', '')
                    strategy_id = group.get('strategy_id', 0)  # 如果不存在默认为0
                    
                    # 遍历组内的标签
                    for tag in group.get('tag', []):
                        # 复制标签原有字段并添加上层字段
                        tag_item = {
                            'strategy_id': strategy_id,
                            'group_id': group_id,
                            'group_name': group_name,
                            'id': tag.get('id', ''),
                            'name': tag.get('name', ''),
                            'create_time': tag.get('create_time', 0),
                            'order': tag.get('order', 0)
                        }
                        all_tags.append(tag_item)
                
                return all_tags
            else:
                error_msg = f"获取企业标签失败: {result.get('errmsg', '未知错误')} (错误码: {result.get('errcode', 'unknown')})"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"请求企业标签失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_strategy_tag_list(self, strategy_id):
        """获取企业规则组标签
        
        Args:
            strategy_id (int): 规则组id，默认为2
            
        Returns:
            list: 标签列表，每个标签包含group_id、group_name、strategy_id字段
        """
        access_token = self.get_access_token()
        
        url = f"https://qyapi.weixin.qq.com/cgi-bin/externalcontact/get_strategy_tag_list"
        
        data = {
            'strategy_id': strategy_id
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f"{url}?access_token={access_token}",
                json=data,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('errcode') == 0:
                tag_group = result.get('tag_group', [])
                
                # 提取所有标签并添加上层字段
                all_tags = []
                for group in tag_group:
                    group_id = group.get('group_id', '')
                    group_name = group.get('group_name', '')
                    current_strategy_id = group.get('strategy_id', strategy_id)  # 优先使用返回的strategy_id
                    
                    # 遍历组内的标签
                    for tag in group.get('tag', []):
                        # 复制标签原有字段并添加上层字段
                        tag_item = {
                            'strategy_id': current_strategy_id,
                            'group_id': group_id,
                            'group_name': group_name,
                            'id': tag.get('id', ''),
                            'name': tag.get('name', ''),
                            'create_time': tag.get('create_time', 0),
                            'order': tag.get('order', 0)
                        }
                        all_tags.append(tag_item)
                
                return all_tags
            else:
                error_msg = f"获取规则组标签失败: {result.get('errmsg', '未知错误')} (错误码: {result.get('errcode', 'unknown')})"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"请求规则组标签失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_kf_messages(self, open_kfid: str, cursor: str) -> Tuple[List[Dict], str]:
        """
        读取客服消息
        
        Args:
            open_kfid: 指定拉取某个客服账号的消息。
            cursor: 上一次调用时返回的next_cursor，默认为空。
            
        Returns:
            消息列表数据, 下一页cursor
        """
        access_token = self.get_access_token()
        
        url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg"
        params = {'access_token': access_token}
        
        data = {
            "open_kfid": open_kfid,
            "cursor": cursor,
        }

        # 初始化
        has_more = True
        msg_list = []

        while has_more:
            try:
                response = requests.post(url, params=params, json=data, timeout=30)
                response.raise_for_status()
                result = response.json()
                
                if result.get('errcode') == 0:
                    logger.info(f"读取客服消息成功，获取到 {len(result.get('msg_list', []))} 条消息，from cursor: {cursor}")

                    msg_list.extend(result.get('msg_list', []))
                    has_more = result.get('has_more', False)
                    data["cursor"] = result.get('next_cursor', '')
                
                else:
                    logger.error(f"读取客服消息失败: {result.get('errmsg')}")
                    has_more = False
                    
            except Exception as e:
                logger.error(f"读取客服消息异常: {e}")
                has_more = False

        return msg_list, data["cursor"]

    def get_kf_state(self, kfid: str, external_userid: str) -> int:
        """
        获取客服会话状态：0，未处理；1，智能助手接待； 2，接待池； 3，人工接待；4，会话结束； -1，异常
        """
        access_token = self.get_access_token()
        url = "https://qyapi.weixin.qq.com/cgi-bin/kf/service_state/get"
        params = {
            'access_token': access_token,
        }
        data = {
            "open_kfid": kfid,
            "external_userid": external_userid,
        }
        headers = {
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(url, params=params, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            if result.get('errcode') == 0:
                return result.get('service_state', -1)
            else:
                logger.error(f"获取客服状态失败: {result.get('errmsg')}")
                raise Exception(result.get('errmsg'))
                
        except Exception as e:
            logger.error(f"获取客服状态异常: {e}")
            raise e

    def trans_kf_state_to_human(self, kfid: str, external_userid: str) -> bool:
        """
        分配客服会话（进入接待池，等待人工接待）
        """
        access_token = self.get_access_token()
        url = "https://qyapi.weixin.qq.com/cgi-bin/kf/service_state/trans"
        params = {
            'access_token': access_token,
        }
        data = {
            "open_kfid": kfid,
            "external_userid": external_userid,
            "service_state": 2,
        }
        headers = {
            'Content-Type': 'application/json'
        }
        try:
            response = requests.post(url, params=params, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            if result.get('errcode') == 0:
                return True
            else:
                logger.error(f"分配客服会话失败: {result.get('errmsg')}")
                raise Exception(result.get('errmsg'))
        except Exception as e:
            logger.error(f"分配客服会话异常: {e}")
            raise e



    def notify_msg(self, user_id: str, content: str) -> bool:
        """通知指定员工

        Args:
            user_id (str): 员工ID
            content (str): 通知内容

        Returns:
            bool: 通知是否成功
        """

        if not user_id or not content:
            raise ValueError("user_id, content不能为空")

        access_token = self.get_access_token()

        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send"

        params = {
            'access_token': access_token,
        }

        data_text = {
            'touser': user_id,
            'msgtype': 'text',
            'agentid': self.app_id,
            'text': {
                'content': content
            },
            'safe': 1,
            'enable_id_trans': 1,
            'enable_duplicate_check': 1,
            'duplicate_check_interval': 300
        }

        headers = {
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(url, params=params, json=data_text, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('errcode') == 0:
                # 只返回通知ID信息
                return True
            else:
                errcode = result.get('errcode', 'unknown')
                errmsg = result.get('errmsg', '未知错误')
                error_msg = f"发送通知失败: {errmsg} (错误码: {errcode})"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"请求发送通知失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def add_strategy_tag(self, strategy_id: int, group_name: str, tag_name: str) -> Dict:
        """初始化策略标签
        
        Args:
            strategy_id (int): 策略id
            group_name (str): 组名
            tag_name (str): 标签名
        Returns:
            Dict: 执行结果
        """
        access_token = self.get_access_token()
        url = f"https://qyapi.weixin.qq.com/cgi-bin/externalcontact/add_strategy_tag"
        params = {
            'access_token': access_token,
        }
        data = {
            'strategy_id': strategy_id,
            'group_name': group_name,
            'tag': [{'name': tag_name}]
        }
        headers = {
            'Content-Type': 'application/json'
        }
        try:
            response = requests.post(url, params=params, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            if result.get('errcode') == 0:
                return result
            else:
                logger.error(f"添加策略标签失败: {result.get('errmsg')}")
                raise Exception(result.get('errmsg'))
        except Exception as e:
            logger.error(f"添加策略标签异常: {e}")
            raise e



    def init_strategy_tags(self):
        """初始化策略标签"""
        strategy_tags = [
            {'strategy_id': 2, 'group_name': '基础属性', 'tag_name': '高净值客户'},
            {'strategy_id': 2, 'group_name': '基础属性', 'tag_name': '中年男性'},
            {'strategy_id': 2, 'group_name': '基础属性', 'tag_name': '已婚有子女'},
            {'strategy_id': 2, 'group_name': '基础属性', 'tag_name': '家有老人'},
            {'strategy_id': 2, 'group_name': '消费行为', 'tag_name': '酱香白酒偏好'},
            {'strategy_id': 2, 'group_name': '消费行为', 'tag_name': '茅台收藏'},
            {'strategy_id': 2, 'group_name': '消费行为', 'tag_name': '高频团购'},
            {'strategy_id': 2, 'group_name': '消费行为', 'tag_name': '节日礼品采购'},
            {'strategy_id': 2, 'group_name': '消费行为', 'tag_name': '高端红酒需求'},
            {'strategy_id': 2, 'group_name': '社交关系', 'tag_name': '商务宴请多'},
            {'strategy_id': 2, 'group_name': '社交关系', 'tag_name': '家庭聚会多'},
            {'strategy_id': 2, 'group_name': '服务敏感度', 'tag_name': '需优先预留'},
            {'strategy_id': 2, 'group_name': '服务敏感度', 'tag_name': '依赖专业鉴酒服务'},
            {'strategy_id': 2, 'group_name': '性别', 'tag_name': '女性'},
            {'strategy_id': 2, 'group_name': '性别', 'tag_name': '男性'},
        ]
        for tag in strategy_tags:
            self.add_strategy_tag(tag['strategy_id'], tag['group_name'], tag['tag_name'])


if __name__ == "__main__":
    import sys
    from pprint import pprint
    print(sys.argv)
    api = WechatWorkAPI()

    if len(sys.argv) > 1:
        if sys.argv[1] == "token":
            pprint(api.get_access_token())
        if sys.argv[1] == "user":
            pprint(api.get_user_info("ChengJianZhang"))
        if sys.argv[1] == "euser":
            pprint(api.get_external_contact_list_by_user("ChengJianZhang"))
        if sys.argv[1] == "tag":
            pprint(api.get_corp_tag_list())
        if sys.argv[1] == "stag":
            pprint(api.get_strategy_tag_list(2))
        if sys.argv[1] == "initag":
            pprint(api.init_strategy_tags())
        if sys.argv[1] == "kfstate":
            pprint(api.get_kf_state("wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw", "wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg"))
        if sys.argv[1] == "kftrans":
            pprint(api.trans_kf_state_to_human("wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw", "wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg"))
        if sys.argv[1] == "kf":
            results, cursor = api.get_kf_messages("wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw", "HHFq49uYHoiCuZRv9Mao")
            for r in results:
                pprint(json.dumps(r, ensure_ascii=False, indent=4))
            print(cursor)

    print("测试命令:")
    print("python wechat_client/wechat_work_api.py token")
    print("python wechat_client/wechat_work_api.py user")
    print("python wechat_client/wechat_work_api.py euser")
    print("python wechat_client/wechat_work_api.py tag")
    print("python wechat_client/wechat_work_api.py stag")
    print("python wechat_client/wechat_work_api.py initag")
    print("python wechat_client/wechat_work_api.py kf") 
    print("python wechat_client/wechat_work_api.py kfstate")
    print("python wechat_client/wechat_work_api.py kftrans")