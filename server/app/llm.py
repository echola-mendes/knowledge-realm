from __future__ import annotations

from app.config import get_settings

CHAT_CALLS = 0
NO_HIT_TEXT = "知识库中没有相关内容。"
SYSTEM_PROMPT = "只根据提供的资料回答。禁止编造出处。资料不足时明确说不知道。"


def llm_keys_ready() -> bool:
    return bool(get_settings().llm_api_key.strip())


def chat(question: str, context: str) -> str:
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
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT + "\n\n资料：\n{context}"),
            ("human", "{question}"),
        ]
    )
    chain = prompt | model
    result = chain.invoke({"context": context, "question": question})
    return str(result.content)
