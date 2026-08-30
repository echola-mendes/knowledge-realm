from __future__ import annotations

from typing import Any

from app.config import get_settings

CHAT_CALLS = 0
SYSTEM_PROMPT = (
    "若资料非空：只根据资料回答，禁止编造出处。"
    "若资料为空：进行正常对话，不要说知识库没有相关内容。"
)


def llm_keys_ready() -> bool:
    return bool(get_settings().llm_api_key.strip())


LAST_USAGE: dict[str, int] | None = None


def chat(
    question: str,
    context: str,
    history: list[tuple[str, str]] | None = None,
    *,
    summary: str | None = None,
    ltm: list[dict[str, str]] | None = None,
) -> str:
    """生成回答。真实调用时把 token 用量写入 LAST_USAGE（供 Agent generate 读取）。"""
    global LAST_USAGE
    answer, usage = chat_with_usage(question, context, history, summary=summary, ltm=ltm)
    LAST_USAGE = usage
    return answer


def chat_with_usage(
    question: str,
    context: str,
    history: list[tuple[str, str]] | None = None,
    *,
    summary: str | None = None,
    ltm: list[dict[str, str]] | None = None,
) -> tuple[str, dict[str, int] | None]:
    """返回 (回答, token 用量)。usage 结构：prompt_tokens / completion_tokens / total_tokens。"""
    global CHAT_CALLS
    CHAT_CALLS += 1
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    system = SYSTEM_PROMPT + "\n\n资料：\n{context}"
    if ltm:
        lines = "\n".join(f"- [{row.get('kind', '')}] {row.get('content', '')}" for row in ltm if row.get("content"))
        if lines.strip():
            system = f"用户长期记忆：\n{lines}\n\n" + system
    if summary and summary.strip():
        system = f"更早对话摘要：\n{summary.strip()}\n\n" + system
    pairs: list[tuple[str, str]] = [("system", system)]
    for role, content in history or []:
        if role == "user":
            pairs.append(("human", content))
        elif role == "assistant":
            pairs.append(("ai", content))
    pairs.append(("human", "{question}"))
    prompt = ChatPromptTemplate.from_messages(pairs)
    chain = prompt | model
    result = chain.invoke({"context": context, "question": question})
    return str(result.content), _usage_of(result)


def _usage_of(message: Any) -> dict[str, int] | None:
    """从 AIMessage 提取 usage_metadata；不可用时返回 None。"""
    meta = getattr(message, "usage_metadata", None)
    if not isinstance(meta, dict):
        return None
    usage = {
        "prompt_tokens": int(meta.get("input_tokens") or 0),
        "completion_tokens": int(meta.get("output_tokens") or 0),
        "total_tokens": int(meta.get("total_tokens") or 0),
    }
    if usage["total_tokens"] <= 0 and usage["prompt_tokens"] <= 0 and usage["completion_tokens"] <= 0:
        return None
    return usage
