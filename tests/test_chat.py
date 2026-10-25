"""Tests for the chat and generation endpoint."""

from fastapi.testclient import TestClient

def test_chat_endpoint_returns_success(client: TestClient, monkeypatch):
    """Test that the chat endpoint retrieves chunks and streams a response."""
    
    # Setup project and pdf
    resp = client.post("/api/projects", json={"name": "Chat Test Project"})
    project_id = resp.json()["id"]

    # Mock the LLM generation
    async def mock_generate_stream(self, question, chunks):
        yield "This "
        yield "is "
        yield "a "
        yield "mocked "
        yield "response."
        
    from services.generation.llm import GenerationService
    monkeypatch.setattr(GenerationService, "generate_stream", mock_generate_stream)

    # Use client.stream context manager
    with client.stream(
        "POST",
        f"/api/projects/{project_id}/chat",
        json={"question": "What is AI?"}
    ) as response:
        assert response.status_code == 200
        text = "".join([chunk for chunk in response.iter_text()])
        assert "event: sources" in text
        assert '{"token": "This "}' in text
        assert '{"token": "is "}' in text
        assert '{"token": "a "}' in text
        assert '{"token": "mocked "}' in text
        assert '{"token": "response."}' in text
        assert "event: done" in text
