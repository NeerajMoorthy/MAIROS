"""Project deletion and the empty-project evidence boundary, end to end.

Deletion must remove everything a project owns — documents, chunks, graph,
papers, patents and task history — from memory *and* from the database, and
must not touch any other project. A newly created project with nothing indexed
must not present a source-grounded answer or a citation, even when another
project on the same server is full of matching text.
"""

from __future__ import annotations

from app.store import MetadataStore, metadata_store


def _upload(client, project_id: str, pdf_path) -> None:
    with open(pdf_path, "rb") as handle:
        response = client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": ("paper.pdf", handle, "application/pdf")},
        )
    assert response.status_code == 201, response.text


class TestProjectDeletion:
    def test_everything_a_project_owns_goes_and_its_neighbour_stays(self, client, sample_pdf):
        from app.dependencies import get_chroma_store

        doomed = client.post("/api/projects", json={"name": "Doomed"}).json()["id"]
        kept = client.post("/api/projects", json={"name": "Kept"}).json()["id"]
        for project_id in (doomed, kept):
            _upload(client, project_id, sample_pdf)
            client.post(
                f"/api/projects/{project_id}/patents",
                json={"title": "P", "text": "Claims\n1. A system comprising self attention."},
            )
            client.post(
                f"/api/projects/{project_id}/tasks",
                json={"question": "what is attention?", "flow": "answer"},
            )

        assert client.delete(f"/api/projects/{doomed}").status_code == 204

        assert metadata_store.get_project(doomed) is None
        assert metadata_store.list_documents(doomed) == []
        assert metadata_store.list_patents(doomed) == []
        assert metadata_store.list_tasks(doomed) == []
        assert get_chroma_store().count(project_id=doomed) == 0

        assert metadata_store.list_documents(kept)
        assert metadata_store.list_patents(kept)
        assert metadata_store.list_tasks(kept)
        assert get_chroma_store().count(project_id=kept) > 0

        # And the rows are gone from the database, not just the cache: a
        # restart must not resurrect them.
        restarted = MetadataStore(database_file=metadata_store.database_file, state_file=metadata_store.state_file)
        restarted.load()
        assert restarted.get_project(doomed) is None
        assert restarted.list_patents(doomed) == []
        assert restarted.list_tasks(doomed) == []
        assert restarted.get_project(kept) is not None

    def test_deleting_a_missing_project_is_a_404(self, client):
        assert client.delete("/api/projects/does-not-exist").status_code == 404


class TestUploadStorage:
    def test_the_original_filename_is_kept_in_metadata_not_in_the_path(self, client, sample_pdf):
        """A long filename overflowed Windows' 260-character path limit (a bare 500)."""
        from app.config import settings

        project_id = client.post("/api/projects", json={"name": "Long names"}).json()["id"]
        long_name = ("a-very-long-descriptive-paper-title-" * 6) + "final.pdf"
        with open(sample_pdf, "rb") as handle:
            response = client.post(
                f"/api/projects/{project_id}/documents",
                files={"file": (long_name, handle, "application/pdf")},
            )

        assert response.status_code == 201, response.text
        assert metadata_store.list_documents(project_id)[0].filename == long_name
        stored = list((settings.upload_dir / project_id).iterdir())
        assert len(stored) == 1
        assert long_name not in stored[0].name and len(stored[0].name) <= 36

    def test_a_file_that_is_not_a_pdf_is_refused_readably_and_leaves_nothing(self, client):
        """Regression (walkthrough K2): a text file renamed to .pdf answered a
        bare 500, the stored file stayed behind (locked on Windows), and
        deleting the project then failed with a 503 until the lock was freed."""
        from app.config import settings

        project_id = client.post("/api/projects", json={"name": "Not a PDF"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": ("notes.pdf", b"This is a plain text file renamed to .pdf.", "application/pdf")},
        )

        assert response.status_code == 400, response.text
        assert "not a readable PDF" in response.json()["detail"]
        assert metadata_store.list_documents(project_id) == []
        upload_folder = settings.upload_dir / project_id
        assert not upload_folder.exists() or not any(upload_folder.iterdir())
        assert client.delete(f"/api/projects/{project_id}").status_code == 204

    def test_a_password_protected_pdf_is_refused_with_the_reason(self, client):
        import fitz  # PyMuPDF

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "Results that need a password.")
        locked = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
        doc.close()

        project_id = client.post("/api/projects", json={"name": "Locked"}).json()["id"]
        response = client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": ("locked.pdf", locked, "application/pdf")},
        )

        assert response.status_code == 400, response.text
        assert "password-protected" in response.json()["detail"]
        assert metadata_store.list_documents(project_id) == []


class TestEmptyProjectEvidenceBoundary:
    def test_a_new_project_cites_nothing_even_when_another_project_could(self, client, sample_pdf):
        full = client.post("/api/projects", json={"name": "Full"}).json()["id"]
        _upload(client, full, sample_pdf)
        empty = client.post("/api/projects", json={"name": "Empty"}).json()["id"]

        question = {"question": "How does self-attention process sequences?"}

        grounded = client.post(f"/api/projects/{full}/query", json=question).json()
        assert grounded["results"], "the project with the paper must retrieve it"

        refused = client.post(f"/api/projects/{empty}/query", json=question).json()
        assert refused["results"] == []
        assert "cannot answer" in refused["answer"].lower()

    def test_a_forced_answer_run_on_an_empty_project_has_no_citations(self, client):
        empty = client.post("/api/projects", json={"name": "Empty"}).json()["id"]
        task = client.post(
            f"/api/projects/{empty}/tasks",
            json={"question": "How does self-attention work?", "flow": "answer"},
        ).json()

        result = client.get(f"/api/tasks/{task['id']}").json()["result"]
        assert result["citations"] == []
        assert result["answer"].startswith("I cannot answer this based on the provided documents")
        assert "p. " not in result["answer"], "no page citation may appear without a retrieved passage"

    def test_once_a_paper_is_indexed_the_same_run_is_cited(self, client, sample_pdf):
        project = client.post("/api/projects", json={"name": "Grows"}).json()["id"]
        _upload(client, project, sample_pdf)
        task = client.post(
            f"/api/projects/{project}/tasks",
            json={"question": "How does self-attention work?", "flow": "answer"},
        ).json()

        result = client.get(f"/api/tasks/{task['id']}").json()["result"]
        assert result["citations"], "an indexed upload is evidence the run may cite"
        assert all(c["document_name"] == "paper.pdf" for c in result["citations"])
