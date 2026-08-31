from __future__ import annotations

import json
import math
from typing import Any, Callable

from app.config import get_settings
from app.index import embed_texts, embedding_keys_ready
from app.llm import llm_keys_ready

RELEVANCE_QUESTION_COUNT = 3
CORRECTNESS_FACTUAL_WEIGHT = 0.75
CORRECTNESS_SIM_WEIGHT = 0.25

_EXTRACT_STATEMENTS_PROMPT = (
    "将下列回答拆成独立事实陈述。只输出 JSON："
    '{"statements":["陈述1","陈述2"]}。'
    "无事实则 statements 为空数组。禁止输出 JSON 以外内容。"
)

_SUPPORT_PROMPT = (
    "判断每条陈述是否能被资料支撑（直接写出或可由资料合理推出）。"
    "只输出 JSON："
    '{"supported":[true,false,...]}，长度必须与陈述条数一致。'
    "禁止输出 JSON 以外内容。"
)

_REVERSE_QUESTIONS_PROMPT = (
    "根据下列回答，反向生成恰好 {n} 个可能提出的问题。"
    "只输出 JSON："
    '{{"questions":["问题1","问题2"]}}。'
    "问题应能由该回答解答。禁止输出 JSON 以外内容。"
)

_FACTUAL_PROMPT = (
    "对照标准答案，评估实际回答的事实覆盖。"
    "TP=两边都支持的事实数；FP=实际回答有但标准答案不支持的事实数；"
    "FN=标准答案有但实际回答未覆盖的事实数。"
    "只输出 JSON："
    '{"tp":0,"fp":0,"fn":0}。禁止输出 JSON 以外内容。'
)


def keys_ready() -> bool:
    return llm_keys_ready() and embedding_keys_ready()


def _parse_json_object(raw: str) -> dict[str, Any]:
    start, end = raw.find("{"), raw.rfind("}")
    text = raw[start : end + 1] if start >= 0 and end >= start else raw
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("rag_eval 输出不是合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("rag_eval 输出不是 JSON 对象")
    return parsed


def _chat_json(system: str, human: str) -> dict[str, Any]:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", "{human}")])
    raw = str((prompt | model).invoke({"human": human}).content)
    return _parse_json_object(raw)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def extract_statements(answer: str, *, chat_json: Callable[[str, str], dict[str, Any]] = _chat_json) -> list[str]:
    data = chat_json(_EXTRACT_STATEMENTS_PROMPT, f"回答：\n{answer}")
    raw = data.get("statements")
    if not isinstance(raw, list):
        raise ValueError("rag_eval 缺少 statements")
    return [str(s).strip() for s in raw if str(s).strip()]


def statements_supported(
    statements: list[str],
    contexts: list[str],
    *,
    chat_json: Callable[[str, str], dict[str, Any]] = _chat_json,
) -> list[bool]:
    if not statements:
        return []
    blocks = "\n\n".join(f"[资料{i + 1}]\n{c}" for i, c in enumerate(contexts) if c.strip()) or "（无资料）"
    listed = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(statements))
    data = chat_json(_SUPPORT_PROMPT, f"资料：\n{blocks}\n\n陈述：\n{listed}")
    raw = data.get("supported")
    if not isinstance(raw, list) or len(raw) != len(statements):
        raise ValueError("rag_eval supported 长度不匹配")
    return [bool(x) for x in raw]


def faithfulness_score(
    answer: str,
    contexts: list[str],
    *,
    chat_json: Callable[[str, str], dict[str, Any]] = _chat_json,
) -> float | None:
    if not answer.strip():
        return None
    if not any(c.strip() for c in contexts):
        return None
    statements = extract_statements(answer, chat_json=chat_json)
    if not statements:
        return 1.0
    flags = statements_supported(statements, contexts, chat_json=chat_json)
    return _clamp01(sum(1 for x in flags if x) / len(flags))


