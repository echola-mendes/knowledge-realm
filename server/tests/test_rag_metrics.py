from __future__ import annotations

from app.config import get_settings
from app.main import reset_app_state
from app.rag_eval import (
    answer_relevance_score,
    compute_rag_metrics,
    faithfulness_score,
)
from tests.http_client import api_client


def _client():
    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def _unit(i: int, dim: int = 8) -> list[float]:
    v = [0.0] * dim
    v[i % dim] = 1.0
    return v


def test_compute_rag_metrics_null_when_missing_inputs():
    out = compute_rag_metrics(
        "退款多久",
        "",
        [],
        gt_answer=None,
        chat_json=lambda *_: {},
        embed=lambda texts: [_unit(0) for _ in texts],
    )
    assert out["faithfulness"] is None
    assert out["answer_relevance"] is None
    assert out["answer_correctness"] is None
    assert out["semantic_similarity"] is None

    out2 = compute_rag_metrics(
        "退款多久",
        "七个工作日",
        ["退款周期为七个工作日"],
        gt_answer=None,
        chat_json=lambda system, human: (
            {"statements": ["退款周期为七个工作日"]}
            if "拆成独立事实" in system
            else {"supported": [True]}
            if "是否能被资料支撑" in system
            else {"questions": ["退款要多久？", "多久能退款？", "退款周期？"]}
        ),
        embed=lambda texts: [_unit(0) for _ in texts],
    )
    assert out2["faithfulness"] == 1.0
    assert out2["answer_relevance"] == 1.0
    assert out2["answer_correctness"] is None
    assert out2["semantic_similarity"] is None


def test_faithfulness_ratio():
    calls: list[str] = []

    def chat_json(system: str, human: str):
        calls.append(system)
        if "拆成独立事实" in system:
            return {"statements": ["A", "B"]}
        if "是否能被资料支撑" in system:
            return {"supported": [True, False]}
        raise AssertionError(system)

    score = faithfulness_score("答", ["资料"], chat_json=chat_json)
    assert score == 0.5
    assert any("拆成独立事实" in s for s in calls)
    assert any("是否能被资料支撑" in s for s in calls)


def test_answer_relevance_generates_questions_then_embeds():
    seen: dict[str, object] = {"embed_inputs": None}

    def chat_json(system: str, human: str):
        assert "反向生成" in system
        assert "回答：" in human
        return {"questions": ["问题甲", "问题乙", "问题丙"]}

    def embed(texts: list[str]):
        seen["embed_inputs"] = texts
        # query 与第 1 个生成问题同向，其余正交 → 均值 1/3
        return [_unit(0), _unit(0), _unit(1), _unit(2)]

    score = answer_relevance_score("原始问题", "某个回答", chat_json=chat_json, embed=embed)
    assert seen["embed_inputs"] == ["原始问题", "问题甲", "问题乙", "问题丙"]
    assert abs(score - (1.0 / 3.0)) < 1e-9



def test_answer_correctness_and_semantic_similarity():
    calls: list[tuple[str, str]] = []

    def chat_json(system: str, human: str):
        calls.append((system, human))
        if "事实覆盖" in system or "TP=两边都支持" in system:
            return {"tp": 1, "fp": 0, "fn": 1}
        if "反向生成" in system:
            return {"questions": ["退款周期多久？"]}
        raise AssertionError(f"未预期的调用: {system[:20]}")

    def embed(texts: list[str]):
        # 保证 actual answer 与 gt answer 用同一向量 → cosine = 1.0
        return [_unit(0), _unit(0)]

    out = compute_rag_metrics(
        "退款周期",
        "7 天",
        [],
        gt_answer="七个工作日",
        chat_json=chat_json,
        embed=embed,
    )
    # factual_f1 = 2*tp / (2*tp + fp + fn) = 2/3
    # correctness = 0.75 * 2/3 + 0.25 * 1.0 = 0.75
    assert out["semantic_similarity"] == 1.0
    assert abs(out["answer_correctness"] - 0.75) < 1e-9
    assert any("事实覆盖" in s or "TP=两边都支持" in s for s, _ in calls)

def test_rag_metrics_api_with_mocks(monkeypatch):
    import app.routers.retrieval_debug as rd

    monkeypatch.setattr(rd, "rag_eval_keys_ready", lambda: True)
    monkeypatch.setattr(
        rd,
        "compute_rag_metrics",
        lambda query, answer, contexts, gt_answer=None: {
            "faithfulness": 0.5,
            "answer_relevance": 0.8,
            "answer_correctness": 0.7 if gt_answer else None,
            "semantic_similarity": 0.9 if gt_answer else None,
        },
    )
    with _client() as client:
        res = client.post(
            "/api/retrieval-debug/rag-metrics",
            json={
                "query": "退款周期",
                "answer": "7 天",
                "contexts": ["退款 7 个工作日"],
                "gt_answer": "七个工作日",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
    assert body["faithfulness"] == 0.5
    assert body["answer_relevance"] == 0.8
    assert body["answer_correctness"] == 0.7
    assert body["semantic_similarity"] == 0.9
