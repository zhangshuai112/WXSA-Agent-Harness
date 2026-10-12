## 目标
1、实现一个企微运营 Harness 的 Web API，用于与企微运营 Harness进行交互。
2、实现一个企微运营 Harness 的 Web UI，用于与企微运营 Harness进行交互。

## Web API 技术栈
- FastAPI
- Python
- 代码目录：@wecom_agent_api 

## Web UI 技术栈
- HTML
- CSS
- JavaScript
- 代码目录：@wecom_agent_ui

## 功能
1、登录
2、底部菜单展示：生成客户画像（profile_suggestion）
3、底部菜单展示：生成客户标签（tag_suggestion）
4、底部菜单展示：生成聊天建议（chat_suggestion）
5、底部菜单展示：生成客服建议（kf_chat_suggestion）
6、底部菜单展示：生成日程建议（schedule_suggestion）

内容区：
1、底部是输入框，用户输入的内容作为talk_suggestion的输入。
2、底部的输入框，也用于展示菜单id（如果是直接点击菜单的话）。
3、内容区的主要区域，用户展示agent的返回结果。

agent的返回结果：
1、agent使用流式返回结果。
2、agent的返回结果，包括两个主要部分：
    1、task_result：任务执行结果。
    2、node_result：节点执行结果。
3、参考类的定义：

```python
class TaskResult(WecomBaseModel):
    task_result: str = Field(default="", description="任务结果")
    task_result_explain: str = Field(default="", description="任务结果解释")
    task_result_code: int = Field(default=1, description="任务结果代码，0: 结果有效，1: 结果无效")

class NodeResult(WecomBaseModel):
    ''' 节点执行 '''
    execute_node_name: str = Field(default="", description="节点名称")
    execute_result_code: int = Field(default=1, description="节点执行结果代码，0: 成功，1: 失败")
    execute_result_msg: str = Field(default="", description="节点执行结果消息")
    execute_exceptions: List[str] = Field(default=[], description="节点执行异常信息")
```


agent的返回结果的示例：

profile_suggestion 流式日志文件：@profile.log
chat_suggestion 流式日志文件：@chat.log

如果agent需要人工介入/确认（human in the loop）：
通过 get_interrupt 获取需要确认的事项，并在页面展示。
获取的interrupt 信息：可以参考这个日志 @get_interrupt.log

人工需要输入的统一定义为三个按钮（选项）：
```python
    ## 期待的反馈结果格式：
    #    {
    #        confirmed: "ok" | "discard" | "recreate"
    #    }
    ## debug in studio：
    # {"confirmed": "ok"}
    # {"confirmed": "discard"}
    # {"confirmed": "recreate"}
```

@wecom_agent_api/wecom_agent_api.py 是已经封装好的企微运营 Harness client API，
@wecom_agent_api/wecom_agent_api_test.py 是已经封装好的企微运营 Harness client API 的测试代码。


页面UI邀请：
1、登录页面：
    用户名、密码登录。
    登录成功后，跳转到主页面。
2、主页面：
    底部是菜单
    内容区域分为：显示区域、输入区域。
    显示区域用于展示agent的返回结果。
    输入区域用于用户输入内容（如果是点击菜单，输入区域的值为菜单id）。
    输入区域的输入内容，点击发送按钮，发送给agent。（如果是点击菜单，直接发送，不需要用户再点击发送按钮）
3、页面宽度：360px（目的是适配企业微信侧边栏的宽度）

