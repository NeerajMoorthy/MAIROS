#!/usr/bin/env python3
"""Run every MAIROS flow against a live backend and record what really happens.

Everything else in this repository is verified offline with a deterministic
model. That proves the plumbing and the validation rules, and proves nothing
about output quality with a real LLM over a real corpus. This harness closes
that gap: it drives the running API over HTTP, times each flow, counts the
events each one emitted, records how much output the validation rules dropped,
and writes both machine-readable JSON and a Markdown table for ``docs/``.

Usage::

    # 1. Start the backend with a real key configured in mairos/.env
    cd apps/api && uvicorn main:app --port 8000

    # 2. Point the harness at a folder of text-based PDFs
    python scripts/live_validation.py --corpus ~/papers --out docs/results_data.json

    # Or let the Literature agent build the corpus from a topic search
    # (arXiv, OpenAlex and Semantic Scholar abstracts) instead:
    python scripts/live_validation.py --topic "retrieval augmented generation"

The script refuses to run against the offline fallback model unless
``--allow-offline`` is passed, because a "live validation" recorded against the
deterministic stand-in would be worse than no numbers at all.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover - dependency guard
    print("httpx is required: pip install httpx", file=sys.stderr)
    raise SystemExit(2)

# Flows exercised, and the question used to drive each one.
FLOW_PROBES: dict[str, str] = {
    "search": "retrieval augmented generation for scientific question answering",
    "answer": "How does retrieval reduce hallucination?",
    "compare": "Compare the methods and reported results of these papers",
    "gaps": "What open problems and limitations remain in this literature?",
    "hypothesis": "What hypotheses follow from the gaps in this literature?",
    "experiment": "Design experiments to test the open problems in this literature",
    "patent": "Which concepts in this project overlap the stored patent text?",
    "novelty": "Is this idea already covered by the indexed sources?",
    # `review` is the long chain — literature, indexing, retrieval, comparison,
    # novelty, synthesis — so it is the probe most likely to time out, and the
    # one whose timing is most worth recording.
    "review": "Review the recent literature on retrieval-augmented generation",
}

# Where each flow's structured output lives, and the key that reports how much
# the evidence rules threw away.
RESULT_KEYS: dict[str, tuple[str, str | None]] = {
    "compare": ("comparison", "uncited_cells_dropped"),
    "gaps": ("gaps", "uncited_gaps_dropped"),
    "hypothesis": ("hypotheses", "unattached_dropped"),
    "experiment": ("experiments", "incomplete_dropped"),
    "patent": ("patent_awareness", None),
    "novelty": ("novelty", "uncited_notes_dropped"),
    "review": ("comparison", "uncited_cells_dropped"),
}

POLL_SECONDS = 2.0
POLL_TIMEOUT = 300.0


@dataclass
class FlowOutcome:
    """What one flow actually did on this corpus."""

    flow: str
    question: str
    status: str = "not_run"
    seconds: float = 0.0
    events: int = 0
    agents: list[str] = field(default_factory=list)
    answer_chars: int = 0
    citations: int = 0
    references: int = 0
    structured_items: int = 0
    dropped_by_validation: int | None = None
    error: str | None = None
    notes: str = ""


@dataclass
class RunReport:
    """The whole session: environment, corpus, flows, retrieval metrics."""

    started_at: str
    base_url: str
    llm: dict = field(default_factory=dict)
    corpus: dict = field(default_factory=dict)
    flows: list[FlowOutcome] = field(default_factory=list)
    evaluation: dict = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["flows"] = [asdict(f) if not isinstance(f, dict) else f for f in self.flows]
        return data


# ---------------------------------------------------------------------------
# Driving the API
# ---------------------------------------------------------------------------
def wait_for_task(client: httpx.Client, task_id: str) -> dict:
    """Poll a task until it settles, or until the timeout expires."""
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        task = client.get(f"/tasks/{task_id}").json()
        if task.get("status") in {"completed", "failed"}:
            return task
        time.sleep(POLL_SECONDS)
    return {"status": "timeout", "events": [], "result": None, "error": "poll timeout"}


def run_flow(client: httpx.Client, project_id: str, flow: str, question: str) -> FlowOutcome:
    """Start one flow, wait for it, and measure what came back."""
    outcome = FlowOutcome(flow=flow, question=question)
    started = time.monotonic()

    try:
        created = client.post(
            f"/projects/{project_id}/tasks", json={"question": question, "flow": flow}
        )
        created.raise_for_status()
        task = wait_for_task(client, created.json()["id"])
    except Exception as exc:
        outcome.status = "error"
        outcome.error = f"{type(exc).__name__}: {exc}"
        outcome.seconds = round(time.monotonic() - started, 2)
        return outcome

    outcome.seconds = round(time.monotonic() - started, 2)
    outcome.status = task.get("status", "unknown")
    outcome.error = task.get("error")

    events = task.get("events") or []
    outcome.events = len(events)
    outcome.agents = sorted({e.get("agent_name", "") for e in events if e.get("agent_name")})

    result = task.get("result") or {}
    outcome.answer_chars = len(result.get("answer") or "")
    outcome.citations = len(result.get("citations") or [])
    outcome.references = len(result.get("references") or [])

    key, dropped_key = RESULT_KEYS.get(flow, (None, None))
    if key:
        payload = result.get(key) or {}
        if isinstance(payload, dict):
            for candidate in ("rows", "gaps", "hypotheses", "experiments", "overlaps"):
                if isinstance(payload.get(candidate), list):
                    outcome.structured_items = len(payload[candidate])
                    break
            if dropped_key is not None:
                outcome.dropped_by_validation = payload.get(dropped_key)
            if payload.get("note"):
                outcome.notes = str(payload["note"])[:200]

    return outcome


def upload_corpus(client: httpx.Client, project_id: str, corpus: Path) -> dict:
    """Upload every PDF in *corpus*, reporting per-file success."""
    pdfs = sorted(p for p in corpus.glob("*.pdf") if p.is_file())
    uploaded, rejected = [], []

    for pdf in pdfs:
        try:
            with open(pdf, "rb") as handle:
                response = client.post(
                    f"/projects/{project_id}/documents",
                    files={"file": (pdf.name, handle, "application/pdf")},
                    timeout=180.0,
                )
            if response.status_code == 201:
                body = response.json()
                uploaded.append(
                    {"file": pdf.name, "pages": body["num_pages"], "chunks": body["num_chunks"]}
                )
            else:
                rejected.append({"file": pdf.name, "status": response.status_code,
                                 "detail": response.json().get("detail", "")[:160]})
        except Exception as exc:
            rejected.append({"file": pdf.name, "status": 0, "detail": f"{type(exc).__name__}: {exc}"})

    return {
        "source": str(corpus),
        "documents": len(uploaded),
        "rejected": rejected,
        "chunks": sum(item["chunks"] for item in uploaded),
        "files": uploaded,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_markdown(report: RunReport) -> str:
    """A Markdown summary suitable for pasting into docs/RESULTS.md."""
    llm = report.llm or {}
    lines = [
        "### Run summary",
        "",
        f"- Date: {report.started_at}",
        f"- Backend: `{report.base_url}`",
        f"- Model: `{llm.get('model', 'unknown')}` (provider `{llm.get('provider', 'unknown')}`, "
        f"live: {llm.get('live')})",
        f"- Corpus: {report.corpus.get('documents', 0)} documents, "
        f"{report.corpus.get('chunks', 0)} indexed chunks",
        "",
        "| Flow | Status | Seconds | Events | Items | Dropped | Answer chars | Citations |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for flow in report.flows:
        entry = flow if isinstance(flow, FlowOutcome) else FlowOutcome(**flow)
        dropped = "—" if entry.dropped_by_validation is None else str(entry.dropped_by_validation)
        lines.append(
            f"| `{entry.flow}` | {entry.status} | {entry.seconds} | {entry.events} | "
            f"{entry.structured_items} | {dropped} | {entry.answer_chars} | {entry.citations} |"
        )

    durations = [
        (f if isinstance(f, FlowOutcome) else FlowOutcome(**f)).seconds
        for f in report.flows
    ]
    if durations:
        lines += [
            "",
            f"Median flow latency: **{statistics.median(durations):.1f}s** · "
            f"slowest: **{max(durations):.1f}s**",
        ]

    evaluation = report.evaluation or {}
    if evaluation.get("aggregates"):
        agg = evaluation["aggregates"]
        lines += [
            "",
            "### Retrieval quality on this corpus",
            "",
            "| Recall@5 | Precision@5 | MRR | nDCG@5 | Cases scored | Not in corpus |",
            "|---|---|---|---|---|---|",
            f"| {agg.get('recall_at_5')} | {agg.get('precision_at_5')} | {agg.get('mrr')} | "
            f"{agg.get('ndcg_at_5')} | {evaluation.get('cases_evaluated')} | "
            f"{evaluation.get('cases_unsupported')} |",
        ]

    if report.failures:
        lines += ["", "### Failures observed", ""]
        lines += [f"- {failure}" for failure in report.failures]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8000/api", help="API base URL")
    parser.add_argument("--corpus", type=Path, help="Folder of text-based PDFs to ingest")
    parser.add_argument(
        "--topic",
        help="Build the corpus from a literature search on this topic instead "
        "(arXiv, OpenAlex and Semantic Scholar abstracts)",
    )
    parser.add_argument("--out", type=Path, default=Path("docs/results_data.json"))
    parser.add_argument("--markdown", type=Path, help="Also write the Markdown summary here")
    parser.add_argument("--project-name", default="Live validation")
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="Run even when the backend reports the offline fallback model (not a real validation)",
    )
    args = parser.parse_args()

    if not args.corpus and not args.topic:
        parser.error("give either --corpus (a folder of PDFs) or --topic (a literature search)")

    report = RunReport(
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        base_url=args.base,
    )

    with httpx.Client(base_url=args.base, timeout=120.0) as client:
        try:
            health = client.get("/health").json()
        except Exception as exc:
            print(f"Cannot reach the backend at {args.base}: {exc}", file=sys.stderr)
            return 2

        report.llm = health.get("llm", {})
        if not report.llm.get("live") and not args.allow_offline:
            print(
                "The backend is running the offline fallback model. Numbers recorded "
                "now would say nothing about live quality.\n"
                "Set GROQ_API_KEY and restart the backend, or pass --allow-offline "
                "to record a plumbing-only run.",
                file=sys.stderr,
            )
            return 3

        project_id = client.post("/projects", json={"name": args.project_name}).json()["id"]
        print(f"project {project_id}")

        # --- corpus -------------------------------------------------------
        if args.corpus:
            report.corpus = upload_corpus(client, project_id, args.corpus)
            for rejected in report.corpus.get("rejected", []):
                report.failures.append(
                    f"upload rejected: {rejected['file']} ({rejected['status']}) {rejected['detail']}"
                )
        else:
            outcome = run_flow(client, project_id, "search", args.topic)
            report.flows.append(outcome)
            stats = client.get(f"/projects/{project_id}/stats").json()
            report.corpus = {
                "source": f"literature search: {args.topic}",
                "documents": stats.get("papers", 0),
                "chunks": stats.get("chunks", 0),
                "rejected": [],
                "files": [],
            }

        print(f"corpus: {report.corpus.get('documents')} docs / {report.corpus.get('chunks')} chunks")

        # A patent record so the patent flow has something to compare against.
        client.post(
            f"/projects/{project_id}/patents",
            json={
                "title": "Live validation placeholder patent",
                "text": "retrieval augmented generation using an embedding index and attention",
            },
        )

        # --- flows --------------------------------------------------------
        already = {f.flow for f in report.flows}
        for flow, question in FLOW_PROBES.items():
            if flow in already:
                continue
            print(f"running {flow}…", flush=True)
            outcome = run_flow(client, project_id, flow, question)
            report.flows.append(outcome)
            if outcome.status != "completed":
                report.failures.append(f"flow {flow}: {outcome.status} {outcome.error or ''}".strip())

        # --- retrieval metrics --------------------------------------------
        try:
            report.evaluation = client.post(
                f"/projects/{project_id}/evaluation/run", json={"k": 5}
            ).json()
        except Exception as exc:
            report.failures.append(f"evaluation: {type(exc).__name__}: {exc}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"wrote {args.out}")

    markdown = render_markdown(report)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown, encoding="utf-8")
        print(f"wrote {args.markdown}")

    print()
    print(markdown)
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
