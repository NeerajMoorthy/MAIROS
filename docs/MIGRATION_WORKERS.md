# Migration plan: Cloudflare Workers + Supabase + external AI APIs

**Status:** proposal, 26 October 2026 — nothing in this plan has been started.
Approve it (or change it) before any code moves.

**Goal:** the link works whenever anyone opens it, without the project owner's
PC. The public API runs on **Cloudflare Workers**, everything that must persist
lives in **Supabase**, model inference goes to **external AI APIs**, and every
long research workflow is **submitted as a job and processed asynchronously**
instead of holding one HTTP request open.

---

## 1. Why this is a port, not a redeploy

The current backend cannot run on Workers as it is:

- It is Python: FastAPI, LangChain, **PyMuPDF** (PDF text), **ChromaDB**
  (vectors), **sentence-transformers / PyTorch** (embeddings), NetworkX
  (graphs). Python Workers run on Pyodide (WebAssembly) and accept only pure
  Python or specially built packages
  ([packages](https://developers.cloudflare.com/workers/languages/python/packages/));
  PyMuPDF, ChromaDB and PyTorch are not among them.
- A Worker has **128 MB of memory** and no disk, so the index, graphs and
  uploads cannot live inside it.
- On the free Workers plan each request and each Workflow step gets **10 ms of
  CPU** ([limits](https://developers.cloudflare.com/workers/platform/limits/)).
  Waiting on Groq or Supabase is free, but PDF parsing, chunking and the
  computed scores (coverage, patent overlap) are not. The **Workers Paid plan
  (US$5/month)** allows up to 5 minutes of CPU
  ([changelog](https://developers.cloudflare.com/changelog/post/2025-03-25-higher-cpu-limits/)).

The code to port, measured today:

| Area | Python lines | What it does |
|---|---:|---|
| `services/agents` | 3,728 | Router, orchestrator and the 13 agents |
| `apps/api/app` | 3,967 | Routes, store, auth, middleware, export |
| `services/literature` | 1,346 | arXiv / OpenAlex / Semantic Scholar, merging, coverage |
| `services/patents` | 1,415 | Segmentation, scoring, findings, exports |
| `services/evaluation` | 738 | Golden set, metrics, runner, RAGAS |
| `services/generation` | 668 | Model provider, offline model |
| `services/knowledge_graph` | 548 | Entity extraction, graph store |
| `services/retrieval` | 532 | Vector store, hybrid retrieval, reranker |
| `services/ingestion` | 369 | Extractor, chunker, pipeline |
| `services/common`, `packages` | 551 | JSON helpers, the API contract |
| **Total** | **≈ 13,900** | plus **550 test functions** that guard the behaviour |

The tests matter as much as the code: they are what guarantees the evidence
chain, the quote-or-drop rules, the "field novelty is never assessed"
boundary and the patent wording rules. Every guarantee must have a test on the
new side before the old side is switched off.

## 2. Target architecture

```
 browser ──► Vercel: Next.js website (unchanged)
               │  /api/*  → MAIROS_API_URL = https://mairos-api.<account>.workers.dev
               ▼
 Cloudflare Worker "mairos-api" (TypeScript, Hono router)
   │  short requests: projects, documents, papers, patents, graph, export, health
   │  POST /tasks  → creates a task row, starts a Workflow, returns 202 + task id
   │  GET  /tasks/{id} → status, events and result from Postgres (the UI already polls)
   ▼
 Cloudflare Workflows "mairos-flow" — one durable step per agent, retried per step
   │  each step reads its inputs from Postgres by id and writes its output back
   ├─► Groq (LLM)                 — the existing models, over HTTPS
   ├─► Workers AI (embeddings)    — e.g. @cf/baai/bge-base-en-v1.5
   ├─► arXiv / OpenAlex / Semantic Scholar
   └─► Supabase
         Postgres: projects, documents, chunks + pgvector embeddings, graph
                   nodes/edges, papers, patents, tasks, task events, evaluations
         Storage:  uploaded PDFs (private bucket)
```

Decisions inside it:

| Concern | Choice | Why |
|---|---|---|
| Language | TypeScript Workers | Full Workers support and libraries for every piece below; Python Workers would still need a rewrite of every native dependency |
| HTTP routing | Hono | Small, built for Workers |
| Async jobs | **Workflows**, plus **Queues** only for fan-out such as per-document indexing | Durable steps with retries and per-step CPU budgets; both are on the free plan ([Queues](https://developers.cloudflare.com/changelog/post/2026-02-04-queues-free-plan/), [Workflows](https://developers.cloudflare.com/workflows/reference/pricing/)) |
| Database access | Postgres over **Hyperdrive** (connection pooling to Supabase) | Real SQL and pgvector queries; the existing `0001_mairos.sql` schema is the starting point |
| Vectors | **pgvector** in the `chunks` table | Replaces ChromaDB; hybrid retrieval combines it with Postgres full-text search, then the graph boost |
| Embeddings | **Workers AI** | No key to manage, a free daily allowance, called from the Worker |
| PDF text | **unpdf** (pdf.js built for serverless) | Runs in Workers; ligatures expanded and unreadable / password-protected files refused, as today |
| PDF files | Supabase Storage, private bucket | Kept for exports, as today |
| Knowledge graph | `graph_nodes` / `graph_edges` tables | Replaces NetworkX JSON files; neighbours become SQL |
| Auth | Unchanged design: Better Auth in Next.js issues JWTs; the Worker verifies them against the JWKS with `jose` | Off for the single-user demo, as today |
| Rate limits | Workers rate-limiting binding | Replaces the in-process limiter |
| ZIP export | `fflate` | Streams a ZIP in the Worker |

**The API contract does not change.** Every route, request and response stays
as in `packages/shared-types`, so the website needs no changes beyond the
backend address. Tasks already run "submit, then poll"; on Workers the work
simply moves out of the request into a Workflow.

## 3. Phases

Each phase ends with its tests passing and a working deployment. The PC
backend stays the live one until phase 8.

| Phase | Ports | Exit criteria |
|---|---|---|
| **0. Accounts and decisions** | — | Workers Paid enabled; Supabase project created; Groq key stored as a Worker secret; embedding model chosen (section 5) |
| **1. Foundation** | Schema `0002` (pgvector `chunks`, graph tables, task events, evaluations); Worker skeleton with health, projects CRUD, the task API; a Workflow that runs a trivial flow and records events | `GET /api/health` and project CRUD pass the existing API contract tests (re-run in Vitest against the Worker); a task created by `POST /tasks` reaches `completed` through a Workflow |
| **2. Ingestion** | Upload → Storage → Workflow: extract (unpdf), chunk (port of `chunker.py`), embed, store | Ports of `test_extractor`, `test_chunker`, `test_pipeline`, `test_ingestion`, `test_project_lifecycle`; the sample papers ingest with the same pages and chunk counts as the walkthrough |
| **3. Retrieval and answers** | Hybrid retrieval (pgvector + full text + graph boost), `/query`, `/chat`, synthesis, citations, the empty-project guard | The empty-project and citation tests; walkthrough Part 3 answers cite the right paper and page |
| **4. Agents and flows** | Router, orchestrator as a Workflow, analysis, knowledge graph, comparison, gaps, hypotheses, experiments, novelty, citation, synthesis, the evidence module, the offline model used by tests | Ports of `test_workflows`, `test_novelty`, `test_agents`, `test_review_fixes`; the field-novelty constant and quote-or-drop rules tested on the new side |
| **5. Literature and project review** | Three sources, merging, coverage report, query planning, intake | Ports of `test_literature_sources`, `test_project_flow` against recorded responses (no network in tests, as today) |
| **6. Patents** | Segmentation, scoring, findings, Markdown/CSV export | Port of `test_patents`, including the legal-wording audit and disclaimer surface |
| **7. Evaluation and export** | Golden set, metrics, runner, project ZIP/JSON export | Ports of `test_evaluation`, `test_project_export`; RAGAS stays an optional offline Python script, since it needs Python |
| **8. Cutover** | Point Vercel's `MAIROS_API_URL` at the Worker; retire the tunnel and `publish_demo.py`; update the docs | The whole sample-project walkthrough passes on the live site; retrieval metrics re-measured with the new embedding model and recorded |

**Effort, honestly:** phases 1–3 are about a week of focused work; phases 4–7
are the bulk, about three to four weeks; the cutover a few days. Plan for
**four to six weeks** in total.

## 4. How the guarantees survive the port

1. **Behaviour fixtures first.** Before porting a module, its Python tests are
   run with a recorder that saves inputs and outputs as JSON fixtures. The
   TypeScript tests load the same fixtures, so both sides must agree, not just
   "look right".
2. **One contract.** `packages/shared-types` is turned into a JSON Schema that
   both sides validate against in their tests.
3. **Side-by-side check.** Until cutover, a script runs the walkthrough's API
   steps against the Python backend and the Worker and diffs the structure of
   the results: verdicts, citations, counts.
4. **No test is dropped silently.** A test that cannot be ported, such as
   RAGAS, is listed in this document with the reason.

## 5. Decisions needed from you

| Decision | Options | Recommendation |
|---|---|---|
| Workers plan | Free (10 ms CPU per step) / **Paid, US$5/month** | Paid: ingestion and scoring do not fit in 10 ms |
| Embedding model | Workers AI `bge-base-en-v1.5` (768-d) / `bge-small` (384-d) / another API (Voyage, Jina, OpenAI) | `bge-base`: no extra key, free daily allowance |
| Supabase plan | Free / Pro (US$25/month) | Free to start. **Note:** free projects are paused after a week without activity, which would take the link down; check whether a scheduled Worker ping is enough, or move to Pro before relying on it |
| Upload size cap | 40 MB today / **15 MB** | 15 MB: a Worker has 128 MB of memory for parsing |
| Sign-in | Off (shared demo) / on (Better Auth) | Off until phase 8, then decide |

## 6. Costs

| Service | Plan | Monthly |
|---|---|---|
| Cloudflare Workers | Paid (includes Workflows, Queues, Workers AI allowance) | US$5 |
| Supabase | Free (Pro if pausing is a problem) | US$0 (or US$25) |
| Groq | Free tier, as today | US$0 within its limits |
| Vercel | Hobby, as today | US$0 |

## 7. Until the cutover

The live link keeps depending on the owner's PC and on a network that allows
the Cloudflare tunnel (outbound UDP or TCP 7844 to Cloudflare). On networks
that block it, the site shows "Backend offline".
