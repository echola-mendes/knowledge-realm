"""业务决策审计埋点（docs/Trace.md V1.1）。

每轮 assistant 回复一条 DecisionRun + 线性 DecisionSpan。
run 行经主流程会话的 savepoint 落库（与该轮消息同事务提交，FK 天然满足）；
spans 与终态更新用独立会话写。公开方法吞掉一切异常——审计故障绝不影响主回答。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import DecisionRun, DecisionSpan

logger = logging.getLogger(__name__)

NODE_TYPES = ("route", "retrieve", "generate", "tool_call", "tool_result")
RUN_STATUSES = ("running", "success", "failed")


class DecisionRecorder:
    """一次性对象：一轮回答一个实例，start → add_span* → finish。"""

    def __init__(
        self,
        *,
        session_factory=session_scope,
        session: Session | None = None,
    ):
        self._session_factory = session_factory
        self._session = session
        self._run_id: uuid.UUID | None = None
        self._spans: list[dict[str, Any]] = []
        self._finished = False

    @property
    def run_id(self) -> uuid.UUID | None:
        return self._run_id

    def start_run(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        mode: str,
        query: str,
    ) -> uuid.UUID | None:
        run_id = uuid.uuid4()
        try:
            if self._session is not None:
                # savepoint：审计行不污染主事务的异常处理；随主事务一起提交
                with self._session.begin_nested():
                    self._session.add(
                        DecisionRun(
                            id=run_id,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            mode=mode,
                            query=query,
                            status="running",
                        )
                    )
            else:
                with self._session_factory() as session:
                    session.add(
                        DecisionRun(
                            id=run_id,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            mode=mode,
                            query=query,
                            status="running",
                        )
                    )
                    session.commit()
            self._run_id = run_id
        except Exception:
            logger.warning("decision audit: start_run failed", exc_info=True)
        return self._run_id

    def add_span(
        self,
        node_type: str,
        *,
        decision: dict[str, Any] | None = None,
        rationale: str | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> uuid.UUID | None:
        try:
            span_id = uuid.uuid4()
            if node_type not in NODE_TYPES:
                node_type = "generate"
            self._spans.append(
                {
                    "id": span_id,
                    "seq": len(self._spans) + 1,
                    "node_type": node_type,
                    "decision": decision,
                    "rationale": rationale,
                    "evidence_refs": evidence_refs,
                    "metrics": metrics,
                }
            )
            return span_id
        except Exception:
            logger.warning("decision audit: add_span failed", exc_info=True)
            return None

    def finish_run(self, status: str, *, message_id: uuid.UUID | None = None) -> None:
        if self._finished:
            return
        self._finished = True
        if status not in RUN_STATUSES:
            status = "failed"
        run_id = self._run_id
        if run_id is None:
            return
        try:
            with self._session_factory() as session:
                run = session.get(DecisionRun, run_id)
                if run is None:
                    return
                run.status = status
                for row in self._spans:
                    session.add(DecisionSpan(run_id=run_id, **row))
                session.commit()
            if message_id is not None:
                # 二次提交：message 绑定失败时不回滚状态与 spans
                with self._session_factory() as session:
                    run = session.get(DecisionRun, run_id)
                    if run is not None:
                        run.message_id = message_id
                        session.commit()
        except Exception:
            logger.warning("decision audit: finish_run failed", exc_info=True)


def recorder_from_config(config: dict | None) -> DecisionRecorder | None:
    """LangGraph 节点从 RunnableConfig.configurable 取埋点实例。"""
    if not config:
        return None
    recorder = (config.get("configurable") or {}).get("decision_recorder")
    return recorder if isinstance(recorder, DecisionRecorder) else None
