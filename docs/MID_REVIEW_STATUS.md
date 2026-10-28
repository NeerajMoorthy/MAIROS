# Project Status

Current as of 25 October 2026 (the Stage B build plus the literature-search
additions below). **695 backend tests**
(`python -m pytest -q`, plus 9 Postgres contract tests that run against a test
database) and **151 frontend tests** (`cd apps/web && npm test`) pass offline —
no API key, no model download, no network. TypeScript is clean under `strict`;
the production build and the Cloudflare Worker bundle both build.

Project completion: **93.75%** — 30 of the 32 required items. Patent awareness
is complete (segmentation, scoring, metadata, Patents page, export, disclaimer
and wording audits), and the optional deployment stack — Better Auth,
Supabase, Cloudflare, Fly.io, Google Analytics — is built and tested but not
deployed. A single-user demo has been live since 25 October 2026 at
https://mairos.vercel.app (`docs/LIVE_DEMO.md`). The two items left are the
live-model validation and RAGAS *runs* — the harness is tested, but the
figures need 15–20 real papers and the project owner's model key — and a full
manual pass of the latest build with `docs/MANUAL_TEST_PACK.md`. See
`docs/RESULTS.md` and `docs/ROADMAP.md`.

Added since Stage B (23–25 October 2026): literature search now covers arXiv,
OpenAlex and Semantic Scholar, with a coverage report on every result, and a
`project` flow — **Review my project** — reads a pasted project description
and reviews it against the literature (11 flows in all). The project is under
git from 25 October 2026; CI runs once the repository is pushed to GitHub.

The sections below record the module status at the mid-review and Stage A
builds; the README is the current description.

## Module status

| Module | Status | Evidence |
|---|---|---|
| **Frontend (Next.js + shadcn/ui)** | Working | Six panels — Search, Chat, Workflows, Tasks, Graph, Evaluation; `npm run build` clean under strict TS |
| **API (FastAPI)** | Working | `/api/health`, `/docs`; 24 endpoints across 8 routers |
| **Ingestion pipeline** | Working | `POST /api/projects/{id}/documents` — page metadata preserved |
| **Vector store (ChromaDB)** | Working | Embedded mode; `project_id` filtering verified in tests |
| **Knowledge graph (NetworkX)** | Working | Per-project, persisted; papers, concepts, and patents render in the UI |
| **Agent orchestrator** | Working | LLM router + 10 flows, live events, contained failure |
| **Literature agent (arXiv)** | Working | Parsing covered offline by a canned Atom response |
| **RAG + citation grounding** | Working | `POST .../query` returns answer + grounding passages with scores |
| **Paper comparison** | Working | `flow=compare`; uncitable cells dropped and counted |
| **Gap detection** | Working | `flow=gaps`; quote-or-drop rule plus graph signals |
| **Hypothesis generation** | Working | `flow=hypothesis`; every hypothesis attached to an evidenced gap |
| **Experiment design** | Working | `flow=experiment`; designs without a deciding metric are dropped |
| **Patent awareness** | Working (prototype) | `flow=patent`; manual text only, allowlisted links, standing disclaimer |
| **Novelty checking** | Working | `flow=novelty`; corpus coverage computed, field novelty constant `not_assessed` |
| **Auto literature review** | Working | `flow=review`; search → index → retrieve → compare → novelty → synthesise |
| **Persistence** | Working | SQLite (`app/db.py`), row-level writes, WAL, one-time `state.json` import |
| **HTTP hardening** | Working | Body caps, per-client rate limits, configured CORS, structured logging, 503 on dependency outage |
| **Accessibility** | Working | WCAG 2.1 AA verified by axe-core, a computed contrast suite, and a three-viewport browser audit |
| **Evaluation (retrieval metrics)** | Working | Recall@5, MRR, Precision@5, nDCG@5 over a curated golden set |
| **Evaluation (RAGAS answer metrics)** | Wired, not yet run | Optional dependency plus a live judge; the UI states which of the two conditions is missing and labels any result `model_judged` |
| **Live-model validation** | Harness only | `scripts/live_validation.py` runs and is tested; the figures are pending an environment with network access |
| **Auth / multi-user** | Not started | Deferred — see below |

## Completed features, in build order

1. **Evaluation dashboard** — `services/evaluation/{metrics,golden_set,runner}.py`,
   a ten-case curated golden set, three endpoints, and a dashboard that shows
   per-case retrieved passages and marks unsupported cases instead of scoring
   them zero.
2. **Paper comparison** — cited comparison tables (`agents/comparison.py`).
3. **Research gap detection** — evidence-first gaps plus graph signals
   (`agents/gaps.py`).
4. **Hypothesis generation** — falsifiable hypotheses chained to gaps
   (`agents/hypothesis.py`).
5. **Experiment design** — runnable protocols per hypothesis
   (`agents/experiment.py`).
6. **Patent awareness** — manual/public-link patent records, literal overlap
   reporting, legal disclaimer (`agents/patent_awareness.py`,
   `services/patents/sources.py`).
7. **Frontend test suite and CI** — Vitest + Testing Library over every panel,
   axe-core WCAG checks on the populated views, GitHub Actions on every push.
