# Prompt — build MAIROS from nothing to ~84%

Paste everything below the line into a fresh session with an empty directory.

This is long because the project is large. It is ordered so that every stage
runs and is testable before the next one starts, and so that nothing is built
on something unproven.

---

Build **MAIROS — Multi-Agent Intelligent Research & Orchestration System**: an
AI research assistant that combines retrieval-augmented generation, a knowledge
graph, and a multi-agent orchestrator to answer research questions with
citations a reader can check, and that runs seven research workflows on top of
that foundation.

## The one idea the whole system is built around

**Nothing is displayed that cannot be traced back to a retrieved passage.**

Every generated claim is checked against the text that was actually retrieved,
and a claim no passage supports is dropped and counted rather than shown. This
is not a feature bolted on at the end — it is the constraint that shapes the
agent design, the data structures, the tests, and the UI. When you have a
choice between a system that says more and a system that can defend everything
it says, choose the second one every time.

Two corollaries that come up constantly:

- **Computed beats generated.** Where a finding can be derived in Python from
  retrieved text, derive it. Use the model for phrasing, never for a verdict.
  A model asked "is this novel?" or "do these overlap?" will oblige.
- **Say what you did not do.** An absence of evidence is reported as an
  absence of evidence, never as a negative finding. This costs nothing and is
  the difference between a system a researcher can rely on and one they cannot.

## Stack and constraints

Python ≥ 3.11 and Node ≥ 20. **No Docker, no database server, no cloud
services.** Everything runs locally from two commands.

Backend: FastAPI, Pydantic v2, pydantic-settings, uvicorn. ChromaDB embedded
for vectors, `sentence-transformers` (`all-MiniLM-L6-v2`) for embeddings,
NetworkX for the knowledge graph, PyMuPDF for PDF extraction, LangChain core
plus `langchain-groq` for the LLM.

Frontend: Next.js 14 App Router, React 18, TypeScript in `strict` mode,
Tailwind v4 (configured in CSS, not `tailwind.config.ts`), shadcn/ui-style
components over Radix primitives, `lucide-react`, `react-force-graph-2d`.

Out of scope for this build, and to be recorded as deferred with reasons:
authentication, multi-user isolation, cloud deployment, Docker, and
learned/GNN models over the knowledge graph.

Layout — a monorepo, with the Pydantic schemas as the single API contract so
the backend and the typed frontend client cannot drift apart:

```
mairos/
├── apps/api/            # FastAPI: main.py, app/{config,store,dependencies,routers}
├── apps/web/            # Next.js
├── packages/shared-types/   # Pydantic schemas — the API contract
├── services/            # agents, ingestion, retrieval, knowledge_graph,
│                        # generation, evaluation, patents, common
├── tests/               # pytest, fully offline
└── docs/
```

## The rule that governs the whole build

**The test suite runs with no API key, no model download, and no network.** Not
"can be made to" — by default. A test that reaches the internet is a broken
test. This is what makes the project demonstrable on any machine, and it forces
a design where every external dependency has a seam.

Two pieces make it work, and both are worth building carefully:

1. **A deterministic offline chat model** implementing LangChain's
   `BaseChatModel`, used automatically when no `GROQ_API_KEY` is set. It must
   return well-formed, schema-correct output derived from the prompt itself —
   for grounded answers it quotes retrieved context verbatim and invents
   nothing. Give every agent prompt a task marker (`[MAIROS-TASK: gaps]`) so
   the offline model can produce the right shape; real models ignore it.
2. **A hashing embedder** for tests, not a constant vector. It must preserve
   relative similarity so retrieval tests assert on actual ranking rather than
   on arbitrary order.

After every stage below, run the full test suite and the production build, and
do not move on until both are green.

```bash
python -m pytest -q
cd apps/web && npm test && npx tsc --noEmit && npm run build
```

---

## Stage 1 — Foundation

Project skeleton, `pydantic-settings` config reading a root `.env` with
absolute paths (so behaviour never depends on the working directory), the
shared Pydantic schemas, and a FastAPI app with `/api/health` reporting which
LLM provider is live.

An in-memory metadata store for projects, documents, papers and tasks, behind a
narrow method surface — `create_project`, `list_documents`, `add_task_event`
and so on. **Design this surface as though it will be swapped onto a database
later, because in Stage 9 it is.** Guard mutations with a lock from the start;
FastAPI runs sync endpoints in a threadpool, so concurrent access is the normal
case, not an edge case.

