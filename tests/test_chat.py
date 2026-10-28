"""Chat & Q&A answer through the orchestrator's agents.

The Chat tab used to call retrieval and generation directly, so its questions
never passed through the agents and never appeared in Agent Activity. Both
chat endpoints now run the ``answer`` flow (retriever → synthesis → citation)
as a recorded task.
"""

import json

from fastapi.testclient import TestClient


def _project_with_pdf(client: TestClient, sample_pdf) -> str:
    project_id = client.post("/api/projects", json={"name": "Chat"}).json()["id"]
    with open(sample_pdf, "rb") as handle:
        client.post(
            f"/api/projects/{project_id}/documents",
            files={"file": ("paper.pdf", handle, "application/pdf")},
        )
    return project_id


def _events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_query_is_answered_by_the_answer_flow_and_recorded(client: TestClient, sample_pdf):
    project_id = _project_with_pdf(client, sample_pdf)

    data = client.post(
        f"/api/projects/{project_id}/query",
        json={"question": "How does self-attention work?", "top_k": 2},
    ).json()

    assert data["answer"] and data["results"]
    assert len(data["results"]) <= 2, "top_k reaches the retriever agent"
    task = client.get(f"/api/tasks/{data['task_id']}").json()
    assert task["flow"] == "answer" and task["status"] == "completed"
    agents = [event["agent_name"] for event in task["events"]]
    assert {"orchestrator", "retriever", "synthesis", "citation"} <= set(agents)
    assert task["result"]["answer"] == data["answer"]


def test_chat_streams_each_agent_step_then_the_answer(client: TestClient, sample_pdf):
    project_id = _project_with_pdf(client, sample_pdf)

    with client.stream(
        "POST", f"/api/projects/{project_id}/chat", json={"question": "What is RAG?"}
    ) as response:
        assert response.status_code == 200
        events = _events("".join(response.iter_text()))

    kinds = [kind for kind, _ in events]
    first_other = next(i for i, kind in enumerate(kinds) if kind != "step")
    assert kinds[:first_other] == ["step"] * first_other, "steps come first, as they happen"
    assert kinds[first_other:] == ["sources", "token", "done"]
    steps = {data["agent"] for kind, data in events if kind == "step"}
    assert {"retriever", "synthesis", "citation"} <= steps

    sources = events[first_other][1]["sources"]
    assert sources and all(s["document_name"] == "paper.pdf" for s in sources)
    done = events[-1][1]
    assert done["ok"] is True
    task = client.get(f"/api/tasks/{done['task_id']}").json()
    assert task["flow"] == "answer"
    assert task["result"]["answer"] == events[first_other + 1][1]["token"]


def test_chat_on_an_empty_project_refuses_without_sources(client: TestClient):
    project_id = client.post("/api/projects", json={"name": "Empty"}).json()["id"]

    with client.stream(
        "POST", f"/api/projects/{project_id}/chat", json={"question": "What is AI?"}
    ) as response:
        events = dict(_events("".join(response.iter_text())))

    assert events["sources"]["sources"] == []
    assert "cannot answer" in events["token"]["token"].lower()


def test_every_registered_agent_belongs_to_a_flow():
    """The Planner agent was registered but in no flow, so it never ran. An
    agent the orchestrator can never reach is dead code that misdescribes the
    system; this keeps the registry and the flows in step."""
    from services.agents.orchestrator import AgentOrchestrator
    from services.agents.router import FLOWS
    from services.generation.provider import OfflineChatModel

    used = {agent for agents in FLOWS.values() for agent in agents}
    registered = set(AgentOrchestrator(llm=OfflineChatModel()).agents)

    assert registered - used == set(), "registered but never run"
    assert used - registered == set(), "named in a flow but not registered"
