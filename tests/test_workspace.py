"""Settings: load the example workspace, download its files, clear the workspace.

The example must leave every feature something to work on — three indexed
papers with their analysis runs, and a stored patent — and clearing must
remove every project, but only when the request says so explicitly and only
the caller's own projects when authentication is on.
"""

from __future__ import annotations

from services.samples import railguard
from tests.test_auth import auth_on, headers_for, signing_keys  # noqa: F401

CONFIRM = {"confirm": "delete-everything"}


def _load(client, **kwargs):
    response = client.post("/api/workspace/example", **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


class TestDescribe:
    def test_lists_files_and_a_step_for_every_feature(self, client):
        body = client.get("/api/workspace/example").json()

        assert body["name"] == railguard.EXAMPLE_PROJECT_NAME
        assert [f["name"] for f in body["files"]] == [name for name, _, _ in railguard.SAMPLE_FILES]
        features = {step["feature"] for step in body["guide"]}
        assert {
            "Topic search", "Upload files", "Review my project", "Compare papers",
            "Detect research gaps", "Generate hypotheses", "Design experiments",
            "Check what is new here", "Literature review", "Patent awareness",
        } <= features

    def test_every_workflow_step_names_a_registered_flow(self, client):
        from services.agents.router import FLOWS

        for step in client.get("/api/workspace/example").json()["guide"]:
            if step["flow"]:
                assert step["flow"] in FLOWS
                assert step["where"] == "workflows"

    def test_review_input_is_long_enough_for_the_intake_step(self, client):
        guide = client.get("/api/workspace/example").json()["guide"]
        review = next(step for step in guide if step["flow"] == "project")
        assert len(review["input"]) >= 200


class TestLoad:
    def test_creates_a_project_with_papers_analyses_and_a_patent(self, client):
        body = _load(client)
        project_id = body["project_id"]

        assert [d["filename"] for d in body["documents"]] == [p[0] for p in railguard.PAPERS]
        assert all(d["num_pages"] == 2 and d["num_chunks"] == 4 for d in body["documents"])

        stats = client.get(f"/api/projects/{project_id}/stats").json()
        assert stats["documents"] == 3
        assert stats["chunks"] == 12
        # Inline in tests: the three analysis runs have finished by now.
        assert stats["task_counts"]["completed"] == 3

        patents = client.get(f"/api/projects/{project_id}/patents").json()["patents"]
        assert [p["title"] for p in patents] == [railguard.PATENT_TITLE]
        assert patents[0]["id"] == body["patent_id"]

    def test_the_example_answers_the_walkthrough_question(self, client):
        project_id = _load(client)["project_id"]
        response = client.post(
            f"/api/projects/{project_id}/retrieve",
            json={"question": "recall and precision of the lightweight CNN in daylight", "top_k": 3},
        )
        texts = " ".join(r["text"] for r in response.json()["results"])
        assert "recall of 0.91" in texts

    def test_loading_again_replaces_the_previous_example(self, client):
        first = _load(client)
        client.post("/api/projects", json={"name": "My own project"})

        second = _load(client)

        assert second["replaced"] == 1
        names = sorted(p["name"] for p in client.get("/api/projects").json())
        assert names == sorted(["My own project", railguard.EXAMPLE_PROJECT_NAME])
        assert client.get(f"/api/projects/{first['project_id']}").status_code == 404


class TestFiles:
    def test_every_listed_file_downloads(self, client):
        for name, media_type, _ in railguard.SAMPLE_FILES:
            response = client.get(f"/api/workspace/example/files/{name}")
            assert response.status_code == 200, name
            assert response.headers["content-type"].split(";")[0] == media_type.split(";")[0]
            assert name in response.headers["content-disposition"]
            assert response.content

    def test_unknown_names_are_404(self, client):
        assert client.get("/api/workspace/example/files/secrets.txt").status_code == 404
        assert client.get("/api/workspace/example/files/..%2Fstate.json").status_code == 404

    def test_the_downloaded_paper_uploads_like_any_pdf(self, client):
        project_id = client.post("/api/projects", json={"name": "Uploads"}).json()["id"]
        pdf = client.get("/api/workspace/example/files/paper-b-ultrasonic-guided-waves.pdf").content
        response = client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": ("paper-b.pdf", pdf, "application/pdf")},
        )
        assert response.status_code == 201
        assert response.json()["num_chunks"] == 4

    def test_the_scanned_page_is_refused_on_upload(self, client):
        project_id = client.post("/api/projects", json={"name": "Uploads"}).json()["id"]
        scanned = client.get("/api/workspace/example/files/scanned-page.pdf").content
        response = client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": ("scanned-page.pdf", scanned, "application/pdf")},
        )
        assert response.status_code == 422


class TestClear:
    def test_refused_without_the_confirmation(self, client):
        client.post("/api/projects", json={"name": "Keep me"})

        for params in ({}, {"confirm": "yes"}):
            assert client.delete("/api/workspace", params=params).status_code == 400
        assert len(client.get("/api/projects").json()) == 1

    def test_deletes_every_project_and_its_data(self, client, tmp_path):
        from app.config import settings

        example = _load(client)
        client.post("/api/projects", json={"name": "Another"})

        response = client.delete("/api/workspace", params=CONFIRM)

        assert response.status_code == 200
        assert response.json() == {"deleted": 2}
        assert client.get("/api/projects").json() == []
        assert client.get(f"/api/projects/{example['project_id']}").status_code == 404
        assert not (settings.upload_dir / example["project_id"]).exists()

    def test_an_empty_workspace_clears_to_zero(self, client):
        assert client.delete("/api/workspace", params=CONFIRM).json() == {"deleted": 0}


class TestWithAuth:
    def test_clear_and_reload_touch_only_the_callers_projects(self, client, auth_on, signing_keys):
        private, _ = signing_keys
        alice, bob = headers_for(private, "alice"), headers_for(private, "bob")
        client.post("/api/projects", json={"name": "Bob's"}, headers=bob)
        _load(client, headers=bob)

        assert _load(client, headers=alice)["replaced"] == 0
        assert client.delete("/api/workspace", params=CONFIRM, headers=alice).json() == {"deleted": 1}

        assert sorted(p["name"] for p in client.get("/api/projects", headers=bob).json()) == sorted(
            ["Bob's", railguard.EXAMPLE_PROJECT_NAME]
        )

    def test_needs_a_token(self, client, auth_on):
        assert client.post("/api/workspace/example").status_code == 401
        assert client.delete("/api/workspace", params=CONFIRM).status_code == 401