The offline chat model and the provider resolution described above.

## Stage 2 — Ingestion and retrieval

PDF extraction with PyMuPDF preserving page numbers — page provenance is what
makes a citation checkable later, so never lose it. Recursive chunking
(512/64 by default) that keeps document id, name, page and chunk index on every
chunk.

ChromaDB in embedded mode with `project_id` filtering, and a `HybridRetriever`
that fuses dense vector search with knowledge-graph traversal, boosting chunks
whose entities the graph connects to the question. Keep the reranker interface
available (`HybridRetriever(reranker=...)`) even if unused by default.

Scanned PDFs have no extractable text. Detect that and return HTTP 422 with an
explanation rather than silently indexing an empty document — there is no OCR
and pretending otherwise wastes the user's time.

## Stage 3 — Knowledge graph

Per-project NetworkX graph, persisted to JSON, with papers, authors and
extracted concepts as nodes. LLM-based entity extraction with a deterministic
fallback, and a `GraphRetriever` the hybrid retriever consumes.

Keep `ProjectGraph`'s surface to about five methods so it could be
reimplemented over Neo4j without touching the retriever.

## Stage 4 — The multi-agent orchestrator

A `BaseAgent` abstract class taking an `AgentContext`, mutating it, returning
it. That single contract is what lets new agents be added without any agent
knowing about any other. `safe_run` converts a failure into a logged error
event so one failing agent degrades the answer rather than aborting the run.

A `RouterAgent` that classifies a request into a flow using the LLM, with a
keyword heuristic as fallback — and a registry mapping flow names to ordered
agent lists. `GET /api/flows` reads that registry, so a new flow appears in the
UI without a frontend change.

**Do not use LangGraph.** These flows are short, linear, and fully determined
by one routing decision made up front — no cycles, no conditional re-entry, no
checkpointing needed at this scale. A `StateGraph` would add a dependency and
an indirection layer without removing a line of logic. Write that reasoning
down in the orchestrator's docstring; "why not the obvious framework" is a
question every reader will have.

First agents: Literature (arXiv, no API key needed), Indexer, Loader,
Retriever, Analysis, Knowledge Graph, Citation (APA 7th, with a deterministic
non-LLM formatter as fallback), Synthesis.

Flows: `search`, `analyze`, `answer`.

Tasks run as FastAPI `BackgroundTasks`, emitting real `TaskEvent`s as they go,
so the UI can show the pipeline live.

Two router details worth getting right now, because they are easy to get wrong
and annoying to debug later. Keyword hints must be multi-word: bare `protocol`
and `ablation` are ordinary subject-matter nouns and will capture requests that
are merely *about* them. And explicit discovery intent ("find papers on X")
must beat a topic keyword, or the same request will route differently once the
project has documents than it did when empty.

## Stage 5 — The interface

Next.js App Router with an `AppShell` (collapsible sidebar, header, backend
status), a projects page, and a project workspace with tabs: Search & Upload,
Chat & Q&A, Workflows, Agent Activity, Knowledge Graph.

A fully typed API client in `lib/api.ts` mirroring the Pydantic schemas. All
requests to a relative `/api` path with a `next.config.js` rewrite to
`127.0.0.1:8000`, so there is no CORS preflight in development and no base URL
to configure in the browser.

Every panel needs four states — loading, empty, error, success — and the empty
states should say what to do next, not just that there is nothing. The Agent
Activity panel shows the live event stream; the Knowledge Graph panel renders
the force graph with a detail card on selection.

When the offline model is in use, say so in the UI. A reviewer seeing
extractive answers should know why.

## Stage 6 — Evidence-linked research workflows

This is where the project stops being a competent RAG demo and becomes the
thing it is for.

Build `services/agents/evidence.py` first: it groups retrieved chunks into
labelled sources (`S1`, `S2`) for prompting, and attaches the passage that best
supports a returned claim by content-word overlap — returning `None` when
nothing overlaps, which is the signal to drop the claim. Nothing in it calls an
LLM. Every workflow below uses it, so a reviewer only has to check the logic
once.

One subtlety worth knowing in advance: anything that ranks terms by frequency
needs occurrence counts, not a set of distinct words. Deduplicate for overlap
tests, count for ranking — a set makes every term tie at one and the ordering
silently collapses to alphabetical.

Then four agents, each with a rule about what it will not do:

