 # 导入操作系统模块，用于环境变量和路径操作
import os
# 导入系统模块，用于路径操作
import sys
# 导入时间模块，用于时间操作（如 sleep 避免请求过快）
import time
# 导入类型提示模块，用于类型注解（List、Dict、Any、Optional 类型）
from typing import List, Dict, Any, Optional

# 添加项目根目录到Python路径，以便导入项目内的其他模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用2次向上2级目录（到项目根目录）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入存储 API 客户端类，用于将数据写入 LangGraph Store
from wechat_sync.wecom_store_api import create_wecom_store_api
# 导入企业微信 API 客户端类，用于调用企业微信 API 获取数据
from wechat_client.wechat_work_api import WechatWorkAPI
# 导入日志配置函数，用于设置日志系统
from logger.logging import setup_logging

# 创建日志记录器，用于记录企业微信外部联系人数据同步相关的日志信息
logger = setup_logging("wechat_work_sync")

# 企业微信外部联系人数据同步服务类，负责从企业微信 API 获取客户和标签数据并同步到 LangGraph Store
class WechatWorkSync:
    """企业微信外部联系人数据同步服务
    
    主要功能：
    - 同步指定员工的外部联系人数据（客户信息）
    - 同步标签数据（企业标签和策略标签）
    """
    
    # 初始化方法，创建同步服务实例
    def __init__(self):
        """
        初始化同步服务，创建必要的 API 客户端实例
        """
        # 创建企业微信 API 客户端实例（用于调用企业微信 API）
        self.wechat_work_api = WechatWorkAPI()
        # 创建存储 API 客户端实例（用于将数据写入 LangGraph Store）
        # 从环境变量中读取服务器地址、用户ID和密码
        self.wecom_store_api = create_wecom_store_api()
        # 标签策略 ID（默认 2，表示规则组标签；0 表示企业标签）
        # 从环境变量读取，如果不存在则使用默认值 "2"
        self.tags_strategy_id = int(os.getenv("TAG_STRATEGY_ID", "2"))  # 标签策略id
        
    def sync_external_contacts_by_user(self, userid: str) -> Dict[str, Any]:
        """
        同步指定员工的外部联系人数据
        
        Args:
            userid: 员工ID
            
        Returns:
            dict: 同步结果统计
        """
        logger.info(f"开始同步员工 {userid} 的外部联系人数据...")
        
        try:
            success_count = 0
            error_count = 0
            cursor = ""
            total_contacts = 0
            
            while True:
                # 分页获取外部联系人详情
                logger.info(f"获取外部联系人数据，cursor: {cursor}")
                result = self.wechat_work_api.get_external_contact_list_by_user(
                    userid=userid,
                    cursor=cursor,
                    limit=1000
                )
                
                external_contact_list = result.get('external_contact_list', [])
                next_cursor = result.get('next_cursor', '')

                if not external_contact_list:
                    logger.info("没有更多外部联系人数据")
                    break
                
                logger.info(f"获取到 {len(external_contact_list)} 个外部联系人")
                total_contacts += len(external_contact_list)
                
                # 处理每个外部联系人
                for item in external_contact_list:
                    try:
                        external_contact = item.get('external_contact', {})
                        follow_info = item.get('follow_info', {})
                        
                        # 解析对应字段
                        external_id = external_contact.get('external_userid', '')
                        union_id = external_contact.get('unionid', '')
                        follow_user_id = follow_info.get('userid', '')
                        name = external_contact.get('name', '')
                        remark_name = follow_info.get('remark', '')
                        tag_ids = follow_info.get('tag_id', [])
                        
                        # 写入到 WecomStoreAPI
                        self.wecom_store_api.upsert_external_user(
                            external_id=external_id,
                            union_id=union_id,
                            follow_user_id=follow_user_id,
                            name=name,
                            remark_name=remark_name,
                            tags=tag_ids
                        )
                        
                        success_count += 1
                        
                    except Exception as e:
                        logger.error(f"写入外部联系人失败 {external_contact.get('external_userid', '')}: {e}")
                        error_count += 1
                
                # 检查是否还有下一页
                if not next_cursor:
                    logger.info("所有外部联系人数据获取完成")
                    break
                
                cursor = next_cursor
                time.sleep(1)  # 避免请求过快
            
            result = {
                'userid': userid,
                'total_contacts': total_contacts,
                'success_count': success_count,
                'error_count': error_count
            }
            
            logger.info(f"外部联系人同步完成: 总计 {total_contacts} 个，成功 {success_count} 个，失败 {error_count} 个")
            return result
            
        except Exception as e:
            error_msg = f"同步员工 {userid} 的外部联系人数据失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def sync_tags(self) -> Dict[str, Any]:
        """
        同步标签数据：将企业标签和策略标签合并后写入到 WecomStoreAPI
        
        Returns:
            dict: 同步结果统计
        """
        logger.info("开始同步标签数据...")
        
        try:
            # 获取策略标签
            logger.info("获取策略标签...")
            all_tags = self.wechat_work_api.get_strategy_tag_list(strategy_id=self.tags_strategy_id)
            logger.info(f"获取到 {len(all_tags)} 个策略标签")
            
            # 写入到 WecomStoreAPI
            success_count = 0
            error_count = 0
            
            for tag in all_tags:
                try:
                    self.wecom_store_api.upsert_tags_setting(
                        tag_id=tag.get('id', ''),
                        strategy_id=tag.get('strategy_id', 0),
                        group_id=tag.get('group_id', ''),
                        group_name=tag.get('group_name', ''),
                        tag_name=tag.get('name', ''),
                        deleted=False
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"写入标签失败 {tag.get('id', '')}: {e}")
                    error_count += 1
            
            result = {
                'total_tags': len(all_tags),
                'success_count': success_count,
                'error_count': error_count
            }
            
            logger.info(f"标签同步完成: 成功 {success_count} 个，失败 {error_count} 个")
            return result
            
        except Exception as e:
            error_msg = f"同步标签数据失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg)


def main():
    """测试函数"""
    try:
        # 初始化同步服务
        sync_service = WechatWorkSync()
        
        print("企业微信数据同步测试")
        print("=" * 50)
        
        
        #print("测试同步员工数据...")
        #external_result = sync_service.sync_external_contacts_by_user('ChengJianZhang')
        #print(f"员工数据同步结果: {external_result}")

        print("测试同步标签数据...")
        tag_result = sync_service.sync_tags()
        print(f"标签数据同步结果: {tag_result}")

        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    main()
