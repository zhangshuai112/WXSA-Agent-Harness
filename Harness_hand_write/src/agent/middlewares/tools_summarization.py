"""
摘要中间件工厂
基于 DeepAgents 0.4 内置的 create_summarization_tool_middleware 创建，
提供以下能力：
1. 自动摘要：上下文接近模型上限时自动压缩历史消息。
2. 主动摘要：提供 compact_conversation 工具，Agent 可在关键节点（如收到子 Agent 报告后）主动调用。
"""

# 导入联合类型，允许 model 参数接收字符串或模型实例。
from typing import Union

# 导入聊天模型的抽象基类，用于标注模型实例参数。
from langchain_core.language_models import BaseChatModel
# 导入创建摘要工具中间件的工厂函数。
from deepagents.middleware.summarization import create_summarization_tool_middleware
# 导入工厂函数所返回的具体中间件类型。
from deepagents.middleware.summarization import SummarizationToolMiddleware
# 导入组合式后端类型，用于访问持久化存储等后端能力。
from deepagents.backends import CompositeBackend


# 创建并配置对话摘要工具中间件。
def build_summarization_middleware(
    # backend 为摘要中间件提供保存完整对话记录的后端。
    backend: CompositeBackend,
    # model 指定生成摘要的模型，默认使用较轻量的 gpt-4o-mini。
    model: Union[str, BaseChatModel] = "gpt-4o-mini",
# 声明该工厂函数返回摘要工具中间件实例。
) -> SummarizationToolMiddleware:
    """
    构建摘要工具中间件。

    该中间件是一个 SummarizationToolMiddleware 实例，内部自动包含了一个
    SummarizationMiddleware（负责自动摘要），并额外提供了一个名为
    `compact_conversation` 的工具，供 Agent 主动触发对话压缩。

    参数:
        backend: 沙箱后端（用于持久化被压缩的完整对话历史）。
        model: 用于生成摘要的模型，可以是字符串标识或模型实例。
               建议使用轻量、便宜的模型以节省成本（如 "gpt-4o-mini"）。

    返回:
        SummarizationToolMiddleware: 可直接传入 create_deep_agent 的 middleware 列表。

    """
    # 该工厂函数会自动创建一个 SummarizationMiddleware 并将其嵌入到
    # SummarizationToolMiddleware 中。触发阈值等参数使用框架默认值，
    # 通常为上下文达到 85% 时触发自动摘要，这已满足多数生产场景。
    # 调用框架工厂；其内部会组合自动摘要和主动压缩对话的工具。
    return create_summarization_tool_middleware(
        # 将调用方指定的摘要模型传给工厂函数。
        model=model,
        # 将调用方提供的组合后端传给工厂函数。
        backend=backend,
    )