- **Comparison** (`compare`) — a table of dimensions × documents where every
  cell carries the passage behind it. A cell no retrieved passage supports is
  dropped and counted. Widen retrieval when fewer than two distinct documents
  are in play, and say so when there is still nothing to compare.
- **Gap detection** (`gaps`) — gaps quoted from the sentence that states them,
  dropped if the wording cannot be located in a passage. Separately, structural
  signals computed from the graph (thinly covered concepts, never-compared
  method pairs), kept visually distinct because a missing edge is evidence
  about this corpus only.
- **Hypothesis** (`hypothesis`) — falsifiable hypotheses, each carrying the
  citation of the gap it descends from. One attached to no evidenced gap, or
  with no testable prediction, is dropped.
- **Experiment** (`experiment`) — objective, datasets, baselines, deciding
  metric, ordered procedure, controls, threats to validity. A design with no
  metric or no procedure decides nothing and is dropped.

The chain is `passage → quoted gap → hypothesis → experiment design`, and each
link must be traceable in the UI.

Render these with a citation chip that expands to the exact supporting passage.

## Stage 7 — Evaluation

Four retrieval metrics computed live with no LLM involved: Recall@k,
Precision@k, MRR, nDCG@k. Ship a curated golden set of about ten hand-written
cases across single-hop, multi-hop and comparison difficulty, and show every
case in the dashboard so a reviewer can read what is being asked before
trusting a score.

Three decisions make these numbers defensible rather than decorative:

1. **A real Recall denominator** — scan the project's whole indexed corpus with
   the case's own relevance rule to count how many relevant passages exist,
   rather than assuming one per question.
2. **Unsupported cases are excluded, not zeroed.** If a case's evidence is not
   in the project at all, the retriever never had a chance; report it as "not
   in this corpus" and keep it out of the averages. Zeroing it would measure
   the corpus, not the retriever.
3. **Name the relevance policy in the UI.** It is a documented keyword proxy,
   not human labels, and saying so is the difference between an honest number
   and a misleading one.

Wire RAGAS as an optional dependency for answer-quality metrics, opt-in per
run. Availability has two independent conditions — the package installed *and*
a live LLM judge — and the UI must say which one is missing rather than
showing a placeholder. Label any result it produces as **model-judged**, not
computed, wherever it appears.

## Stage 8 — Patent awareness (the narrow safe subset)

A researcher wants to know whether their project's vocabulary shows up in a
patent. That is answerable. Whether they infringe one is not, and this feature
must never imply it does.

- MAIROS **never fetches a patent.** The text analysed is what the user
  pasted; a URL is stored as a reference for a human to open, never requested
  by the server. No request-forgery surface, no scraping.
- Links are **allowlisted** to free public registries (Google Patents,
  Espacenet, PATENTSCOPE, USPTO, PatentsView, Indian Patent Search).
- Findings are **computed** — literal term matching in Python. A model may
  phrase a summary of findings that already exist and may not add, remove or
  reword one.
- Every response carries the disclaimer: *Research-support only. Not legal
  advice or a patentability assessment.* Absence of overlap is never reported
  as clearance.

Flow `patent`, plus endpoints to add and remove patent references by hand.

## Stage 9 — Frontend tests and CI

Vitest, Testing Library and jsdom covering every panel's loading, empty, error
and success states — including a failed-task error state and the
citation-chip reveal. GitHub Actions running `pytest`, `npm test` and
`npm run build` on every push.

Two setup notes that will otherwise cost an hour each. `@vitejs/plugin-react`
is ESM-only, so the config file must be `vitest.config.mts`. And if `tsconfig`
sets `jsx: "preserve"` for Next, Vitest needs `esbuild: { jsx: "automatic" }`
or every test fails with `React is not defined`.

Mock the API client with a proxy that lazily creates a `vi.fn()` per accessed
method, so tests do not need updating every time an endpoint is added.

## Stage 10 — Persistence

Replace the in-memory store with SQLite, **behind the same method surface** —
no call site should change. Verify that by running the existing suite
unchanged.

A document table (id, project_id, created_at, payload JSON) rather than a
normalised schema: every read goes through the in-memory cache, nothing queries
metadata relationally, and the only filters are "by project" and "newest
first". A normalised schema would buy nothing and cost a migration every time a
Pydantic model gains a field. Lift out and index the two columns anything
actually filters on.

