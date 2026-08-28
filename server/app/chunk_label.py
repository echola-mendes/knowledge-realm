"""Global chunk labels: Chunk_1, Chunk_2, …"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

SEQ = "chunk_label_seq"


def allocate_chunk_labels(session: Session, count: int) -> list[str]:
    if count <= 0:
        return []
    rows = session.execute(
        text(f"SELECT nextval('{SEQ}') AS n FROM generate_series(1, :count)"),
        {"count": count},
    ).all()
    return [f"Chunk_{int(row.n)}" for row in rows]
