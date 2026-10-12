# 导入 Python 标准库的类型提示模块，用于类型注解
from typing import List, Dict, Any
# 导入 Pydantic 库，用于数据验证和模型定义
# BaseModel: Pydantic 的基础模型类，所有数据模型都继承自它
# Field: 用于定义字段的约束条件、默认值、描述等信息
from pydantic import BaseModel, Field
# 导入类型扩展模块，提供 Annotated 类型注解（Python 3.9+ 新特性）
from typing_extensions import Annotated

# 导入操作系统和系统相关模块，用于路径操作
import os,sys
# 将项目根目录添加到 Python 模块搜索路径的最前面
# 这样可以直接使用 from models.xxx import xxx 的方式导入模块
# os.path.abspath(__file__): 获取当前文件的绝对路径
# os.path.dirname(...): 获取目录路径，连续调用4次向上4级目录（到项目根目录）
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# 导入自定义的基础模型类，所有业务模型都继承自它
# 它提供了 get_schema_json() 和 get_example_json() 等方法，用于 LLM 结构化输出
from .wecom_base_model import WecomBaseModel

# 使用 Annotated 类型约束
# 定义一个时间字符串类型，使用正则表达式验证格式必须是 "YYYY-MM-DD HH:MM:SS"
# 这个类型会在 Pydantic 验证时自动检查字符串是否符合时间格式
TimeStr = Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')]

#####  员工  #####
# 员工信息模型类，继承自 WecomBaseModel
class EmployeeInfo(WecomBaseModel):
    ''' 员工信息 '''
    # 员工的企业微信 user_id，用于唯一标识员工
    user_id: str = Field(default="", description="用户ID")
    # 员工的姓名
    name: str = Field(default="", description="名称")


#####  标签  #####
# 标签信息模型类，表示一个标签的基本信息
class TagInfo(WecomBaseModel):
    ''' 标签信息 '''
    # 标签的唯一标识符
    tag_id: str = Field(default="", description="标签ID")
    # 标签的显示名称
    tag_name: str = Field(default="", description="标签名称")
    # 标签建议的原因说明（用于 AI 生成标签建议时说明为什么建议这个标签）
    tag_reason: str = Field(default="", description="标签建议原因")

# 全局标签设置模型类，包含系统中所有可用的标签列表
class TagSetting(WecomBaseModel):
    ''' 全局标签设置 '''
    # 标签列表，每个元素是一个 TagInfo 对象
    tag_setting: List[TagInfo] = Field(default=[], description="全局标签列表")

# 标签建议模型类，用于 AI 生成客户标签建议
class TagSuggestion(WecomBaseModel):
    ''' 标签建议 '''
    # 建议添加的标签列表（AI 认为应该给客户添加这些标签）
    tag_ids_add: List[TagInfo] = Field(default=[], description="建议添加的标签列表")
    # 建议删除的标签列表（AI 认为应该从客户身上移除这些标签）
    tag_ids_remove: List[TagInfo] = Field(default=[], description="建议删除的标签列表")

    # 类方法装饰器，表示这是一个类方法，可以通过类直接调用，不需要创建实例
    @classmethod
    def get_example_instance(cls):
        # 返回一个示例实例，用于在 LLM Prompt 中展示期望的输出格式
        # cls 是类本身（TagSuggestion），return cls(...) 相当于 return TagSuggestion(...)
        return cls(
            # 示例：建议添加两个标签
            tag_ids_add=[
                    TagInfo(tag_id="tag_id_1", tag_name="tag_name_1", tag_reason="建议添加该标签的原因"),
                    TagInfo(tag_id="tag_id_2", tag_name="tag_name_2", tag_reason="建议添加该标签的原因")
                ],
            # 示例：建议删除两个标签
            tag_ids_remove=[
                    TagInfo(tag_id="tag_id_3", tag_name="tag_name_3", tag_reason="建议删除该标签的原因"),
                    TagInfo(tag_id="tag_id_4", tag_name="tag_name_4", tag_reason="建议删除该标签的原因")
                ]
        )


#####  profile  #####
# 客户画像子项模型类，表示客户画像中的一个属性项（键值对）
class ProfileItem(WecomBaseModel):
    ''' profile子项 '''
    # 属性名称，如"姓名"、"年龄"、"兴趣爱好"等
    item_name: str = Field(default="", description="profile子项的名称")
    # 属性值，如"张博士"、"25"、"运动、音乐"等
    item_value: str = Field(default="", description="profile子项的值")