WAL mode, `busy_timeout`, and a per-thread connection — sharing one SQLite
connection across threads is exactly the pattern that raises
`SQLite objects created in a thread can only be used in that same thread`.
Keep a registry of every connection opened so `close()` can close all of them,
and use a separate lock for that registry: the write lock is already held when
a connection is created, and `threading.Lock` is not reentrant.

Tests the JSON snapshot could not have passed: restart durability, a run
interrupted mid-pipeline keeping its events, task history not capped, cascade
delete, and concurrent writes from 20+ threads. Add concurrent *reads* during
writes too — unlocked `dict.values()` iteration raises
`RuntimeError: dictionary changed size during iteration` under ordinary load.

## Stage 11 — Novelty and literature review

A `NoveltyAgent`, and this is the most delicate agent in the system.

"Is this novel?" is an unbounded negative claim: supporting it means showing
nothing in the published record anticipates the idea. A system that has read a
handful of PDFs cannot show that. So the agent answers the narrower question it
*can* answer and refuses the wider one out loud:

- **"New to this project"** — computed by content-word overlap against
  retrieved passages. Cite the covering passage where there is one; where there
  is not, say so with the exact scope of what was searched.
- **"Novel in the field"** — always `"not_assessed"`, with a reason naming what
  assessing it would require. No code path may set it to anything else. Make it
  a module constant so a grep proves there is no branch that upgrades it, and
  type it in TypeScript as the string literal so the UI cannot render one.

Four traps here, all of which are easy to fall into and hard to notice:

1. **The verdict must not come from the model.** Test it with a deliberately
   sycophantic model that calls everything unprecedented, and assert not one
   verdict moves.
2. **`NoveltyAgent` is not the last agent in the flow.** Synthesis runs after
   it and writes the headline prose. Handed "is my idea of X novel?" over
   passages that do not mention X, a model obeying every grounding rule answers
   "none of these describe X, so it appears to be novel" and cites a passage
   for it. Strip novelty framing from the question before any model sees it,
   and compose the novelty answer from the computed report rather than
   generating it.
3. **Score the idea, not the phrasing.** The overlap ratio divides by the
   claim's own token count, so every word typed only to ask the question drags
   it down — towards "not found in this corpus", the one verdict that reads
   like a novelty signal. Strip the framing before scoring too.
4. **A high ratio on a short claim means nothing.** Four content words reach
   0.75 on three incidental hits in a long passage, so a table caption gets
   reported as prior coverage. Require a minimum number of *matched* words, not
   just a high proportion.

Then a `review` flow chaining discovery into comparison and synthesis:
`literature → indexer → retriever → comparison → novelty → knowledge_graph →
citation → synthesis`. The retriever in the middle is load-bearing — Literature
puts papers on the context and Indexer embeds them, but Comparison reads
`retrieved_chunks`, so without a retrieval step it compares nothing.

Note that this flow indexes fetched arXiv abstracts into the project and
retrieves them straight back, so they arrive at the novelty agent looking like
"documents from this project". Distinguish them by document id when reporting
scope, or a project with no uploads will be told its own library lacks
something it never contained.

## Stage 12 — Accessibility and responsive hardening

Verify rather than assert. Three layers, all of which found real defects:

- **A browser pass** (Playwright) over every route at 375, 768 and 1440 px,
  checking horizontal overflow, target sizes, accessible names and focus
  indicators.
- **axe-core** running the WCAG 2.1 AA ruleset inside the Vitest suite against
  the *populated* result views — the states that only exist after a run, which
  is most of what a reviewer actually looks at. Disable the colour-contrast
  rule there: jsdom lays nothing out, so axe cannot read a real computed
  colour.
- **A computed contrast test** that parses the theme tokens out of
  `globals.css`, converts OKLCH to sRGB, and asserts every real pairing meets
  4.5:1 for text and 3:1 for meaningful non-text. Write the conversion
  yourself — it is about forty lines — and include tests of the conversion
  itself, or the suite is only self-consistent.

Expect to find, among others: a sidebar that opens at 240 px on a 375 px phone
and pushes the page off-screen; nav buttons stranded in the tab order behind a
zero-width container (`visibility: hidden`, not just `w-0`, is what removes
them); inputs labelled by placeholder alone; colour tokens that fail AA outright
in one theme; and bare `<button>` disclosures with no focus ring and no
`aria-expanded`.

