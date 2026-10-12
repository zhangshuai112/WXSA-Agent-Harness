"""
自定义网络搜索工具。

基于智谱 AI 的搜狗 Web Search API，供主 Agent 和所有子 Agent 使用。
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")


def _sync_web_search(query: str) -> str:
    try:
        # ``zai-sdk`` 0.2.x defines the client in ``zai._client`` but some
        # installations do not re-export it from the top-level ``zai``
        # package (especially when an unrelated ``zai`` package is also
        # installed). Support both layouts.
        try:
            from zai import ZhipuAiClient
        except ImportError:
            from zai._client import ZhipuAiClient

        if not ZHIPU_API_KEY:
            return "搜索失败: 未配置 ZHIPU_API_KEY"

        client = ZhipuAiClient(api_key=ZHIPU_API_KEY)
        response = client.web_search.web_search(
            search_engine="search_pro",
            search_query=query,
            count=3,  # 返回结果的条数，范围1-50，默认10
            search_recency_filter="noLimit",  # 搜索指定日期范围内的内容
        )
        if response.search_result:
            return "\n\n".join([d.content for d in response.search_result])
        return "没有搜索到任何内容！"
    except Exception as e:
        print(e)
        return f"搜索失败: {e}"


@tool("web_search", parse_docstring=True)
async def web_search(query: str) -> str:
    """
    使用搜狗的API进行Web搜索。

    Args:
        query: 需要搜索的内容或者关键字。

    Returns:
        返回搜索之后的结果。
    """
    return await asyncio.to_thread(_sync_web_search, query)


if __name__ == "__main__":
    print(asyncio.run(web_search.ainvoke("人")))
