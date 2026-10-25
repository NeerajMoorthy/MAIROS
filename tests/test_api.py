"""End-to-end API tests via the FastAPI TestClient."""

from __future__ import annotations

import io

import fitz  # PyMuPDF


def _pdf_bytes(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


TRANSFORMER_PAGE = (
    "The transformer architecture uses multi-head self-attention. "
    "Each attention head learns different relationships between tokens. "
    "Positional encodings are added to preserve sequence order."
)
RAG_PAGE = (
    "Retrieval-augmented generation combines retrieval with language models. "
    "RAG reduces hallucination by grounding answers in retrieved passages. "
    "Dense vector search is used to find relevant context."
)


class TestHealth:
    def test_health_reports_provider(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        # No key configured in tests -> the offline model must be active.
        assert body["llm"]["live"] is False

    def test_api_prefixed_health(self, client):
        assert client.get("/api/health").status_code == 200


class TestProjects:
    def test_create_returns_flat_object(self, client):
        resp = client.post(
            "/api/projects", json={"name": "My Research", "description": "notes"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Research"
        assert data["description"] == "notes"
        assert data["id"]

    def test_list_returns_bare_array(self, client):
        """The frontend maps over this directly — it must not be wrapped."""
        client.post("/api/projects", json={"name": "P1"})
        client.post("/api/projects", json={"name": "P2"})

        resp = client.get("/api/projects")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert {p["name"] for p in body} == {"P1", "P2"}

    def test_get_missing_project_404s(self, client):
        assert client.get("/api/projects/nonexistent").status_code == 404

    def test_delete_project(self, client):
        from app.config import settings
        from app.dependencies import get_chroma_store
        from services.knowledge_graph.networkx_store import kg_store

        pid = client.post("/api/projects", json={"name": "Temp"}).json()["id"]
        other_pid = client.post("/api/projects", json={"name": "Keep"}).json()["id"]

        vector_store = get_chroma_store()
        vector_store.add_chunks(
            ids=["delete-me", "keep-me"],
            documents=["project content", "other project content"],
            metadatas=[
                {"project_id": pid, "document_id": "d1"},
                {"project_id": other_pid, "document_id": "d2"},
            ],
        )
        graph = kg_store.for_project(pid)
        graph_path = graph.persist_path
        graph.add_entity("Temporary concept")
        uploads = settings.upload_dir / pid
        uploads.mkdir(parents=True)
        (uploads / "paper.pdf").write_bytes(b"uploaded content")

        assert client.delete(f"/api/projects/{pid}").status_code == 204
        assert client.get(f"/api/projects/{pid}").status_code == 404
        assert vector_store.count(project_id=pid) == 0
        assert vector_store.count(project_id=other_pid) == 1
        assert not uploads.exists()
        assert not graph_path.exists()
        assert pid not in kg_store._graphs


class TestIngestion:
    def _project(self, client) -> str:
        return client.post("/api/projects", json={"name": "Test"}).json()["id"]

    def test_upload_pdf_indexes_and_starts_a_task(self, client):
        project_id = self._project(client)

        resp = client.post(
            f"/api/projects/{project_id}/documents",
            files={
                "file": ("paper.pdf", io.BytesIO(_pdf_bytes([TRANSFORMER_PAGE, RAG_PAGE])), "application/pdf")
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "completed"
        assert data["num_pages"] == 2
        assert data["num_chunks"] > 0
        # Upload must kick off the Analysis -> KG -> Citation pipeline.
        assert data["task_id"]

    def test_non_pdf_rejected(self, client):
        project_id = self._project(client)
        resp = client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_to_missing_project_404s(self, client):
        resp = client.post(
            "/api/projects/missing/documents",
            files={"file": ("p.pdf", io.BytesIO(_pdf_bytes(["Some text."])), "application/pdf")},
        )
        assert resp.status_code == 404

    def test_project_detail_lists_document(self, client):
        project_id = self._project(client)
        client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": ("doc.pdf", io.BytesIO(_pdf_bytes(["Content here."])), "application/pdf")},
        )

        detail = client.get(f"/api/projects/{project_id}").json()
        assert len(detail["documents"]) == 1
        assert detail["documents"][0]["filename"] == "doc.pdf"
        assert detail["num_documents"] == 1


class TestQuery:
    def _project_with_pdf(self, client) -> str:
        project_id = client.post("/api/projects", json={"name": "Research"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/documents",
            files={
                "file": ("paper.pdf", io.BytesIO(_pdf_bytes([TRANSFORMER_PAGE, RAG_PAGE])), "application/pdf")
            },
        )
        return project_id

    def test_query_returns_answer_and_sources(self, client):
        project_id = self._project_with_pdf(client)

        resp = client.post(
            f"/api/projects/{project_id}/query",
            json={"question": "How does self-attention work?", "top_k": 5},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["question"] == "How does self-attention work?"
        assert data["answer"]
        assert 0 < len(data["results"]) <= 5

    def test_results_carry_provenance(self, client):
        project_id = self._project_with_pdf(client)

        data = client.post(
            f"/api/projects/{project_id}/query",
            json={"question": "What is retrieval-augmented generation?"},
        ).json()

        assert data["results"]
        for result in data["results"]:
            assert result["document_name"] == "paper.pdf"
            assert result["page"] is not None and result["page"] >= 1
            assert result["chunk_id"]
            assert result["text"]
            assert isinstance(result["score"], float)

    def test_query_missing_project_404s(self, client):
        resp = client.post("/api/projects/nope/query", json={"question": "test"})
        assert resp.status_code == 404

    def test_empty_project_says_it_cannot_answer(self, client):
        project_id = client.post("/api/projects", json={"name": "Empty"}).json()["id"]

        data = client.post(
            f"/api/projects/{project_id}/query", json={"question": "anything"}
        ).json()

        assert data["results"] == []
        assert "cannot answer" in data["answer"].lower()

    def test_retrieve_only_skips_generation(self, client):
        project_id = self._project_with_pdf(client)
        data = client.post(
            f"/api/projects/{project_id}/retrieve", json={"question": "attention"}
        ).json()
        assert data["answer"] == ""
        assert data["results"]


class TestGraph:
    def test_empty_graph_is_valid_shape(self, client):
        project_id = client.post("/api/projects", json={"name": "G"}).json()["id"]
        data = client.get(f"/api/projects/{project_id}/graph").json()
        assert data["nodes"] == []
        assert data["links"] == []

    def test_graph_missing_project_404s(self, client):
        assert client.get("/api/projects/nope/graph").status_code == 404


class TestTasks:
    def test_analyze_flow_completes_with_an_answer(self, client):
        project_id = client.post("/api/projects", json={"name": "Flow"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/documents",
            files={
                "file": ("paper.pdf", io.BytesIO(_pdf_bytes([TRANSFORMER_PAGE, RAG_PAGE])), "application/pdf")
            },
        )

        # TestClient runs background tasks synchronously, so by now it is done.
        tasks = client.get(f"/api/projects/{project_id}/tasks").json()
        assert tasks, "upload should have created a task"

        task = client.get(f"/api/tasks/{tasks[0]['id']}").json()
        assert task["status"] == "completed", task.get("error")
        assert task["result"]["answer"]
        assert task["result"]["routing"]["flow"] == "analyze"
        assert task["events"], "the activity log must not be empty"

    def test_answer_flow_produces_citations(self, client):
        project_id = client.post("/api/projects", json={"name": "QA"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/documents",
            files={
                "file": ("paper.pdf", io.BytesIO(_pdf_bytes([TRANSFORMER_PAGE, RAG_PAGE])), "application/pdf")
            },
        )

        created = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "How does RAG reduce hallucination?", "flow": "answer"},
        )
        assert created.status_code == 201

        task = client.get(f"/api/tasks/{created.json()['id']}").json()
        assert task["status"] == "completed", task.get("error")
        assert task["result"]["citations"], "answer flow must attach provenance"
        assert task["result"]["references"], "citation agent must produce references"

    def test_invalid_flow_rejected(self, client):
        project_id = client.post("/api/projects", json={"name": "Bad"}).json()["id"]
        resp = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "hi", "flow": "teleport"},
        )
        assert resp.status_code == 400

    def test_task_missing_404s(self, client):
        assert client.get("/api/tasks/nope").status_code == 404


class TestSearchFlowEndToEnd:
    """Steps 1-5 of the demo flow, with arXiv stubbed out."""

    @staticmethod
    def _patch_arxiv(monkeypatch):
        import services.agents.literature as literature_module

        from test_literature import _FakeClient

        monkeypatch.setattr(literature_module.httpx, "AsyncClient", _FakeClient)

    def test_topic_search_indexes_papers_and_builds_graph(self, client, monkeypatch):
        self._patch_arxiv(monkeypatch)

        project_id = client.post("/api/projects", json={"name": "Search"}).json()["id"]

        created = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "find papers on retrieval augmented generation"},
        )
        assert created.status_code == 201

        task = client.get(f"/api/tasks/{created.json()['id']}").json()
        assert task["status"] == "completed", task.get("error")

        result = task["result"]
        assert result["routing"]["flow"] == "search"
        assert len(result["papers"]) == 2
        assert len(result["references"]) == 2
        assert result["answer"]

        # 4. Knowledge Graph agent populated the graph.
        graph = client.get(f"/api/projects/{project_id}/graph").json()
        assert graph["nodes"], "search flow must add nodes to the knowledge graph"
        assert any(n["group"] == "Paper" for n in graph["nodes"])
        assert any(n["group"] == "Person" for n in graph["nodes"])

        # 5. Papers are persisted for the Papers list.
        papers = client.get(f"/api/projects/{project_id}/papers").json()
        assert len(papers) == 2
        assert papers[0]["reference"]

        # 6. Indexed abstracts are now answerable by RAG.
        answer = client.post(
            f"/api/projects/{project_id}/query",
            json={"question": "language models store factual knowledge"},
        ).json()
        assert answer["results"], "retrieved papers must be queryable"

    def test_stats_reflect_the_run(self, client, monkeypatch):
        self._patch_arxiv(monkeypatch)
        project_id = client.post("/api/projects", json={"name": "Stats"}).json()["id"]
        client.post(
            f"/api/projects/{project_id}/tasks",
            json={"question": "find papers on rag", "flow": "search"},
        )

        stats = client.get(f"/api/projects/{project_id}/stats").json()
        assert stats["papers"] == 2
        assert stats["graph"]["nodes"] > 0
        assert stats["task_counts"]["completed"] == 1
        assert sum(stats["task_counts"].values()) == stats["tasks"]

    def test_evaluation_status_separates_what_it_can_and_cannot_measure(self, client):
        status = client.get("/api/evaluation/status").json()
        # Retrieval metrics need no LLM, so they are always available once the
        # curated golden set ships with the package.
        assert status["status"] == "ready"
        assert status["retrieval_metrics_available"] is True
        assert status["golden_set_size"] > 0
        # Answer-quality metrics are only claimed when RAGAS really is present
        # and a live model can judge.
        assert status["answer_metrics_available"] == (status["ragas_installed"] and status["llm_live"])
        assert set(status["metrics"]) == {
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
        }