If you make the sidebar overlay on mobile, two things follow immediately: it
must close when a nav item is used, or it covers the page the user just asked
for; and it must render closed below the breakpoint *by CSS*, because the
server-rendered HTML is painted before any hydration effect can correct it.

Honour `prefers-reduced-motion`. No visual redesign in this stage.

## Stage 13 — Baseline hardening

No authentication — this is a single-researcher tool, and that stays recorded
as deferred rather than pretended. What is needed is protection against one
client or a runaway loop exhausting the box.

- **Body caps** checked from `Content-Length` before anything reads the body.
  Also meter the stream: a chunked HTTP/1.1 request has no `Content-Length` at
  all, and a header-only check waves it straight through.
- **Rate limits**, fixed window per client address, with a smaller budget for
  anything that starts agent work. Exempt the health probe by *exact path* — a
  suffix match makes `/anything/health` an unlimited endpoint. Put
  embedding-heavy routes and cascading deletes on the write budget. Evict idle
  counters. Say in the docstring that this is per-worker rather than implying a
  distributed guarantee.
- **CORS** from configuration, never `*`, credentials off, methods and headers
  enumerated. **Add it last so it is outermost** — a rejection produced above
  `CORSMiddleware` carries no `Access-Control-Allow-Origin`, so the browser
  blocks it and every carefully worded 413, 429 and 503 reaches the frontend as
  an opaque `TypeError: Failed to fetch`.
- **Structured logging**, one JSON line per request with a correlation id
  returned as `X-Request-ID`. Sanitise a client-supplied id before it reaches
  log output.
- **Outage handling**: a dependency being unreachable is a 503 naming which
  dependency and what to do; a genuine bug stays a 500 with its stack trace in
  the log, not in the response. Be narrow about which exceptions count —
  `isinstance(exc, OSError)` also catches `FileNotFoundError` and
  `PermissionError`, which are bugs, not outages. Follow only the explicit
  `__cause__` chain, never `__context__`: Python sets that implicitly for
  anything raised inside any `except` block, so one handled file lookup
  upstream turns every later exception into a false 503.

Implement the generic handler as **middleware**, not
`@app.exception_handler(Exception)` — the latter lives in
`ServerErrorMiddleware`, outside CORS, so its responses are unreadable by the
browser.

## Stage 14 — Live-model validation, honestly

Write a harness that indexes a real corpus, runs every flow against a live
model, and records per flow: status, wall-clock time, events emitted, items
produced, **how many items the evidence rules dropped**, and citations. That
dropped count is the most interesting number in the report — a high one means
the model is asserting things the corpus does not support and the guard is
earning its place.

The harness must **refuse to run against the offline model** unless explicitly
forced. A "live validation" recorded against the deterministic stand-in would
be worse than no numbers at all.

Write `docs/RESULTS.md` separating what is **proven** (the offline suite) from
what is **not yet measured** (output quality under a live model). If the run
cannot be executed in the environment, produce the harness, leave the table
empty, and say plainly why — do not fill it with plausible-looking figures.

---

## Throughout

**Comment the decisions, not the syntax.** A comment explaining *why* a
threshold is 0.6, why the store is a document table, why LangGraph was rejected
or why a test asserts an absence is worth ten explaining what a loop does. When
you fix a bug, record what it was in the comment — the next person to read that
line is deciding whether to undo your fix.

**Write tests that assert the system's own guarantees**, not that a model said
something. "An uncitable comparison cell is dropped", "a fabricated patent
overlap cannot reach the report", "no verdict moves when the model insists
everything is unprecedented" — these stay true regardless of which model runs.

**Docs as you go**: a `README.md` that explains design decisions rather than
listing files, a status document, a roadmap, and `docs/RESULTS.md`.

## Before calling it done

Have the work reviewed adversarially: read the code looking for ways each
guarantee could fail rather than confirming it works, reproduce every finding
before fixing it, and add a test for each. When this was done on the real
build it found fourteen genuine defects that a fully passing suite had not
caught — including an agent whose own guarantee held while the flow around it
broke the same promise.

Then state which stages are complete, which are partial and why, and what
percentage of the full scope you believe the project has actually reached —
with the reasoning, not just the number. If something could not be measured in
the environment you had, that belongs in the number and in the write-up.

At this point the project is at roughly 84%. The remaining work is completing
patent awareness beyond the safe subset — claim-level segmentation, weighted
scoring, metadata, a dedicated page, export — plus a final visual design pass
and the live-model figures.
