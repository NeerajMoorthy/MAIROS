# Mid-Review Demo Script (5 minutes)

> **Superseded.** This is the original mid-review script, kept for reference.
> The current sequence — which also covers the research workflows and the
> evaluation dashboard — is [DEMONSTRATION.md](DEMONSTRATION.md).

## Pre-flight (10 minutes before)

1. `cd mairos && cp .env.example .env`, set `GROQ_API_KEY`.
2. Backend: `cd apps/api && uvicorn main:app --reload --port 8000`
3. Confirm the LLM is live: `curl localhost:8000/api/health` should show
   `"live": true`. If it shows `false`, the key is missing — the demo still
   works but answers become extractive.
4. Frontend: `cd apps/web && npm run dev`
5. Have one text-based PDF ready (e.g. *Attention Is All You Need*).
6. Open <http://localhost:3000>.

> Warm the embedding model first: upload your PDF once before the review so the
> ~90 MB model download does not happen live.

---

## Minute 1 — The problem and the shape of the system

Open the **Projects** page and create a project.

> "MAIROS answers research questions with citations you can check. Three
> pieces: a RAG pipeline over papers, a knowledge graph built as papers are
> processed, and a multi-agent orchestrator that decides which agents to run
> for a given request."

---

## Minute 2 — Topic search (the search flow)

**Search & Upload** → type *"retrieval augmented generation for scientific
question answering"* → Search.

> "I did not tell it what to do. The Orchestrator's Router classifies the
> request — this one is literature discovery, so it runs Literature → Indexer →
> Knowledge Graph → Citation → Synthesis."

The UI jumps to **Agent Activity**.

---

## Minute 3 — Watching the agents (the money shot)

Point at the activity log as it fills in:

- **Orchestrator** — the routing decision *and its reason*.
- **Literature** — the queries it ran, which of arXiv, OpenAlex and Semantic
  Scholar answered, and the papers it kept, by title. *"If a source is down or
  rate-limited, it says so here and in the result's 'What was searched'
  section, instead of quietly searching less."*
- **Indexer** — chunks embedded into ChromaDB. *"This is what makes them
  answerable in the next step."*
- **Knowledge Graph** — nodes and edges added, with the delta.
- **Citation** — APA references generated.
- **Synthesis** — the grounded overview.

Scroll to the final answer and the APA reference list.

---

## Minute 4 — Upload a PDF (the analyze flow)

**Search & Upload** → upload your PDF.

> "Same orchestrator, different route. A specific document means the Analysis
> agent, not literature search: Loader → Analysis → Knowledge Graph →
> Citation."

Show the new run in **Agent Activity** — note the different pipeline on the
orchestrator's second log line.

---

## Minute 5 — Grounded Q&A and the graph

**Chat & Q&A** → *"How does this paper reduce hallucination?"*

> "The answer is generated only from the retrieved passages. Every claim ends
> with its source and page, and the passages themselves are shown underneath —
> so grounding is auditable, not asserted."

Expand a source card and match a sentence to it.

**Knowledge Graph** → the accumulated graph.

> "Both runs wrote into this. Colour is entity type — papers, authors, methods,
> concepts, datasets. It also feeds back into retrieval: a chunk reachable in
> the graph gets its vector score boosted, and shows a *graph* badge in chat."

Click a node to show its type and mention count.

---

## Closing

> "End to end: ingestion with page-level provenance, hybrid retrieval,
> multi-agent orchestration with live tracing, an accumulating knowledge graph,
> and citation grounding. Next: hypothesis generation, novelty detection, and
> experiment design — each is a new agent class registered with the
> orchestrator, no restructuring."

---

## If something breaks

| Symptom | What to say | Fix |
|---|---|---|
| arXiv times out | *"The Literature agent failed and the pipeline degraded instead of crashing — that's the `safe_run` contract."* | Point at the failed event; upload a PDF instead. |
| LLM rate-limited | *"We're in offline-fallback mode; the orchestration and retrieval are unaffected, answers become extractive quotes."* | Nothing — it self-degrades. |
| Chat says it cannot answer | *"That's correct behaviour — it refuses rather than hallucinating when retrieval misses."* | Ask something covered by the PDF. |
| Scanned PDF rejected (422) | *"OCR is out of scope for mid-review."* | Use a text-based PDF. |
| Graph is empty | Run a search or upload first. | — |
