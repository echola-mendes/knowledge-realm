import uuid

from sqlalchemy import select

from app.audit import DecisionRecorder
from app.db import session_scope
from app.models import Conversation, DecisionRun, DecisionSpan, KnowledgeBase, Message, User


def _make_user_convo() -> tuple[uuid.UUID, uuid.UUID]:
    with session_scope() as session:
        user = User(username=f"rec-{uuid.uuid4().hex[:8]}", password_hash="x")
        session.add(user)
        session.flush()
        kb = KnowledgeBase(user_id=user.id, name="rec-kb", is_default=True)
        session.add(kb)
        session.flush()
        convo = Conversation(user_id=user.id, knowledge_base_id=kb.id, title="rec")
        session.add(convo)
        session.commit()
        return user.id, convo.id


def test_recorder_persists_run_and_ordered_spans():
    user_id, convo_id = _make_user_convo()
    rec = DecisionRecorder()
    run_id = rec.start_run(user_id=user_id, conversation_id=convo_id, mode="chat", query="问题")
    assert run_id is not None
    rec.add_span("retrieve", decision={"tool": "search_knowledge", "query": "问题"}, evidence_refs=[{"type": "chunk", "id": "c1", "score": 0.9}])
    rec.add_span("generate", decision={"summary": "答"}, metrics={"elapsed_ms": 12})
    with session_scope() as session:
        msg = Message(conversation_id=convo_id, role="assistant", content="答")
        session.add(msg)
        session.commit()
        msg_id = msg.id
    rec.finish_run("success", message_id=msg_id)

    with session_scope() as session:
        run = session.get(DecisionRun, run_id)
        assert run is not None
        assert run.status == "success"
        assert run.message_id == msg_id
        assert run.mode == "chat"
        spans = session.scalars(
            select(DecisionSpan).where(DecisionSpan.run_id == run_id).order_by(DecisionSpan.seq)
        ).all()
        assert [s.seq for s in spans] == [1, 2]
        assert [s.node_type for s in spans] == ["retrieve", "generate"]
        assert spans[0].evidence_refs[0]["id"] == "c1"
        assert spans[1].metrics == {"elapsed_ms": 12}


def test_recorder_start_failure_returns_none_and_finish_is_noop():
    user_id, convo_id = _make_user_convo()

    class BrokenFactory:
        def __call__(self):
            raise RuntimeError("db down")

    rec = DecisionRecorder(session_factory=BrokenFactory)
    assert rec.start_run(user_id=user_id, conversation_id=convo_id, mode="chat", query="q") is None
    rec.add_span("generate", decision={"summary": "x"})
    rec.finish_run("success")  # run 未落库 → 静默 no-op
    rec.finish_run("success")  # 重复 finish 不抛

    with session_scope() as session:
        rows = session.scalars(select(DecisionRun).where(DecisionRun.user_id == user_id)).all()
        assert rows == []


def test_recorder_finish_with_bad_message_id_does_not_raise():
    user_id, convo_id = _make_user_convo()
    rec = DecisionRecorder()
    run_id = rec.start_run(user_id=user_id, conversation_id=convo_id, mode="knowledge", query="q")
    rec.add_span("route", decision={"action": "search"}, rationale="需要检索")
    # message_id 不存在 → FK 冲突 → 吞异常；两阶段设计下状态与 spans 仍落库
    rec.finish_run("success", message_id=uuid.uuid4())

    with session_scope() as session:
        run = session.get(DecisionRun, run_id)
        assert run is not None
        assert run.status == "success"
        assert run.message_id is None
