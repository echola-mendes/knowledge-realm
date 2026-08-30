from __future__ import annotations

import app.quality as quality_mod
from app.schemas import AnswerQualityOut
from tests.http_client import api_client


def _client():
    from app.main import reset_app_state
    from app.config import get_settings

    reset_app_state()
    get_settings(load_file=True)
    return api_client()


def test_answer_quality_scores(monkeypatch):
    import app.routers.retrieval_debug as rd

    monkeypatch.setattr(rd, "judge_keys_ready", lambda: True)
    monkeypatch.setattr(
        rd,
        "judge_answer",
        lambda query, answer, contexts: {
            "faithfulness": 4,
            "relevance": 5,
            "completeness": 3,
            "issues": ["遗漏了资料2中的例外条款"],
        },
    )
    with _client() as client:
        res = client.post(
            "/api/retrieval-debug/answer-quality",
            json={"query": "退款周期", "answer": "7 个工作日", "contexts": ["退款周期为 7 个工作日"]},
        )
        assert res.status_code == 200
        body = res.json()
    assert body["faithfulness"] == 4
    assert body["relevance"] == 5
    assert body["completeness"] == 3
    assert body["issues"] == ["遗漏了资料2中的例外条款"]


def test_answer_quality_requires_llm(monkeypatch):
    import app.routers.retrieval_debug as rd

    monkeypatch.setattr(rd, "judge_keys_ready", lambda: False)
    with _client() as client:
        res = client.post(
            "/api/retrieval-debug/answer-quality",
            json={"query": "q", "answer": "a", "contexts": []},
        )
    assert res.status_code == 503


def test_parse_judge_json_clamps_and_tolerates():
    raw = '{"faithfulness": 9, "relevance": "4", "completeness": 0, "issues": ["a", "", 3]}'
    out = quality_mod.parse_judge_json(raw)
    assert out["faithfulness"] == 5
    assert out["relevance"] == 4
    assert out["completeness"] == 1
    assert out["issues"] == ["a", "3"]


def test_parse_judge_json_rejects_garbage():
    import pytest

    with pytest.raises(ValueError):
        quality_mod.parse_judge_json("不是JSON")
    with pytest.raises(ValueError):
        quality_mod.parse_judge_json('{"faithfulness": "x"}')
    assert AnswerQualityOut(**quality_mod.parse_judge_json('{"faithfulness":3,"relevance":3,"completeness":3}'))