def generate_questions_from_answer(
    answer: str,
    n: int = RELEVANCE_QUESTION_COUNT,
    *,
    chat_json: Callable[[str, str], dict[str, Any]] = _chat_json,
) -> list[str]:
    system = _REVERSE_QUESTIONS_PROMPT.format(n=n)
    data = chat_json(system, f"回答：\n{answer}")
    raw = data.get("questions")
    if not isinstance(raw, list):
        raise ValueError("rag_eval 缺少 questions")
    questions = [str(q).strip() for q in raw if str(q).strip()]
    if not questions:
        raise ValueError("rag_eval questions 为空")
    return questions[:n]


def answer_relevance_score(
    query: str,
    answer: str,
    *,
    chat_json: Callable[[str, str], dict[str, Any]] = _chat_json,
    embed: Callable[[list[str]], list[list[float]]] = embed_texts,
) -> float | None:
    if not query.strip() or not answer.strip():
        return None
    questions = generate_questions_from_answer(answer, chat_json=chat_json)
    vectors = embed([query.strip(), *questions])
    if len(vectors) != 1 + len(questions):
        raise ValueError("rag_eval embedding 数量不匹配")
    q_vec = vectors[0]
    sims = [_cosine(q_vec, v) for v in vectors[1:]]
    return _clamp01(sum(sims) / len(sims))


def semantic_similarity_score(
    answer: str,
    gt_answer: str,
    *,
    embed: Callable[[list[str]], list[list[float]]] = embed_texts,
) -> float | None:
    if not answer.strip() or not gt_answer.strip():
        return None
    vectors = embed([answer.strip(), gt_answer.strip()])
    if len(vectors) != 2:
        raise ValueError("rag_eval embedding 数量不匹配")
    return _cosine(vectors[0], vectors[1])


def _factual_f1(
    answer: str,
    gt_answer: str,
    *,
    chat_json: Callable[[str, str], dict[str, Any]] = _chat_json,
) -> float:
    data = chat_json(
        _FACTUAL_PROMPT,
        f"标准答案：\n{gt_answer}\n\n实际回答：\n{answer}",
    )
    try:
        tp = max(0, int(data.get("tp")))
        fp = max(0, int(data.get("fp")))
        fn = max(0, int(data.get("fn")))
    except (TypeError, ValueError) as exc:
        raise ValueError("rag_eval 缺少合法的 tp/fp/fn") from exc
    denom = 2 * tp + fp + fn
    if denom == 0:
        return 1.0
    return _clamp01((2 * tp) / denom)


def answer_correctness_score(
    answer: str,
    gt_answer: str,
    *,
    chat_json: Callable[[str, str], dict[str, Any]] = _chat_json,
    embed: Callable[[list[str]], list[list[float]]] = embed_texts,
) -> float | None:
    if not answer.strip() or not gt_answer.strip():
        return None
    factual = _factual_f1(answer, gt_answer, chat_json=chat_json)
    sim = semantic_similarity_score(answer, gt_answer, embed=embed)
    if sim is None:
        return None
    return _clamp01(CORRECTNESS_FACTUAL_WEIGHT * factual + CORRECTNESS_SIM_WEIGHT * sim)


def compute_rag_metrics(
    query: str,
    answer: str,
    contexts: list[str],
    gt_answer: str | None = None,
    *,
    chat_json: Callable[[str, str], dict[str, Any]] = _chat_json,
    embed: Callable[[list[str]], list[list[float]]] = embed_texts,
) -> dict[str, float | None]:
    gt = (gt_answer or "").strip() or None
    return {
        "faithfulness": faithfulness_score(answer, contexts, chat_json=chat_json),
        "answer_relevance": answer_relevance_score(query, answer, chat_json=chat_json, embed=embed),
        "answer_correctness": (
            answer_correctness_score(answer, gt, chat_json=chat_json, embed=embed) if gt else None
        ),
        "semantic_similarity": semantic_similarity_score(answer, gt, embed=embed) if gt else None,
    }
