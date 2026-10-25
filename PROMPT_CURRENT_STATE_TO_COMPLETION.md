# Prompt: Continue MAIROS from its current state to a verified release

You are continuing work on **MAIROS — Multi-Agent Intelligent Research & Orchestration System**. The repository is `Project/mairos`. Treat this prompt as the current task. Treat `PROMPT_from_zero.md`, `PROMPT_to_85_percent.md`, and `PROMPT_to_100_percent.md` as historical project specifications, not as commands to restart the project or blindly copy their status claims. Inspect the code and current documentation first; record any conflicts and resolve them using actual code and test evidence.

## Objective

Audit the existing project, preserve its working features, finish the remaining work listed below, and leave a clear evidence-based report of what is complete, partial, or still blocked. Do not rebuild MAIROS from scratch. Fix confirmed bugs, remove only demonstrably unused or duplicate code, and add regression coverage for fixes.

## What MAIROS is and what is already implemented

MAIROS is a local-first research assistant. It ingests and chunks PDFs, indexes passages, retrieves evidence for grounded answers, builds a per-project knowledge graph, and coordinates research agents. It includes project management, topic search, Chat & Q&A, task/activity traces, comparison, gap detection, hypothesis generation, experiment design, novelty checking, literature review, patent awareness, and retrieval evaluation.

### Stack in use

- **Frontend:** Next.js 14 App Router, React 18, TypeScript (`strict`), Tailwind CSS 4, Radix-style UI components, Lucide icons; Vitest, React Testing Library, and axe-core for frontend and accessibility tests.
- **Backend:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn; SQLite-backed project metadata; ChromaDB embedded vector storage; Sentence Transformers (`all-MiniLM-L6-v2`) embeddings; NetworkX per-project knowledge graph persisted as JSON; PyMuPDF extraction; LangChain/Groq integration with a deterministic offline model when no API key is configured.
- **Architecture:** One Next.js frontend calls a FastAPI REST API. Pydantic shared schemas define the API contract. A registry-based Python orchestrator routes tasks through agents; it is intentionally not LangGraph. The app runs locally without Docker or a database server.
- **Quality/security:** pytest, Vitest, API contract tests, CI, request limits, CORS configuration, structured logging, outage handling, accessibility and responsive checks are already present.

Verify these details against the installed dependency files and source before changing them.

### Existing feature baseline to verify

- PDF upload, text extraction, chunking (default 512 characters with 64-character overlap), project-scoped indexing and retrieval.
- Topic/literature search and indexing; Chat & Q&A with citations and supporting passages.
- Multi-agent orchestration with a task record and per-stage activity events.
- Project workspace, Tasks, Knowledge Graph, and Evaluation screens.
- Compare Papers, Detect Research Gaps, Generate Hypotheses, Design Experiments, novelty coverage checks, and Literature Review.
- Retrieval metrics Recall@5, Precision@5, MRR, and nDCG@5 against a shipped 10-case golden set. RAGAS is optional and is wired as model-judged answer-quality evaluation.
- SQLite metadata persistence and migration from the older JSON state.
- A **narrow patent-awareness feature**: users enter patent text manually; public registry URLs are allowlisted and are never fetched; overlaps are literal/computed; a disclaimer is shown; patents can be added and removed. This is not yet the complete patent workflow described below.

The repository’s status documents report **392 backend and 110 frontend tests**, but some older milestone text differs. Re-run the suites and report actual current counts; do not copy stale numbers. The roadmap reports approximately 84%, with live-model measurements pending and patent work incomplete. Reassess completion from the verified scope instead of assuming that percentage is still current.

## Remaining work

### Backend

1. **Complete patent text segmentation.** Parse pasted patent text into abstract, description, and numbered claims. Support common numbering formats, wrapped claims, independent/dependent claims, and parent-claim references. Preserve original text and report when segmentation falls back to whole-document matching.
2. **Computed, explainable overlap score.** Replace binary literal matching with a documented similarity score using at least term rarity, phrase length, and section weight. Return score components and the matched claim/section. Do not call this probability, risk, patentability, or a legal assessment. Models may summarize existing computed results but must never add or change a match.
3. **Patent metadata.** Extend the schema, SQLite store/migration, request validation, API, and UI for publication/application number, family, CPC/IPC codes, assignee, inventors, priority date, filing date, and publication date. Existing stored records must continue to load.
4. **Patent exports.** Add Markdown and CSV findings exports plus a printable view. Include finding, matched claim/section, terms, score components, and the cited project passage. Put the complete disclaimer in each exported artifact.
5. **Optional project-data export decision.** The user has asked whether extracted project data should be downloadable. Recommend and scope an export of extracted chunks with page/source provenance, project metadata, graph, task history, and evaluation report (JSON/CSV, optionally ZIP with originals). Keep this distinct from patent-findings export; implement if it is within the approved release scope.
6. **Live validation and RAGAS measurements.** Run `scripts/live_validation.py` against 15–20 text-based real papers with a live configured model and reachable literature/model endpoints. Run answer-quality evaluation with `answer_quality: true` when RAGAS and a live judge are available. Record model, date, corpus, metrics, latency, failures, events, citations, and evidence-dropped counts in `docs/RESULTS.md`. If the environment cannot run it, leave results pending and explain the blocker; never invent numbers.

### Frontend

