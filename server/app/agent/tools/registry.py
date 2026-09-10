from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agent.tools.graph import search_graph_tool
from app.agent.tools.knowledge import search_knowledge_tool
from app.agent.tools.text2sql import text2sql_tool
from app.agent.tools.web import web_search_tool

AGENT_TOOL_NAMES = ("search_knowledge", "search_graph", "web_search", "text2sql")

AGENT_TOOLS: list[BaseTool] = [
    search_knowledge_tool,
    text2sql_tool,
    search_graph_tool,
    web_search_tool,
]


def tools_for(*, allow_web: bool = False, enable_graph: bool = False) -> list[BaseTool]:
    """按门控返回供 model.bind_tools 的工具子集。"""
    tools: list[BaseTool] = [search_knowledge_tool, text2sql_tool]
    if enable_graph:
        tools.append(search_graph_tool)
    if allow_web:
        tools.append(web_search_tool)
    return tools
