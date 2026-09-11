"""Step 3: citations dedup by (document_id, chunk_id) + score top-N."""
from __future__ import annotations

import inspect
import json
import uuid

from langchain_core.messages import AIMessage, ToolMessage

from app.agent import graph as graph_mod
from app.agent.graph import MAX_CITATIONS, _merge_citations, build_graph, initial_state, reset_graph
from app.rag.search import SearchHit
from app.schemas import CitationOut


def _cite(doc: str, chunk: str, score: float | None = None, **extra) -> dict:
    item = {
        "document_id": doc,
        "chunk_id": chunk,
        "document_name": extra.pop("document_name", "n.md"),
        "content": extra.pop("content", "c"),
    }
    if score is not None:
        item["score"] = score
    item.update(extra)
    return item


def _config(thread: str, **extra):
    cfg = {"thread_id": thread, "session": object(), "user_id": uuid.uuid4(), **extra}
    return {"configurable": cfg}


def test_same_key_keeps_higher_score():
    low = _cite("d1", "c1", 0.4, content="low")
    high = _cite("d1", "c1", 0.9, content="high")
    out = _merge_citations([low, high])
    assert len(out) == 1
    assert out[0]["score"] == 0.9
    assert out[0]["content"] == "high"
    out = _merge_citations([high, low])
    assert len(out) == 1
    assert out[0]["score"] == 0.9
    assert out[0]["content"] == "high"


def test_missing_score_keeps_first_until_scored_arrives():
    first = _cite("d1", "c1", content="first")
    second = _cite("d1", "c1", content="second")
    assert _merge_citations([first, second])[0]["content"] == "first"
    scored = _cite("d1", "c1", 0.3, content="scored")
    assert _merge_citations([first, scored])[0]["content"] == "scored"
    assert _merge_citations([scored, first])[0]["content"] == "scored"


def test_early_high_score_survives_later_low_score_flood():
    early = [_cite("d", f"h{i}", 0.99 - i * 0.001) for i in range(5)]
    flood = [_cite("x", f"l{i}", 0.1) for i in range(50)]
    out = _merge_citations(early + flood)
    assert len(out) == MAX_CITATIONS
    kept = {c["chunk_id"] for c in out}
    assert {c["chunk_id"] for c in early} <= kept
    assert out[0]["chunk_id"] == "h0"


def test_unscored_keeps_first_seen_and_caps_at_max():
    items = [_cite("d", f"c{i}") for i in range(30)]
    out = _merge_citations(items)
    assert len(out) == MAX_CITATIONS
    assert [c["chunk_id"] for c in out] == [f"c{i}" for i in range(MAX_CITATIONS)]


def test_unscored_fill_remaining_slots_after_scored():
    unscored = [_cite("u", f"{i}") for i in range(30)]
    scored = [_cite("s", "top", 0.5)]
    out = _merge_citations(unscored[:5] + scored + unscored[5:])
    assert len(out) == MAX_CITATIONS
    assert out[0]["chunk_id"] == "top"
    assert [c["chunk_id"] for c in out[1:]] == [str(i) for i in range(MAX_CITATIONS - 1)]


def test_merged_citation_validates_as_citation_out():
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    out = _merge_citations(
        [
            {
                "document_id": doc_id,
                "document_name": "a.md",
                "chunk_id": chunk_id,
                "page_start": 1,
                "page_end": 1,
                "content": "x",
                "score": 0.9,
            }
        ]
    )
    parsed = CitationOut.model_validate(out[0])
    assert parsed.document_id == doc_id
    assert parsed.chunk_id == chunk_id
    assert parsed.score == 0.9


def test_merge_used_on_aggregate_and_node_tools_paths():
    src = inspect.getsource(graph_mod)
    assert "_merge_citations" in inspect.getsource(graph_mod._aggregate_from_tool_messages)
    assert "_merge_citations" in inspect.getsource(graph_mod.node_tools)
    assert "citations[-MAX_CITATIONS:]" not in src


def test_early_high_score_survives_multi_round_tools(monkeypatch):
    reset_graph()
    high_chunk = uuid.uuid4()
    high_doc = uuid.uuid4()

    def fake_search(session, query, **kwargs):
        if query == "high":
            return [
                SearchHit(
                    document_id=high_doc,
                    document_name="keep.md",
                    chunk_id=high_chunk,
                    content="keep-me",
                    score=0.99,
                    page=1,
                    heading=None,
                    kind="note",
                )
            ]
        return [
            SearchHit(
                document_id=uuid.uuid4(),
                document_name="flood.md",
                chunk_id=uuid.uuid4(),
                content=f"low-{i}",
                score=0.01,
                page=1,
                heading=None,
                kind="note",
            )
            for i in range(25)
        ]

    monkeypatch.setattr("app.agent.tools.knowledge.search_chunks", fake_search)
    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "search_knowledge", "args": {"query": "high"}, "id": "c1"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "search_knowledge", "args": {"query": "flood"}, "id": "c2"}],
            ),
            AIMessage(content="终答"),
        ]
    )

    class FakeRunnable:
        def invoke(self, messages, config=None):
            return next(responses)

        def stream(self, messages, config=None):
            yield next(responses)

    class FakeModel:
        def bind_tools(self, tools, **kwargs):
            return FakeRunnable()

        def invoke(self, messages, config=None):
            return next(responses)

    monkeypatch.setattr(graph_mod, "_chat_model", lambda: FakeModel())
    state = initial_state("保质")
    state["max_loops"] = 5
    out = build_graph().invoke(state, config=_config(f"cite-{uuid.uuid4()}"))
    cites = out.get("citations") or []
    assert len(cites) <= MAX_CITATIONS
    assert any(str(c.get("chunk_id")) == str(high_chunk) for c in cites)
    assert out["answer"] == "终答"
    payload = json.dumps(cites, default=str)
    assert "keep-me" in payload