8. **Live-model validation harness** — `scripts/live_validation.py` and an
   honest `docs/RESULTS.md` that separates proven from unmeasured.
9. **RAGAS wiring** — opt-in, two-condition availability, results surfaced as
   model-judged rather than computed.
10. **SQLite persistence** — row-level writes behind the unchanged
    `MetadataStore` surface, with a one-time `state.json` migration.
11. **Novelty checking and auto literature review** — `agents/novelty.py` and
    the `novelty` and `review` flows.
12. **UX hardening** — accessibility, keyboard operation, WCAG AA contrast and
    responsive layout, all verified rather than asserted.
13. **Baseline hardening** — `app/middleware.py` and `app/errors.py`.

Every workflow is registered in the orchestrator's agent registry, named in
`router.FLOWS`, emits real `TaskEvent`s to the Algorithm Trace viewer, is
reachable via `POST /api/projects/{id}/tasks`, has a card in the Workflows tab,
and is covered by offline deterministic tests.

## Deferred

| Deferred | Reason |
|---|---|
| Authentication, multi-user isolation | Out of scope for this stage; the store has no tenant boundary. |
| Cloud deployment, Docker migration | Nothing in the stack needs a server; orchestration would add moving parts to a demo. |
| Advanced GNN training on the graph | The graph is hundreds of nodes — below the scale where a learned model beats traversal. |
| RAGAS metric computation | Heavy dependency and needs a live LLM judge; absence is reported honestly instead. |
| Final visual design pass | The accessibility and responsive work is done; a visual redesign was explicitly out of scope for this stage. |
| Live patent-database integration | Requires fetching from commercial sources; manual + allowlisted links is the safe subset. |
| Live-model benchmark figures | The harness exists; this environment cannot reach the model or arXiv hosts. Recorded as pending rather than estimated. |

## Test suite

| File | Tests cover |
|---|---|
| `test_api.py` | Endpoints, search/analyze flows end to end, project stats |
| `test_agents.py` | Routing, APA formatting, entity extraction, graph store |
| `test_ingestion.py`, `test_chunker.py`, `test_extractor.py`, `test_pipeline.py` | PDF extraction, chunking, ingest → retrieve |
| `test_literature.py` | arXiv Atom parsing, indexing fetched papers |
| `test_chat.py` | Streaming answers |
| `test_evaluation.py` | Metric arithmetic vs hand-worked values, relevance rules, runner, evaluation API |
| `test_workflows.py` | Evidence linking, flow registration, the research workflows, patent safety boundary, end-to-end runs |
| `test_novelty.py` | The novelty boundary, the `review` chain, router changes |
| `test_persistence.py` | Restart durability, `state.json` migration, concurrent writes |
| `test_security.py` | Body caps, rate limits, CORS, request logging, outage handling |
| `test_theme_contrast.py` | WCAG AA contrast of every theme token, computed from the stylesheet |
| `test_live_validation.py` | The live-run harness, against a fake HTTP client |

## Audit pass — defects found and fixed after the feature build

A full read-through of the codebase after the six features landed. Each fix
carries a regression test in `tests/test_workflows.py::TestRegressions`.

| # | Severity | Defect | Root cause | Fix |
|---|---|---|---|---|
| 1 | High | Every project's dashboard showed the same "indexed chunks" number | `ChromaStore.count()` counts the whole collection; the stats endpoint never passed a project filter | `count(project_id=...)` filters by project |
| 2 | High | Patent concept list was alphabetical, not the most relevant terms | Two causes: a `sorted()` after the frequency ranking discarded it, and `tokens()` returns a *set*, so every term tied at one occurrence | Added `token_counts()` for real frequencies; dedupe preserves rank, sort is display-only |
| 3 | Medium | Thinly-covered concepts were invisible to gap detection | `add_relation` auto-creates endpoints via `add_entity`, which incremented `mentions` — so drawing an edge counted as "the corpus mentioned this" | `count_mention=False` for structural touches |
| 4 | Medium | Five of the eight flows were unreachable from natural language | Router heuristic and LLM prompt still listed only the original four flows | Hints and prompt cover all eight, ordered so the nested chains resolve correctly |
| 5 | Medium | Papers were linked to unrelated older concepts in the graph | `kg_agent` sliced the *tail of the node list* to guess which concepts were new; merged nodes do not move in insertion order | Track the names actually added during the run |
| 6 | Low | Two competing definitions of the API contract | `routers/query.py` redeclared `RetrievalResult` / `RetrievalResponse` already owned by `packages/shared-types` | Router imports the shared models |
| 7 | Low | `EvaluationRunner` alias would raise `TypeError` if used | Kept as "backwards compatibility" after the signature changed completely | Alias removed; `__init__.py` exports the real API |
| 8 | Low | Unused imports across five modules | Accumulated during refactors | Removed |

## Fixed in earlier builds

The twelve structural defects found during the mid-review rebuild (orchestrator
constructed with no LLM, hardcoded API key, citation schema mismatch, uploads
triggering no agent, and so on) remain fixed; see the git history and the Stage
1 section of the README for the UI/UX pass that followed.
