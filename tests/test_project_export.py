"""Project-wide data export (`GET /api/projects/{id}/export`).

What is asserted: the archive contains every promised file, provenance
survives (page and chunk index on every chunk), nothing is truncated, the
manifest's hashes are true, originals come back byte-for-byte only when asked
for, generated content keeps its caveats in the file itself, and one project's
export never contains another's data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile

import pytest

from app.store import MetadataStore, metadata_store
from services.patents.sources import FULL_DISCLAIMER

REQUIRED = {
    "README.txt",
    "manifest.json",
    "project.json",
    "chunks.jsonl",
    "chunks.csv",
    "graph.json",
    "tasks.jsonl",
    "patents.json",
}


def _project(client, name="Exported") -> str:
    return client.post("/api/projects", json={"name": name}).json()["id"]


def _upload(client, project_id: str, pdf_path, filename="paper.pdf") -> None:
    with open(pdf_path, "rb") as handle:
        assert client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": (filename, handle, "application/pdf")},
        ).status_code == 201


def _zip(client, project_id: str, **params) -> zipfile.ZipFile:
    response = client.get(f"/api/projects/{project_id}/export", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(response.content))


def _jsonl(archive: zipfile.ZipFile, name: str) -> list[dict]:
    return [json.loads(line) for line in archive.read(name).decode("utf-8").splitlines() if line]


@pytest.fixture()
def populated(client, sample_pdf):
    project_id = _project(client)
    _upload(client, project_id, sample_pdf)
    client.post(
        f"/api/projects/{project_id}/patents",
        json={"title": "Attention apparatus", "text": "Claims\n1. A system comprising self attention."},
    )
    client.post(f"/api/projects/{project_id}/tasks", json={"question": "what is attention?", "flow": "answer"})
    return project_id


class TestZipContents:
    def test_every_promised_file_is_there(self, client, populated):
        archive = _zip(client, populated)
        names = set(archive.namelist())
        assert REQUIRED <= names
        assert "evaluation.json" not in names  # none has been run yet
        assert not any(name.startswith("originals/") for name in names)
        assert "no evaluation has been run" in archive.read("README.txt").decode()
        assert "not included" in archive.read("README.txt").decode()

    def test_chunks_keep_their_provenance_and_none_are_lost(self, client, populated):
        archive = _zip(client, populated)
        chunks = _jsonl(archive, "chunks.jsonl")
        stats = client.get(f"/api/projects/{populated}/stats").json()

        assert len(chunks) == stats["chunks"] > 0
        for chunk in chunks:
            assert chunk["document_name"] == "paper.pdf"
            assert chunk["page"] in (1, 2)
            assert isinstance(chunk["chunk_index"], int)
            assert chunk["text"]

        rows = list(csv.DictReader(io.StringIO(archive.read("chunks.csv").decode("utf-8-sig"))))
        assert [r["chunk_id"] for r in rows] == [c["chunk_id"] for c in chunks]

    def test_graph_tasks_and_patents_match_the_api(self, client, populated):
        archive = _zip(client, populated)

        graph = json.loads(archive.read("graph.json"))
        live = client.get(f"/api/projects/{populated}/graph").json()
        assert {n["id"] for n in graph["nodes"]} == {n["id"] for n in live["nodes"]}

        tasks = _jsonl(archive, "tasks.jsonl")
        live_tasks = client.get(f"/api/projects/{populated}/tasks").json()
        assert {t["id"] for t in tasks} == {t["id"] for t in live_tasks}
        assert all(t["events"] for t in tasks), "each run's events travel with it"

        patents = json.loads(archive.read("patents.json"))
        assert patents["disclaimer"] == FULL_DISCLAIMER
        assert [p["title"] for p in patents["patents"]] == ["Attention apparatus"]

    def test_generated_content_keeps_its_caveats_in_the_file(self, client, populated):
        readme = _zip(client, populated).read("README.txt").decode()
        assert "not_assessed" in readme
        assert "grounded only in the passages cited" in readme
        assert FULL_DISCLAIMER in readme

    def test_the_manifest_hashes_are_true(self, client, populated):
        archive = _zip(client, populated, include_originals="true")
        manifest = json.loads(archive.read("manifest.json"))
        listed = {entry["path"] for entry in manifest["files"]}
        assert listed == set(archive.namelist()) - {"manifest.json"}
        for entry in manifest["files"]:
            payload = archive.read(entry["path"])
            assert len(payload) == entry["bytes"]
            assert hashlib.sha256(payload).hexdigest() == entry["sha256"]


class TestEvaluationInExport:
    def test_the_latest_evaluation_is_included_survives_restart_and_dies_with_the_project(self, client, populated):
        report = client.post(f"/api/projects/{populated}/evaluation/run", json={"k": 5}).json()

        archive = _zip(client, populated)
        exported = json.loads(archive.read("evaluation.json"))
        assert exported["report"]["aggregates"] == report["aggregates"]
        assert "latest evaluation report" in archive.read("README.txt").decode()

        restarted = MetadataStore(database_file=metadata_store.database_file, state_file=metadata_store.state_file)
        restarted.load()
        assert restarted.get_evaluation(populated).report["aggregates"] == report["aggregates"]

        client.delete(f"/api/projects/{populated}")
        assert metadata_store.get_evaluation(populated) is None
        again = MetadataStore(database_file=metadata_store.database_file, state_file=metadata_store.state_file)
        again.load()
        assert again.get_evaluation(populated) is None


class TestOriginals:
    def test_originals_come_back_byte_for_byte_only_when_asked(self, client, sample_pdf):
        project_id = _project(client)
        _upload(client, project_id, sample_pdf, "paper.pdf")
        _upload(client, project_id, sample_pdf, "paper.pdf")  # same name twice

        assert not any(n.startswith("originals/") for n in _zip(client, project_id).namelist())

        archive = _zip(client, project_id, include_originals="true")
        originals = sorted(n for n in archive.namelist() if n.startswith("originals/"))
        assert originals == ["originals/paper (2).pdf", "originals/paper.pdf"]
        for name in originals:
            assert archive.read(name) == sample_pdf.read_bytes()

    def test_uploads_from_before_the_mapping_are_still_included(self, client, sample_pdf):
        from app.config import settings

        project_id = _project(client)
        legacy = settings.upload_dir / project_id
        legacy.mkdir(parents=True)
        (legacy / "1234_old-upload.pdf").write_bytes(b"%PDF-legacy")

        archive = _zip(client, project_id, include_originals="true")
        assert archive.read("originals/unmatched/1234_old-upload.pdf") == b"%PDF-legacy"


class TestJsonFormat:
    def test_one_json_document_with_notes(self, client, populated):
        response = client.get(f"/api/projects/{populated}/export", params={"format": "json"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["format_version"] == 1
        assert {"project", "documents", "chunks", "graph", "tasks", "patents", "notes"} <= set(body)
        assert body["notes"]["patents"] == FULL_DISCLAIMER

    def test_originals_are_refused_in_json(self, client, populated):
        response = client.get(
            f"/api/projects/{populated}/export", params={"format": "json", "include_originals": "true"}
        )
        assert response.status_code == 400

    def test_unknown_format_and_project(self, client, populated):
        assert client.get(f"/api/projects/{populated}/export", params={"format": "xml"}).status_code == 422
        assert client.get("/api/projects/missing/export").status_code == 404


class TestIsolationAndLimits:
    def test_another_projects_data_never_appears(self, client, sample_pdf):
        mine = _project(client, "Mine")
        theirs = _project(client, "Theirs")
        _upload(client, theirs, sample_pdf, "theirs.pdf")
        client.post(f"/api/projects/{theirs}/patents", json={"title": "Their patent", "text": "t"})

        archive = _zip(client, mine, include_originals="true")
        assert _jsonl(archive, "chunks.jsonl") == []
        assert json.loads(archive.read("patents.json"))["patents"] == []
        assert not any(n.startswith("originals/") for n in archive.namelist())

    def test_large_indexes_are_not_truncated(self, client):
        """The store's default scan stops at 2,000 chunks; an export must not."""
        from app.dependencies import get_chroma_store

        project_id = _project(client, "Big")
        count = 2_050
        get_chroma_store().add_chunks(
            ids=[f"big-{i}" for i in range(count)],
            documents=[f"passage number {i}" for i in range(count)],
            metadatas=[
                {"project_id": project_id, "document_id": "d", "document_name": "big.pdf", "page": 1, "chunk_index": i}
                for i in range(count)
            ],
        )
        assert len(_jsonl(_zip(client, project_id), "chunks.jsonl")) == count

    def test_exports_draw_on_the_expensive_budget(self):
        from starlette.requests import Request

        from app.middleware import RateLimitMiddleware

        limiter = RateLimitMiddleware(app=None, read_limit=100, write_limit=3)
        request = Request({"type": "http", "method": "GET", "path": "/api/projects/p/export", "headers": []})
        assert limiter._bucket(request) == ("expensive", 3)

    def test_another_user_cannot_export_your_project(self, client, monkeypatch):
        """With auth on, the export is guarded by the same ownership check."""
        import time

        import jwt
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from app import auth
        from app.config import settings

        private = Ed25519PrivateKey.generate()
        public = json.loads(jwt.algorithms.OKPAlgorithm.to_jwk(private.public_key()))
        public.update({"kid": "k", "alg": "EdDSA"})

        async def fake_fetch(url):
            return {"keys": [public]}

        monkeypatch.setattr(auth, "fetch_jwks", fake_fetch)
        monkeypatch.setattr(settings, "auth_jwks_url", "https://site/api/auth/jwks")
        auth.jwks_cache.clear()

        def headers(sub):
            token = jwt.encode({"sub": sub, "exp": int(time.time()) + 300}, private, algorithm="EdDSA", headers={"kid": "k"})
            return {"Authorization": f"Bearer {token}"}

        project_id = client.post("/api/projects", json={"name": "A"}, headers=headers("alice")).json()["id"]
        assert client.get(f"/api/projects/{project_id}/export", headers=headers("bob")).status_code == 404
        assert client.get(f"/api/projects/{project_id}/export", headers=headers("alice")).status_code == 200
        auth.jwks_cache.clear()
