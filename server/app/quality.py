from __future__ import annotations

import json

from app.config import get_settings

JUDGE_SYSTEM_PROMPT = (
    "你是 RAG 回答质量评审。根据给定资料评估回答，只输出 JSON："
    '{"faithfulness":1-5整数,"relevance":1-5整数,"completeness":1-5整数,'
    '"issues":["问题1","问题2"]}。'
    "faithfulness=回答是否忠于资料（编造/与资料矛盾扣分）；"
    "relevance=回答是否切题；"
    "completeness=资料中与问题相关的信息是否被充分使用。"
    "资料为空时按普通对话标准评 relevance 与 completeness，faithfulness 满分。"
    "issues 用中文短语列出扣分原因，无问题则空数组。禁止输出 JSON 以外内容。"
)


def judge_keys_ready() -> bool:
    return bool(get_settings().llm_api_key.strip())


def judge_answer(query: str, answer: str, contexts: list[str]) -> dict[str, object]:
    """LLM-as-judge：返回 {faithfulness, relevance, completeness, issues}。"""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    blocks = "\n\n".join(f"[资料{i + 1}]\n{c}" for i, c in enumerate(contexts) if c.strip()) or "（无资料）"
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", JUDGE_SYSTEM_PROMPT),
            ("human", "问题：{query}\n\n回答：{answer}\n\n{blocks}"),
        ]
    )
    raw = str((prompt | model).invoke({"query": query, "answer": answer, "blocks": blocks}).content)
    return parse_judge_json(raw)


def parse_judge_json(raw: str) -> dict[str, object]:
    start, end = raw.find("{"), raw.rfind("}")
    text = raw[start : end + 1] if start >= 0 and end >= start else raw
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("judge 输出不是合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("judge 输出不是 JSON 对象")

    def score(key: str) -> int:
        try:
            return max(1, min(5, int(parsed.get(key))))
        except (TypeError, ValueError):
            raise ValueError(f"judge 缺少合法的 {key}") from None

    issues_raw = parsed.get("issues")
    issues = [str(i) for i in issues_raw if str(i).strip()] if isinstance(issues_raw, list) else []
    return {
        "faithfulness": score("faithfulness"),
        "relevance": score("relevance"),
        "completeness": score("completeness"),
        "issues": issues,
    }