#####  客户  #####
# 客户基本信息模型类
class CustomerInfo(WecomBaseModel):
    ''' 客户信息 '''
    # 外部用户ID，企业微信中客户的唯一标识
    external_id: str = Field(default="", description="外部用户ID")
    # 微信 union_id，用于跨应用识别同一用户
    union_id: str = Field(default="", description="union_id")
    # 负责跟进该客户的员工 user_id
    follow_user_id: str = Field(default="", description="关注用户ID")
    # 客户的昵称或备注名
    nick_name: str = Field(default="", description="昵称")

# 客户标签模型类，包含客户当前拥有的所有标签
class CustomerTags(WecomBaseModel):
    ''' 客户标签 '''
    # 客户标签列表，每个元素是一个 TagInfo 对象
    customer_tags: List[TagInfo] = Field(default=[], description="客户标签")

# 客户画像模型类，包含客户的详细画像信息（多维度属性）
class CustomerProfile(WecomBaseModel):
    ''' 客户 profile '''
    # 客户画像属性列表，每个元素是一个 ProfileItem 对象（键值对）
    profile_items: List[ProfileItem] = Field(default=[], description="profile子项的列表")

    # 类方法：返回客户画像的示例实例
    # 这个示例展示了客户画像应该包含哪些维度的信息
    @classmethod
    def get_example_instance(cls):
        return cls(
            # 示例客户画像，包含20多个维度的客户信息
            profile_items=[
                    # 基本信息维度
                    ProfileItem(item_name="姓名", item_value="张博士"),
                    ProfileItem(item_name="年龄", item_value="25"),
                    ProfileItem(item_name="性别", item_value="男"),
                    ProfileItem(item_name="婚姻状况", item_value="未婚"),
                    ProfileItem(item_name="兴趣爱好", item_value="运动、音乐"),
                    ProfileItem(item_name="教育程度", item_value="本科"),
                    # 饮酒相关维度
                    ProfileItem(item_name="饮酒频率", item_value="每周一次"),
                    ProfileItem(item_name="饮酒场景", item_value="聚会、独自小酌"),
                    ProfileItem(item_name="饮酒金额", item_value="100元"),
                    ProfileItem(item_name="饮酒口感偏好", item_value="醇厚"),
                    ProfileItem(item_name="饮酒购买渠道", item_value="线下实体店、线上电商平台"),
                    # 生活相关维度
                    ProfileItem(item_name="饮食习惯", item_value="无忌口、偏好的菜系等"),
                    ProfileItem(item_name="出行方式", item_value="自驾、公交、地铁"),
                    ProfileItem(item_name="宠物情况", item_value="是否养宠物及宠物种类"),
                    ProfileItem(item_name="娱乐活动偏好", item_value="看电影、唱K等具体活动"),
                    ProfileItem(item_name="家庭成员", item_value="如配偶、子女等"),
                    # 酒类消费相关维度
                    ProfileItem(item_name="常喝的酒的种类", item_value="如白酒、红酒、啤酒等"),
                    ProfileItem(item_name="喜欢的酒的品牌", item_value="如茅台、五粮液等"),
                    ProfileItem(item_name="消费频率", item_value="如每周一次、每月几次等"),
                    ProfileItem(item_name="消费场景", item_value="如聚会、独自小酌等"),
                    ProfileItem(item_name="每次消费的大致金额", item_value="如100元"),
                    ProfileItem(item_name="对酒的口感偏好", item_value="如醇厚、清爽等"),
                    ProfileItem(item_name="购买渠道", item_value="如线下实体店、线上电商平台等")
                ]
        )


#####  聊天对话  #####
# 聊天消息模型类，表示一条聊天消息
class ChatMessage(WecomBaseModel):
    ''' 聊天消息 '''
    # 消息发送者，如"销售人员"或"客户"
    sender: str = Field(default="", description="发送者")
    # 消息接收者，如"客户"或"销售人员"
    receiver: str = Field(default="", description="接收者")
    # 消息内容
    content: str = Field(default="", description="内容")
    # 消息发送时间，使用 TimeStr 类型确保格式正确
    msg_time: TimeStr = Field(default="", description="消息时间")

# 回复建议模型类，用于 AI 生成聊天回复建议
class ReplySuggestion(WecomBaseModel):
    ''' 回复建议 '''
    # AI 生成的建议回复内容
    reply_content: str = Field(default="", description="回复内容")
    # AI 生成该回复的原因说明（解释为什么这样回复）
    reply_reason: str = Field(default="", description="回复原因")

    # 类方法：返回回复建议的示例实例
    @classmethod
    def get_example_instance(cls):
        return cls(
            reply_content="回复内容",
            reply_reason="回复原因"
        )

