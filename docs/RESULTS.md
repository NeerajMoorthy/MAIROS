# Measured results

This document separates two things that are easy to conflate: what MAIROS has
**proven**, and what it has only **demonstrated**.

- **Proven** — 846 automated tests (695 backend, 151 frontend) that run with
  no API key, no network and no model download, plus 9 Postgres contract tests
  run against a real PostgreSQL 16 server. They assert the system's own
  guarantees: routing decisions, retrieval ranking, evidence linking, the
  drop-what-cannot-be-cited rules, the novelty boundary, the patent boundary
  and disclaimer surface, per-user isolation, restart durability, HTTP
  hardening, WCAG AA contrast, and every API contract.
- **Not yet measured** — output quality under a live language model on a
  realistic corpus. The harness for it exists (`scripts/live_validation.py`);
  the numbers below are marked pending because the run has not been executed.

No number in this file is estimated, extrapolated, or filled in by hand.

---

## 1. What is measured today

### Retrieval quality

Computed live per project by `POST /api/projects/{id}/evaluation/run`, with no
LLM involved, against the ten-case curated golden set in
`services/evaluation/golden_set.json`:

| Metric | Definition |
|---|---|
| Recall@5 | relevant passages in the top 5 ÷ all relevant passages in the corpus |
| Precision@5 | relevant passages in the top 5 ÷ 5 |
| MRR | mean of 1 ÷ rank of the first relevant hit |
| nDCG@5 | log₂-discounted gain ÷ the best achievable ranking |

These are reproducible: the same corpus and the same golden set give the same
numbers every time, because nothing in the path is generative. Run the
evaluation on your own corpus to get figures for it.

### Test coverage

| Suite | Count | Scope |
|---|---|---|
| Backend (`pytest`) | 695 passed, 9 skipped | Agents, flows, retrieval, evaluation maths, API contracts, regressions |
| — of which `test_patents.py` | 62 | Segmentation, scoring, metadata, exports, disclaimer surface, legal-wording audit |
| — of which `test_auth.py` | 15 | JWT verification and per-user isolation |
| — of which `test_database_contract.py` | 13 (+9 Postgres) | One store contract for SQLite and Postgres; the 9 skipped run when `MAIROS_TEST_DATABASE_URL` is set and passed against PostgreSQL 16 |
| — of which `test_literature_sources.py` | 55 | Three-source parsing, link allowlist, de-duplication and ranking, query planning, coverage report, unavailable sources |
| — of which `test_project_flow.py` | 26 | Intake grounding, project routing, the `project` flow end to end |
| — of which `test_review_fixes.py` | 30 | One regression test per finding of the independent review of the literature search and project review |
| — of which `test_sample_project.py` | 17 | The walkthrough's sample files: pages, chunks, titles, the figures answers are checked against, no ligatures, the files that must be refused, the contributions the intake rules read, the patent's claim dependencies |
| — of which `test_project_export.py` | 15 | Project data export: contents, provenance, no truncation, true manifest hashes, originals, isolation |
| — of which `test_project_lifecycle.py` | 8 | Deletion cascade, upload storage, files that are not readable PDFs, empty-project evidence boundary |
| — of which `test_novelty.py` | 65 | The novelty boundary end to end, the `review` chain, routing |
| — of which `test_persistence.py` | 20 | Restart durability, `state.json` migration, concurrency |
| — of which `test_security.py` | 57 | Body caps, rate limits, CORS, request logging, outage handling |
| — of which `test_theme_contrast.py` | 52 | WCAG AA contrast of every theme token, computed from the stylesheet |
| Frontend (`vitest`) | 151 | Every panel's states; the Patents page in every state; axe-core WCAG 2.1 AA; the legal-wording audit over rendered patent output |

`.github/workflows/ci.yml` is set up to run both suites, the type check and the
production build on every push and pull request — but only once the repository
is on GitHub. It was first committed locally on 25 October 2026 and has not
been pushed, so CI has not run yet; every count here comes from local runs.

### Accessibility

Measured, not asserted. axe-core runs the WCAG 2.1 AA ruleset inside the Vitest
suite against the populated result views; `tests/test_theme_contrast.py`
computes every token pair's contrast ratio from `globals.css`; and a Playwright
pass over four routes at 375/768/1440 px found and fixed a 193 px horizontal
overflow on phones, five nav buttons stranded in the tab order behind a
collapsed sidebar, four colour pairs below AA (one at 1.12:1), and six inputs
labelled by placeholder alone. The README's *Accessibility and responsiveness*
section lists each finding against its fix.