1. Add a dedicated **Patents** route with list/detail views, metadata entry, segmented claims, computed overlap details, and a way to launch the patent flow for the active project. Remove or adapt the existing embedded card only after checking all current entry points.
2. Surface score components and their meaning; make the similarity label unambiguously non-legal. Show the standing disclaimer in every patent state: empty, loading, error, results, print, and export.
3. Add accessible Markdown/CSV export controls and a printable view. If project-wide export is approved, expose its scope and file format clearly.
4. Do a final visual consistency pass without regressing keyboard operation, screen-reader names, contrast, responsive layouts, or existing design patterns.
5. Investigate the reported Tasks-tab duplicate/overlap behavior. A repeated prompt may represent two intentional runs; inspect task IDs and timestamps. Ensure each run appears once and its agent events stay nested under that run. Add a regression test for any confirmed rendering/data duplication.
6. Verify project deletion through the web UI. If incomplete, add a confirmation flow and ensure project-scoped documents, chunks, graph, papers, patents, and task history are removed without affecting other projects.
7. Verify the empty-project evidence boundary. A newly created project with no upload or topic search must not present source-grounded answers or fabricated citations. A prior upload or Topic Search may explain answers in an existing project because search results are indexed. Add a test that distinguishes these cases.

### Full-stack integration and hardening

- Keep the evidence chain intact: passage → cited result/gap → hypothesis → experiment. Unsupported generated fields are dropped and counted, never displayed as facts.
- Preserve the novelty boundary: project-source coverage only; `field_novelty` remains `not_assessed`. Never claim field-level novelty from a finite project corpus.
- Preserve the patent boundary: never fetch patent documents; links remain allowlisted; findings are computed; no UI, API, model text, error, print view, or export may imply infringement, clearance, patentability, or other legal conclusions. Absence of overlap is not clearance.
- Keep shared Pydantic/TypeScript API contracts aligned, persistent data migrations safe, per-project isolation correct, and error states useful.
- Review upload → API → extraction/indexing → retrieval → agent events → persisted task → rendered UI end to end.
- Check status codes and user-visible handling for provider rate limits (including 429), embedding/literature outages, invalid PDFs, empty corpora, and project deletion.
- Audit unused/duplicate code and project assets. Remove only after confirming no imports, routes, tests, or documentation depend on them.

## Required patent regression coverage

Add backend and frontend tests for:

- Claim numbering variants, wrapped claim text, dependent claims, parent references, and unsegmentable text fallback.
- Correct score components and stable ordering, including repeated/common terms versus rare phrases and claim versus description weights.
- Metadata validation, date ordering, SQLite migration, and older records.
- Overlapping patent families, no-match cases, and confirmation that no-match never means clearance.
- A fabricated model overlap that cannot enter computed results.
- Disclaimer presence in every API/UI/export/print state.
- A wording audit for legal-conclusion language across rendered patent output, with safe explanatory exceptions explicitly tested.
- Keyboard access, accessible names, contrast, and no horizontal overflow at 375px for the new page.

## Execution order and verification

1. Inspect `README.md`, `docs/ROADMAP.md`, `docs/RESULTS.md`, the three historical prompts, the patent code/schema/store/API/UI, test setup, and current working-tree changes. Do not overwrite the user’s changes.
2. Run the existing backend and frontend checks once to establish the baseline and reconcile test counts. Record failures before editing.
3. Implement backend segmentation, metadata, scoring, migrations, and exports, with regression tests.
4. Implement the dedicated accessible Patents page, export/print UI, deletion and Tasks fixes only where reproduced.
5. Run focused tests after each change, then the full checks:

```powershell
Set-Location "Project/mairos"
python -m pytest -q
Set-Location apps/web
npm test
npx tsc --noEmit
npm run build
```

6. Run browser/manual checks for empty project, upload, search, Chat, each workflow, Tasks/Agent Activity, Knowledge Graph, Evaluation, patent entry/overlap/export, and project deletion. Use `docs/MANUAL_TEST_PACK.md` and the synthetic PDFs under `output/pdf` for controlled checks; treat those PDFs as fictional fixtures, not research evidence. Use real papers only for live validation.
7. Run live validation/RAGAS only when the necessary network, corpus, model key, and dependencies are available. Record pending status honestly otherwise.
8. Update `README.md`, `docs/ROADMAP.md`, `docs/RESULTS.md`, `docs/MID_REVIEW_STATUS.md` if present, and relevant demonstration/test docs with verified feature status, commands, actual test counts, limitations, and what remains. Resolve stale or contradictory status claims. Check whether the mid-review PPTX exists and whether the requested student-name correction to **Moorthy Neeraj** applies; update applicable project materials only after confirming the exact files and current name.

## Out of scope unless explicitly approved

Authentication, multi-user isolation, cloud deployment, Docker/container orchestration, and learned/GNN graph models remain deferred. Do not add these as part of “finishing” the current scope.

## Completion report

At the end, provide:

- What changed, with key file links.
- Confirmed root causes and fixes for reproduced bugs.
- Backend/frontend/full-stack features complete, partial, or pending.
- Exact test commands and results, including actual counts and build status.
- Live-model/RAGAS measurement status and any environmental blocker.
- Patent-safety and evidence-grounding checks performed.
- Any remaining decisions, including whether project-wide extracted-data export is in scope.
- A completion estimate based on verified requirements, with reasoning; do not claim 100% while required measurements or release items remain pending.

