# Roadmap to completion

Current state: **93.75%** — 30 of the 32 required items. 695 backend and 151
frontend tests pass offline (plus 9 Postgres contract tests that pass against
a real PostgreSQL 16 server), TypeScript is clean under `strict`, and both the
production Next.js build and the Cloudflare Worker bundle build.

**Why not 100%.** Every build item is complete and tested. Two items are open.
One is a *measurement*: live-model validation over 15–20 real papers and a
RAGAS run. The harness for both is written and tested; the numbers have not
been taken. The other is a full manual pass of the latest build, which
`docs/SAMPLE_PROJECT_WALKTHROUGH.md` now scripts from start to finish.
Counting the project as finished because the code to measure it exists would
be exactly the overclaim the rest of this system is built to avoid. (The
original Stage B plan sets this rule explicitly: "treat the project as 95%
rather than 100%" until the figures exist. The exact count sits just under
that ceiling.)

---

## Stage A — complete except for one measurement

| # | Work item | Status | Evidence |
|---|---|---|---|
| 1 | Frontend test suite + CI | ✅ Complete | 151 Vitest tests incl. axe-core WCAG 2.1 AA; `.github/workflows/ci.yml` runs pytest, `npm test`, `tsc` and the build |
| 2 | Live-model validation, recorded | ⚠️ **Harness complete, numbers pending** | `scripts/live_validation.py` + 10 tests. See below. |
| 3 | RAGAS wired | ✅ Complete (no live run yet) | `services/evaluation/ragas_runner.py`, labelled model-judged |
| 4 | SQLite persistence | ✅ Complete | `app/db.py`, `app/store.py` |
| 5 | Novelty + literature review | ✅ Complete | `agents/novelty.py`, flows `novelty`, `review` |
| 5a | Multi-source literature search + coverage report | ✅ Complete | `services/literature/` (arXiv, OpenAlex, Semantic Scholar); checked live 23 Oct 2026 against arXiv and OpenAlex — Semantic Scholar answered 429 without a key, and the report said so |
| 5b | Project-description review | ✅ Complete | `agents/intake.py`, flow `project`, **Review my project** workflow |
| 5c | Independent review of 5a and 5b | ✅ Complete | 15 findings, all reproduced and fixed, 30 regression tests in `tests/test_review_fixes.py`; listed in the README |
| 6 | UX hardening | ✅ Complete | Browser audit + axe + computed contrast |
| 7 | Baseline security | ✅ Complete | `app/middleware.py`, `app/errors.py` |

## Stage B — patent awareness, completed

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Claim-level segmentation | ✅ | `services/patents/segmentation.py`; 7 numbering styles, wrapped claims, dependencies, fallback that says so |
| 2 | Weighted, explainable overlap score | ✅ | `services/patents/scoring.py`; rarity × length × section weight, components shown in UI and exports |
| 3 | Patent metadata | ✅ | Schema, store, API (create/PATCH), UI form; date-order and code-shape validation; older records load |
| 4 | Dedicated Patents page | ✅ | `/projects/{id}/patents`: list, detail with segmented claims, findings, run the flow |
| 5 | Export | ✅ | Markdown, CSV, printable view — full disclaimer in each body |
| 6 | Disclaimer surface review | ✅ | Route-enumerating test (fails on a new patent route without it); UI states loading/empty/error/results/print tested |
| 7 | Harder-case tests | ✅ | 62 tests in `tests/test_patents.py` + 17 in the Patents page suite, incl. fabricated model overlaps and the legal-wording audit |
| 8 | Final visual pass | ✅ | Hardcoded colours replaced by theme tokens, shared result views, consistent page headers; 375px overflow measured and fixed |
| 9 | Live-model validation | ⚠️ Pending | As Stage A item 2 |

## Deployment stack (added in this pass, all opt-in)

| Item | Status | Evidence |
|---|---|---|
| Better Auth sign-in + per-user isolation | ✅ Built and tested; not deployed | `tests/test_auth.py` (15 tests, real Ed25519 JWTs) |
| Supabase Postgres store | ✅ Verified against PostgreSQL 16 | `tests/test_database_contract.py` |
| Cloudflare frontend (OpenNext) | ✅ Bundle builds; not deployed | `npm run cf:build` |
| Fly.io API | ✅ Dockerfile + `fly.toml`; not deployed | `docs/DEPLOYMENT.md` |
| Google Analytics | ✅ Page views only, opt-in | `components/Analytics.tsx` |
| Single-user demo: Vercel site, API on the owner's PC via a Cloudflare quick tunnel | ✅ Live since 25 Oct 2026, no sign-in | `docs/LIVE_DEMO.md`, `scripts/publish_demo.py` |

---

## What remains

| Item | What it needs |
|---|---|
| Live-model validation figures | 15–20 real, text-based PDFs on one topic, a live `GROQ_API_KEY`, then `python scripts/live_validation.py --corpus <folder> --out docs/results_data.json --markdown docs/results_summary.md`. Paste the table into section 2 of `docs/RESULTS.md` with date, model and corpus. |
| RAGAS figures | `pip install "ragas>=0.2,<1"`, then one evaluation run with `answer_quality: true` on that corpus. |
| A full manual pass of the latest build | Follow `docs/SAMPLE_PROJECT_WALKTHROUGH.md` on the live demo or locally, and fill in its checklist. |
| A multi-user deployment | Your Supabase, Fly.io and Cloudflare accounts; follow `docs/DEPLOYMENT.md`. The single-user demo is already live (`docs/LIVE_DEMO.md`). |
| CI running for real | The project is a local git repository from 25 October 2026. Push it to a GitHub repository and `.github/workflows/ci.yml` runs both suites, the type check and the build on every push. |
| RAGAS in the project's own environment | RAGAS is installed in the system Python but not in `mairos/.venv`, which the API runs from: `.venv\Scripts\python.exe -m pip install "ragas>=0.2,<1"`. |

## Project-wide data export — built

Approved and implemented as scoped, separately from the patent-findings export:

- `GET /api/projects/{id}/export?format=zip|json&include_originals=true|false`
  (`apps/api/app/export.py`), and **Export data** in the workspace header.
- The ZIP holds `README.txt` (contents, counts, and the caveats generated
  content carries), `manifest.json` (size and SHA-256 per file),
  `project.json`, `chunks.jsonl` + `chunks.csv` (document, page and chunk index
  on every chunk), `graph.json`, `tasks.jsonl`, `evaluation.json` (latest
  report, now persisted per project), `patents.json` (with the full
  disclaimer), and `originals/` only when asked for. JSON is the same data in
  one document, without PDFs.
- Nothing is truncated: the vector store is read without its usual 2,000-row
  cap (a test indexes 2,050 chunks and checks all are exported).
- Owner-only with auth on (same ownership check as every project route); drawn
  from the rate limiter's expensive budget.
- Uploads made before this build have no recorded file↔document mapping, so
  their PDFs export under `originals/unmatched/` with their stored names.
