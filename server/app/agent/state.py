"""P1 Agent graph states: thin shared base + path-specific TypedDicts.

Domain types (SearchHit / Citation / evidence item shapes) and RAG services stay
shared elsewhere. Flow fields must not cross Knowledge ↔ React.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Mapping, Sequence, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages


class BaseAgentState(TypedDict, total=False):
    """Fields already used by both knowledge_flow and ReAct with the same shape."""

    knowledge_base_id: str | None
    messages: list[dict[str, str]]
    summary: str
    ltm_hits: list[dict[str, Any]]
    answer: str
    usage: dict[str, int]
    citations: list[dict[str, Any]]


class KnowledgeState(BaseAgentState, total=False):
    """State for knowledge_flow DAG only."""

    query_type: Literal["simple", "complex"]
    sub_questions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    searched_queries: list[str]
    knowledge_gaps: list[str]
    current_qi_index: int
    last_qi_hits: int
    retrieve_phase: Literal["initial", "rewrite"]
    search_query: str
    skip_retrieve: bool
    next_flow: str
    # Supplemental retrieve budget (rewrite 后的 search 次数); not ReAct tool rounds.
    loop_count: int
    max_loops: int


class ReactState(BaseAgentState, total=False):
    """State for graph.py ReAct (agent ⇄ tools) only."""

    task: Literal["agent", "report"]
    agent_messages: Annotated[Sequence[AnyMessage], add_messages]
    web_hits: list[dict[str, Any]]
    allow_web: bool
    tool_call_count: int
    # Tools-node round count; semantics differ from KnowledgeState.loop_count.
    loop_count: int
    max_loops: int
    # Retrieval-control layer (not DAG schedulers like current_qi_index / next_flow).
    query_type: Literal["simple", "complex"]
    sub_questions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    knowledge_gaps: list[str]
    searched_queries: list[str]
    # Latest tool-round sufficiency summary (not a DAG scheduler).
    sufficiency: dict[str, Any]


def user_question(state: Mapping[str, Any]) -> str:
    """Read the latest user text from messages (both paths) or ReAct agent_messages."""
    for item in reversed(state.get("messages") or []):
        if isinstance(item, dict) and item.get("role") == "user":
            return item.get("content") or ""
    for item in reversed(list(state.get("agent_messages") or [])):
        if isinstance(item, HumanMessage):
            content = item.content
            return content if isinstance(content, str) else str(content)
    return ""
