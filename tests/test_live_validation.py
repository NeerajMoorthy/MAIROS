"""Tests for the live-validation harness.

The harness itself cannot run offline — it needs a live model, reachable
literature sources, and the embedding model — so what is tested here is everything that
does not need the network: how a task's response is turned into a measurement,
and how those measurements are rendered. That keeps the reporting path honest
before it is ever pointed at a real run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live_validation.py"

pytest.importorskip("httpx")

_spec = importlib.util.spec_from_file_location("live_validation", _SCRIPT)
live_validation = importlib.util.module_from_spec(_spec)
sys.modules["live_validation"] = live_validation
assert _spec.loader is not None
_spec.loader.exec_module(live_validation)

FlowOutcome = live_validation.FlowOutcome
RunReport = live_validation.RunReport


class FakeClient:
    """Minimal stand-in for httpx.Client — returns canned task payloads."""

    def __init__(self, created: dict, task: dict):
        self._created = created
        self._task = task
        self.posts: list[tuple[str, dict]] = []

    class _Response:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def post(self, url: str, json: dict | None = None, **kwargs):
        self.posts.append((url, json or {}))
        return self._Response(self._created)

    def get(self, url: str, **kwargs):
        return self._Response(self._task)


COMPLETED_TASK = {
    "id": "t1",
    "status": "completed",
    "error": None,
    "events": [
        {"agent_name": "orchestrator", "stage": "orchestrating"},
        {"agent_name": "retriever", "stage": "retrieving"},
        {"agent_name": "gaps", "stage": "analyzing"},
    ],
    "result": {
        "answer": "An answer of some length.",
        "citations": [{"chunk_id": "c1"}, {"chunk_id": "c2"}],
        "references": ["Ref one."],
        "gaps": {
            "gaps": [{"id": "GAP1"}, {"id": "GAP2"}],
            "uncited_gaps_dropped": 3,
            "graph_signals": [],
        },
    },
}


class TestFlowMeasurement:
    def test_measures_events_agents_and_dropped_output(self):
        client = FakeClient({"id": "t1"}, COMPLETED_TASK)

        outcome = live_validation.run_flow(client, "p1", "gaps", "what is missing?")

        assert outcome.status == "completed"
        assert outcome.events == 3
        assert outcome.agents == ["gaps", "orchestrator", "retriever"]
        assert outcome.structured_items == 2
        # The point of the harness: record what validation threw away.
        assert outcome.dropped_by_validation == 3
        assert outcome.citations == 2
        assert outcome.answer_chars == len("An answer of some length.")

    def test_forces_the_requested_flow(self):
        client = FakeClient({"id": "t1"}, COMPLETED_TASK)
        live_validation.run_flow(client, "p1", "experiment", "how would we test this?")

        url, body = client.posts[0]
        assert url == "/projects/p1/tasks"
        assert body["flow"] == "experiment"

    def test_a_failed_flow_is_recorded_not_raised(self):
        failed = {**COMPLETED_TASK, "status": "failed", "error": "boom", "result": None}
        outcome = live_validation.run_flow(FakeClient({"id": "t1"}, failed), "p1", "gaps", "q")

        assert outcome.status == "failed"
        assert outcome.error == "boom"
        assert outcome.structured_items == 0

    def test_a_transport_error_is_recorded_not_raised(self):
        class Exploding(FakeClient):
            def post(self, *args, **kwargs):
                raise RuntimeError("connection refused")

        outcome = live_validation.run_flow(
            Exploding({}, {}), "p1", "compare", "compare these"
        )
        assert outcome.status == "error"
        assert "connection refused" in outcome.error


class TestMarkdownRendering:
    def _report(self) -> RunReport:
        return RunReport(
            started_at="2026-09-19 10:00:00",
            base_url="http://localhost:8000/api",
            llm={"provider": "groq", "model": "llama-3.3-70b-versatile", "live": True},
            corpus={"documents": 17, "chunks": 812, "rejected": []},
            flows=[
                FlowOutcome(flow="answer", question="q", status="completed", seconds=4.0,
                            events=6, structured_items=0, answer_chars=900, citations=5),
                FlowOutcome(flow="gaps", question="q", status="completed", seconds=12.0,
                            events=9, structured_items=4, dropped_by_validation=2,
                            answer_chars=700, citations=5),
            ],
            evaluation={
                "aggregates": {"recall_at_5": 0.71, "precision_at_5": 0.3,
                               "mrr": 0.82, "ndcg_at_5": 0.74},
                "cases_evaluated": 8,
                "cases_unsupported": 2,
            },
        )

    def test_reports_environment_corpus_and_every_flow(self):
        markdown = live_validation.render_markdown(self._report())

        assert "llama-3.3-70b-versatile" in markdown
        assert "17 documents, 812 indexed chunks" in markdown
        assert "| `answer` | completed |" in markdown
        assert "| `gaps` | completed |" in markdown

    def test_reports_latency_and_retrieval_metrics(self):
        markdown = live_validation.render_markdown(self._report())

        assert "Median flow latency: **8.0s**" in markdown
        assert "slowest: **12.0s**" in markdown
        assert "0.71" in markdown and "0.82" in markdown

    def test_a_flow_that_dropped_nothing_shows_a_dash_not_a_zero(self):
        markdown = live_validation.render_markdown(self._report())
        answer_row = next(line for line in markdown.splitlines() if "`answer`" in line)
        assert "| — |" in answer_row

    def test_failures_are_listed_rather_than_summarised_away(self):
        report = self._report()
        report.failures = ["flow patent: failed rate limited"]
        markdown = live_validation.render_markdown(report)

        assert "Failures observed" in markdown
        assert "rate limited" in markdown

    def test_renders_before_any_flow_has_run(self):
        empty = RunReport(started_at="now", base_url="http://x/api")
        markdown = live_validation.render_markdown(empty)
        assert "Run summary" in markdown


def test_every_probed_flow_is_a_registered_flow():
    """The harness must not probe a flow the orchestrator does not have."""
    from services.agents.router import FLOWS

    assert set(live_validation.FLOW_PROBES) <= set(FLOWS)
    assert set(live_validation.RESULT_KEYS) <= set(FLOWS)