---

## 2. What is pending

**Status: not yet run.** The harness is written and tested; the run requires an
environment this project has not yet had access to — a live `GROQ_API_KEY`,
reachable `arxiv.org`, and the ~90 MB embedding model download.

The table below is the shape the results will take. It is intentionally left
empty rather than filled with plausible-looking figures.

| Flow | Status | Seconds | Events | Items produced | Dropped by validation | Citations |
|---|---|---|---|---|---|---|
| `search` | pending | — | — | — | — | — |
| `answer` | pending | — | — | — | — | — |
| `compare` | pending | — | — | — | — | — |
| `gaps` | pending | — | — | — | — | — |
| `hypothesis` | pending | — | — | — | — | — |
| `experiment` | pending | — | — | — | — | — |
| `patent` | pending | — | — | — | — | — |
| `novelty` | pending | — | — | — | — | — |
| `review` | pending | — | — | — | — | — |

Retrieval metrics on a real corpus: **pending**.

**Why it is still pending.** The first attempt, in an earlier sandbox, could not
reach `huggingface.co` or `export.arxiv.org`. The current development machine
(checked 22 October 2026) *does* have outbound access and a configured Groq
key, so that blocker is gone. What is still missing is the corpus: the only
PDFs in the repository are the synthetic fixtures under `output/pdf`, which are
fictional test documents and must not be reported as research results. The run
needs 15–20 real, text-based papers, and it spends the key's quota — so it was
left for the project owner to start rather than run unasked. The harness's own
behaviour is covered by ten tests in `tests/test_live_validation.py`, and it
refuses to record a run against the offline model.

### What the run will answer

1. **Does output quality hold up?** Offline, the workflows produce conservative
   text derived from retrieved passages. The open question is whether a live
   model produces genuinely useful comparisons, gaps and hypotheses — and how
   often its output fails the evidence rules and gets dropped.
2. **How much gets dropped?** The `Dropped by validation` column is the most
   interesting number in the table. A high count means the model is asserting
   things the corpus does not support, and the guard is earning its place.
3. **How slow is it?** The chained flows make several model calls in sequence —
   `experiment` runs retrieval → gaps → hypotheses → design, and `review` runs
   literature → indexing → retrieval → comparison → novelty → synthesis, which
   makes it the longest chain and the one most likely to hit the 300 s poll
   timeout. Latency decides whether these are usable interactively or belong in
   a background queue.
5. **How often does novelty find nothing?** The `novelty` flow's value depends
   on the corpus being large enough for "not found in this project's sources"
   to be informative rather than routine. The harness records the verdict split
   so that can be judged rather than assumed.
4. **Where does it fail?** Rate limits, timeouts, malformed JSON from the model,
   and scanned PDFs are all expected; the harness records each rather than
   aborting.

---

## 3. How to run it

```bash
# 1. Configure a real key
cd mairos && cp .env.example .env     # set GROQ_API_KEY=gsk_...

# 2. Start the backend and confirm the model is live
cd apps/api && uvicorn main:app --port 8000
curl -s localhost:8000/api/health     # expect "live": true

# 3a. Run against a folder of 15-20 text-based PDFs
python scripts/live_validation.py \
    --corpus ~/papers \
    --out docs/results_data.json \
    --markdown docs/results_summary.md

# 3b. Or let the Literature agent build the corpus from a topic search
#     (arXiv, OpenAlex and Semantic Scholar — titles and abstracts only)
python scripts/live_validation.py --topic "retrieval augmented generation"
```

The harness **refuses to run against the offline fallback model** unless
`--allow-offline` is passed. A "live validation" recorded against the
deterministic stand-in would be worse than no numbers at all, so that refusal is
deliberate.

It writes `results_data.json` (machine-readable, every flow's full measurement)
and prints a Markdown summary to paste into section 2 of this file. Replace the
pending table with the generated one, and note the date and model used.

### Choosing the corpus

Use 15–20 text-based PDFs on one topic, with at least two papers that address
the same problem differently — otherwise the `compare` flow has nothing to
contrast and the `gaps` flow has no disagreement to find. Scanned PDFs are
rejected with HTTP 422 by design (no OCR); the harness records them as upload
failures rather than silently skipping them.
