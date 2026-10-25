# MAIROS — Final Demonstration Sequence

Roughly 10 minutes, in this order. Each step builds on the previous one, so the
evidence chain is visible by the end rather than asserted at the start.

> The earlier five-minute mid-review script is kept at
> [MID_REVIEW_DEMO.md](MID_REVIEW_DEMO.md); this document supersedes it.

---

## Pre-flight (10 minutes before)

1. `cd mairos && cp .env.example .env`, set `GROQ_API_KEY`.
2. Backend: `cd apps/api && uvicorn main:app --reload --port 8000`
3. Confirm the LLM is live: `curl localhost:8000/api/health` should report
   `"live": true`. If it reports `false`, the demo still runs end to end —
   every workflow degrades to deterministic output and the UI says so.
4. Frontend: `cd apps/web && npm run dev` → <http://localhost:3000>
5. Have **two** text-based PDFs ready (the comparison needs two documents), and
   one patent abstract copied to the clipboard — e.g. any record on
   <https://patents.google.com>.
6. Upload one PDF once beforehand so the ~90 MB embedding model is already
   downloaded.

---

## 1 · The shape of the system (1 min)

Create a project. Point at the sidebar: Projects, Workspace, Tasks, Knowledge
Graph, Evaluation.

> "Three pieces underneath: a RAG pipeline over papers, a knowledge graph built
> as papers are processed, and an orchestrator that decides which agents run.
> Everything else in this demo is an agent added to that orchestrator — the
> orchestrator itself has not changed since the mid-review."

---

## 2 · Ingest and ground (2 min)

**Search & Upload** → run a topic search, then upload both PDFs.

Watch the **Tasks** trace: Router → Retrieval → Indexing → Knowledge Graph →
Citation → Synthesis, with real timestamps and messages.

**Chat & Q&A** → ask a question about the uploaded papers.

> "Every claim ends with its source and page, the retrieval score is shown, and
> the passages themselves are underneath — grounding is auditable, not
> asserted."

---

## 3 · Paper comparison (1.5 min)

**Workflows → Compare papers → Run.**

> "This is a comparison table, not a summary. Rows are dimensions the sources
> actually speak to; columns are the documents. Every cell has a citation chip —
> click one and it opens the passage that cell came from."

If the run reports dropped cells, say so:

> "Cells the model produced that no retrieved passage supported were dropped and
> counted. A cited table that quietly includes an unsupported claim is worse
> than no table."

---

## 4 · Gaps → hypotheses → experiments (3 min)

**Workflows → Detect research gaps → Run.**

> "Each gap is quoted from the sentence that states it. If the wording cannot be
> located in a retrieved passage, the gap is dropped — a gap is a claim about
> the literature, so it needs evidence like any other."

Point at the structural signals separately:

> "These come from the knowledge graph, not from a model: concepts only one
> paper mentions, and method pairs nothing in this corpus compares. Absence of
> evidence in this corpus, which is why they are labelled as signals rather than
> findings."

**Workflows → Generate hypotheses → Run.** Show that each hypothesis names the
gap it descends from and keeps that gap's citation.

**Workflows → Design experiments → Run.** Open one design: objective, datasets,
baselines, deciding metric, ordered procedure, controls, threats to validity.

> "The full chain is visible: passage → quoted gap → hypothesis → protocol. The
> system will not produce a design for a hypothesis nobody proposed, or a
> hypothesis for a gap nothing evidenced."

---

## 5 · Patent awareness (1 min)

**Workflows → Patent awareness.** Paste the patent title, the public link, and
the abstract text, then **Run**.

> "Note what is not here: a fetch button. MAIROS never downloads a patent — the
> text compared is what I pasted, and the link is validated against a list of
> free public registries and stored only as a reference. That keeps it clear of
> commercial database terms and removes the server-side request surface
> entirely."

Point at the disclaimer, which is attached to every response:

> "Research-support only. Not legal advice or a patentability assessment. The
> findings are literal term overlaps computed in Python — a model cannot invent
> one — and no overlap is never reported as clearance."

Open **Knowledge Graph**: the patent appears as its own node type.

---

## 6 · Evaluation (1.5 min)

**Evaluation** page → pick the project → **Run evaluation**.

> "Recall@5, MRR, Precision@5, and nDCG@5, computed live against this project's
> own indexed chunks. No LLM involved, so these numbers are reproducible."

Expand one case:

> "You can see exactly which passages came back and which counted as relevant.
> The relevance rule is a documented keyword policy, not a claim of human
> labelling — it is printed next to the score."

Point at the unsupported cases:

> "These are excluded from the averages rather than scored zero: their evidence
> does not exist in this corpus, so the retriever never had a chance to find it.
> Counting them as failures would understate the retriever and flatter the next
> build that adds the missing paper."

And the RAGAS banner:

> "Faithfulness and answer relevancy need RAGAS, which is not installed here, so
> the dashboard says so and shows no number for them. Retrieval metrics do not
> need it."

---

## Closing (30 s)

> "End to end: ingestion with page-level provenance, hybrid retrieval, a
> multi-agent orchestrator with a live trace, an accumulating knowledge graph,
> five research workflows that each refuse to state what they cannot cite, and
> measured retrieval quality. 183 tests pass offline — no API key, no network.
> What is deliberately not here: authentication, cloud deployment, and learned
> graph models, all listed as deferred in the README."

---

## If something breaks

| Symptom | What to say | Fix |
|---|---|---|
| arXiv times out | *"The Literature agent failed and the pipeline degraded instead of crashing — that's the `safe_run` contract."* | Point at the failed event; upload a PDF instead. |
| LLM rate-limited | *"We're in offline-fallback mode. Orchestration, retrieval, evidence linking and every validation rule are unaffected — the text just gets more conservative."* | Nothing; it self-degrades. |
| Comparison says it needs two sources | *"Correct behaviour — it widened retrieval, still found one document, and said so rather than comparing a paper with itself."* | Upload the second PDF. |
| No gaps found | *"Nothing in these passages stated a limitation it could quote, so it reported none. The graph signals below are still computed."* | Use a paper with a limitations section. |
| Evaluation shows low recall | *"That's the honest number for this corpus — one PDF covering a tenth of the golden set. Watch it move as documents are added."* | Add more documents and re-run. |
| Patent URL rejected | *"The allowlist is doing its job — only free public registries are accepted as references."* | Use a patents.google.com link, or paste text with no link. |
