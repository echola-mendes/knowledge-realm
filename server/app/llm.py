from __future__ import annotations

from app.config import get_settings

CHAT_CALLS = 0
SYSTEM_PROMPT = (
    "若资料非空：只根据资料回答，禁止编造出处。"
    "若资料为空：进行正常对话，不要说知识库没有相关内容。"
)


def llm_keys_ready() -> bool:
    return bool(get_settings().llm_api_key.strip())


def chat(
    question: str,
    context: str,
    history: list[tuple[str, str]] | None = None,
    *,
    summary: str | None = None,
    ltm: list[dict[str, str]] | None = None,
) -> str:
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
    return str(result.content)
