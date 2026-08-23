import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session_scope
from app.kb import DEFAULT_KB_NAME
from app.main import create_app, reset_app_state
from app.models import Document, KnowledgeBase
from app.storage import files_dir, parsed_dir


def _client() -> TestClient:
    reset_app_state()
    get_settings(load_file=True)
    return TestClient(create_app(load_file=True, ensure_default=True))


def test_list_contains_default_and_created():
    with _client() as client:
        n1, n2 = f"Java-{uuid.uuid4().hex[:8]}", f"AI-{uuid.uuid4().hex[:8]}"
        r1 = client.post("/api/knowledge-bases", json={"name": n1})
        r2 = client.post("/api/knowledge-bases", json={"name": n2})
        assert r1.status_code == 201
        assert r2.status_code == 201
        names = {row["name"] for row in client.get("/api/knowledge-bases").json()}
        assert DEFAULT_KB_NAME in names
        assert n1 in names
        assert n2 in names


def test_rename_and_duplicate_name():
    with _client() as client:
        created = client.post("/api/knowledge-bases", json={"name": f"临时-{uuid.uuid4().hex[:8]}"}).json()
        kb_id = created["id"]
        new_name = f"已改-{uuid.uuid4().hex[:8]}"
        renamed = client.put(f"/api/knowledge-bases/{kb_id}", json={"name": new_name})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == new_name
        taken = f"占用-{uuid.uuid4().hex[:8]}"
        client.post("/api/knowledge-bases", json={"name": taken})
        conflict = client.post("/api/knowledge-bases", json={"name": taken})
        assert conflict.status_code == 409


def test_delete_kb_removes_docs_and_files():
    with _client() as client:
        created = client.post("/api/knowledge-bases", json={"name": f"待删-{uuid.uuid4().hex[:8]}"}).json()
        kb_id = uuid.UUID(created["id"])
        doc_id = uuid.uuid4()
        data_dir = get_settings().data_dir
        year_dir = files_dir() / "2026"
        year_dir.mkdir(parents=True, exist_ok=True)
        file_path = year_dir / f"{doc_id}.txt"
        file_path.write_text("hello", encoding="utf-8")
        parsed = parsed_dir(doc_id)
        parsed.mkdir(parents=True, exist_ok=True)
        (parsed / "document.md").write_text("x", encoding="utf-8")
        session = session_scope()
        try:
            session.add(
                Document(
                    id=doc_id,
                    knowledge_base_id=kb_id,
                    filename="hello.txt",
                    ext=".txt",
                    kind="txt",
                    checksum=str(doc_id).replace("-", ""),
                    status="ready",
                    byte_size=5,
                )
            )
            session.commit()
        finally:
            session.close()
        res = client.delete(f"/api/knowledge-bases/{kb_id}")
        assert res.status_code == 204
        assert client.get(f"/api/knowledge-bases/{kb_id}").status_code == 404
        assert not file_path.exists()
        assert not parsed.exists()
        session = session_scope()
        try:
            assert session.get(Document, doc_id) is None
            assert session.get(KnowledgeBase, kb_id) is None
        finally:
            session.close()
    reset_app_state()