# 聊天记录模型类，包含多条聊天消息
class ChatHistory(WecomBaseModel):
    ''' 聊天记录 '''
    # 聊天消息列表，按时间顺序排列
    chat_msgs: List[ChatMessage] = Field(default=[], description="聊天记录")

# 客服聊天记录模型类，包含客户与客服的对话记录
class KFChatHistory(WecomBaseModel):
    ''' 客服聊天记录 '''
    # 客服聊天消息列表
    kf_chat_msgs: List[ChatMessage] = Field(default=[], description="客服聊天记录")

#####  订单  #####
# 订单信息模型类
class OrderInfo(WecomBaseModel):
    ''' 订单信息 '''
    # 订单ID，唯一标识一个订单
    order_id: str = Field(default="", description="订单ID")
    # 订单中的商品名称列表
    order_products: List[str] = Field(default="", description="订单产品")
    # 订单创建时间
    order_create_time: TimeStr = Field(default="", description="订单创建时间")

# 订单历史模型类，包含客户的所有历史订单
class OrderHistory(WecomBaseModel):
    ''' 订单历史 '''
    # 订单列表，每个元素是一个 OrderInfo 对象
    orders: List[OrderInfo] = Field(default=[], description="历史订单记录")
    
#####  日程  #####

# 日程建议模型类，用于 AI 生成客户跟进日程建议
class ScheduleSuggestion(WecomBaseModel):
    ''' 日程建议 '''
    # 日程标题，描述日程的具体事项
    title: str = Field(default="",title="Title", description="日程标题")
    # 日程开始时间，格式为 "YYYY-MM-DD HH:MM:SS"
    start_time: TimeStr = Field(default="",title="Start Time", description="开始时间，格式 yyyy-MM-dd HH:mm:ss")
    # 日程持续时间，单位：分钟
    duration: int = Field(default=30,title="Duration", description="持续时间，单位分钟")
    # 日程建议的原因说明（解释为什么需要这个日程）
    schedule_reason: str = Field(default="",title="Schedule Reason", description="日程建议原因")

    # 类方法：返回日程建议的示例实例
    @classmethod
    def get_example_instance(cls):
        return cls(
            title="日程标题，包含具体事项说明",
            start_time="2025-08-01 10:00:00",
            duration=60,
            schedule_reason="日程建议原因"
        )

#####  讨论  #####

# 自由讨论输出模型类，用于处理未明确意图的对话场景
class JustTalkOutput(WecomBaseModel):
    ''' 讨论应答 '''
    # AI 生成的应答内容（用于回答用户的问题或进行闲聊）
    just_talk_output: str = Field(default="", description="讨论应答")
    
    # 类方法：返回自由讨论输出的示例实例
    @classmethod
    def get_example_instance(cls):
        return cls(
            just_talk_output="输出应答内容"
        )


#####  意图检测  #####
# 意图模型类，用于表示用户的意图
class Intent(WecomBaseModel):
    ''' 意图 '''
    # 意图ID，如 "chat_suggestion"、"tag_suggestion" 等
    intent_id: str = Field(default="", description="意图ID")
    # 意图的描述说明
    intent_description: str = Field(default="", description="意图描述")

    # 类方法：返回意图的示例实例
    @classmethod
    def get_example_instance(cls):
        return cls(
            intent_id="chat_suggestion",
            intent_description="生成聊天建议"
        )


# 任务结果模型类，用于表示智能体执行任务的结果
class TaskResult(WecomBaseModel):
    # 任务执行的结果内容（主要输出）
    task_result: str = Field(default="", description="任务结果")
    # 任务结果的解释说明（解释为什么是这个结果）
    task_result_explain: str = Field(default="", description="任务结果解释")
    # 任务结果代码：0 表示结果有效，1 表示结果无效
    task_result_code: int = Field(default=1, description="任务结果代码，0: 结果有效，1: 结果无效")

# 节点执行结果模型类，用于表示 LangGraph 中某个节点的执行结果
class NodeResult(WecomBaseModel):
    ''' 节点执行 '''
    # 执行的节点名称，如 "intent_detection"、"chat_suggestion" 等
    execute_node_name: str = Field(default="", description="节点名称")
    # 节点执行结果代码：0 表示成功，1 表示失败
    execute_result_code: int = Field(default=1, description="节点执行结果代码，0: 成功，1: 失败")
    # 节点执行结果消息（成功或失败的描述信息）
    execute_result_msg: str = Field(default="", description="节点执行结果消息")
    # 节点执行过程中的异常信息列表（如果有异常）
    execute_exceptions: List[str] = Field(default=[], description="节点执行异常信息")
    