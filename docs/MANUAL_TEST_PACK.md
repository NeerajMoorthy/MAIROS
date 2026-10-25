# MAIROS manual test pack

**Test ID:** MAIROS-MANUAL-02 (extends MANUAL-01)  
**Goal:** Manually test project creation, the empty-project evidence guard, uploads, Chat & Q&A, multi-source topic search and its coverage report, all research workflows including **Review my project**, Agent Activity, Tasks, Knowledge Graph, Evaluation, patent awareness, data export, failure handling, and project deletion in one controlled sequence.

**Time:** about 60–90 minutes with a live model. Record each result in the
checklist at the end.

## 0. Pre-flight

Start the API and the web app (see the README, *Run it*), then check:

| # | Step | Expected |
|---|---|---|
| 0.1 | Open <http://localhost:8000/api/health> | `"status": "ok"` and `"llm": {"provider": "groq", "live": true}`. If it says `offline`, the Groq key is not being read — workflows still run, but answers are extractive quotes. |
| 0.2 | Open <http://localhost:3000> | Projects page loads; the sidebar shows **Backend online** and the model name. |
| 0.3 | Note the provider limit | Groq's free tier allows 8,000 tokens per minute. **Wait about 60 seconds between workflow runs**; a run that hits the limit should still complete, with the affected step falling back (see section 9). |

## Test-data files

Use these four PDFs. Upload each as a separate document so Compare Papers can distinguish the sources.

| File | Pages | MAIROS chunks at 512/64 | Use |
| --- | ---: | ---: | --- |
| `output/pdf/mairos-workflow-test-corpus-10-pages.pdf` | 10 | 10 | Controlled corpus for the Evaluation golden set |
| `output/pdf/synthetic-paper-a-grounded-generation.pdf` | 2 | 10 | Grounded generation and citation evidence |
| `output/pdf/synthetic-paper-b-graph-retrieval.pdf` | 2 | 9 | Graph-guided retrieval evidence |
| `output/pdf/synthetic-paper-c-adaptive-chunking.pdf` | 2 | 9 | Section-aware chunking evidence |

The three SYN-A/B/C files are fictional test papers. Their samples, methods, percentages, and metrics are invented and labeled inside each PDF. Use them to test app behavior only; do not cite them as published research. The 10-page corpus was run through MAIROS's PDF extractor and chunker: it produced 10 pages and exactly 10 chunks. Each of the ten shipped evaluation cases has at least one matching corpus chunk under the app's documented `term_match` rule.

The full evaluation cases and expected answers are in `services/evaluation/golden_set.json`. A fuller fixture with page-level evidence is in `docs/fixtures/e2e-rag-evaluation-data.json` (that JSON describes the separate `e2e-rag-evaluation-source.pdf` fixture; do not upload both 10-page PDFs in this run).

## Project setup and empty-project check

1. In the web app, create a new project:
   - **Name:** `MAIROS Full-Feature Manual Test`
   - **Description:** `Controlled test of upload, grounded research workflows, and retrieval evaluation`
2. Before uploading or searching, ask this in **Chat & Q&A**:

   > According to the project's sources, how does retrieval reduce hallucination? Cite the supporting passage.

   **Expected:** No source-grounded answer or citation yet; the app should say that this project has no supporting indexed evidence. If it answers with citations, inspect this new project's document and paper lists. A previous Topic Search, upload, or saved project can supply indexed context even when you did not upload a file in the current moment. A truly new empty project should not silently borrow another project's evidence.
3. Upload only `mairos-workflow-test-corpus-10-pages.pdf` first. Confirm 10 pages and 10 chunks in the upload/workspace details.
4. Run **Evaluation** once before adding the synthetic comparison papers.
   - All 10 golden cases should be supported; unsupported count should be 0.
   - Recall@5, Precision@5, MRR, and nDCG@5 should be in the 0–1 range.
   - Do not expect fixed metric values: ranking depends on the embedder and vector store.
   - Answer-quality scores may be unavailable because this run evaluates retrieval, not generated answers.

## Upload and run the research workflows

Upload SYN-A, SYN-B, and SYN-C separately. Confirm the project now has four documents. After indexing, use each input once in the relevant web feature.

### Chat & Q&A

> According to Synthetic Paper A, what supported-claim rate and citation-entailment rate did retrieve-then-generate achieve? What limitation does the paper identify? Cite the source pages.

**Check for:** 81% supported claims; 74% citation entailment; citation checking under paraphrase is an open question; citations point to SYN-A passages. The answer must keep the figures labeled as synthetic fixture data.

### Topic Search

Search for:

> graph-augmented retrieval for scientific question answering

**Check for:** a clear results/empty-results state, paper metadata and sources for any results, and one corresponding task run. Topic Search can discover and index papers without a manual upload; those papers can later ground Chat answers. Search results depend on network/provider availability, so exact results are not fixed.

Then open the run in **Agent Activity** and check the multi-source search:

| # | Check | Expected |
|---|---|---|
| TS.1 | **What was searched** section | Lists arXiv, OpenAlex and Semantic Scholar, each marked *searched*, *rate limited* or *not reached* — in words, not colour alone. Without `SEMANTIC_SCHOLAR_API_KEY`, Semantic Scholar is usually *rate limited*, with a message naming that setting. |
| TS.2 | Queries | 2–4 queries, each tagged *rules* or *model*. With a live model, all but the first are usually *model*. |
| TS.3 | Counts | "Papers kept *n* of *m*", duplicates merged, a year range and the search date. Kept ≤ 8 by default. |
| TS.4 | Warnings | Any source that did not answer is named. Fewer than 5 papers → a "too few" warning. |
| TS.5 | Scope note | "…not a systematic review. Full texts were not read…" is always shown. |
| TS.6 | Retrieved papers list (Search & Upload tab) | No paper appears twice. Each shows source badges (e.g. *arXiv*, *OpenAlex*) and, where available, venue and year. |
| TS.7 | Paper links | Labels read *View publication*, *View on arXiv*, *View on OpenAlex* or *View on Semantic Scholar*. Hover each: the address is on `doi.org`, `arxiv.org`, `openalex.org` or `semanticscholar.org` only. |
| TS.8 | Activity trace | The literature agent's lines show the queries run, any source that failed, and "Kept *n* of *m* papers … duplicate record(s) merged". |

### Compare Papers

> Compare SYN-A, SYN-B, and SYN-C by research question, method, dataset, reported metric/result, limitation, and open question. Cite every filled cell. Mark any unsupported cell as unavailable; keep the figures labeled as fictional test data.

**Check for these source values:**
- SYN-A: supported claims 62/100 vs 81/100; citation entailment 74/100.
- SYN-B: Recall@5 0.62 vs 0.78; median latency 0.42s vs 0.68s.
- SYN-C: nDCG@5 0.71 vs 0.75; complete evidence 34/60 vs 40/60.

### Detect Research Gaps

> Across SYN-A, SYN-B, and SYN-C, list only limitations or open questions explicitly stated by the papers. Quote the supporting sentence and cite its source. Put any cross-paper idea in a separate section labeled as an inference, not a quoted paper finding.

**Check for:** paraphrased citations under paraphrase (SYN-A); noisy or incomplete graph edges and latency trade-offs (SYN-B); missing headings, tables/equations, and chunk-size selection (SYN-C). Unsupported gap claims should be omitted.

### Generate Hypotheses

> Using only the cited gaps in SYN-A, SYN-B, and SYN-C, propose up to two falsifiable hypotheses. For each, state the gap it addresses, independent variable, dependent variable, predicted direction, and supporting citation. Label cross-paper hypotheses as test ideas derived from these synthetic fixtures.

**Check for:** testable predictions linked to cited gaps, not uncited guesses or claims that a result is already established.

### Design Experiments

> Design a reproducible experiment for this hypothesis: “For multi-hop scientific questions, section-aware chunking combined with one-hop graph expansion improves Recall@5 over dense-only retrieval, at the cost of higher latency.” Specify objective, dataset, baselines, primary metric, secondary metric, ordered procedure, controls, and threats to validity. Cite which fixture gaps motivated each choice and label all fixture data as synthetic.

**Check for:** a defined comparison, dataset, deciding metric, ordered procedure, controls, and threats; each important design choice should trace to evidence or be labeled as a proposed control.

### Check What Is New Here (Novelty)

> Check project-source coverage for this claim: “This project combines section-aware chunking with one-hop concept-graph expansion for multi-hop scientific retrieval.” Cite any matching passages. Report only whether the claim is covered by this project's indexed sources; do not claim field-level novelty.

**Check for:** a project-corpus coverage result and citations (or an explicit not-found result); field novelty remains **not assessed**. “Not found in these sources” must not be presented as proof that the idea is new.

### Literature Review

> Review work on graph-augmented retrieval for scientific question answering. Find and index relevant papers, compare their methods and findings with the sources already in this project, identify cited gaps, and state what is new to this project's collection. Separate retrieved evidence from your synthesis and do not claim field-level novelty.

**Check for:** a chained search/index/retrieve/compare/novelty report with citations. Results vary with the live literature source and network. A project literature review is not a systematic review of the whole field.

### Review my project

Create a **second** project, `Railway Review Test`, so this run's papers do not
mix with the synthetic corpus. In **Workflows → Review my project**:

| # | Step | Expected |
|---|---|---|
| RP.1 | Type `A robot for railway cracks.` | The **Review project** button stays disabled; the hint reads "*n* / 200 characters minimum". |
| RP.2 | Replace it with the description below and click **Review project** | The run starts; a progress panel appears. A live run takes about 1–2 minutes. |

> Low-cost railway track crack detection robot
>
> Manual inspection of railway tracks is slow and expensive, and small cracks are often missed until they cause a failure. We are building a low-cost robot that moves along the rails and detects cracks in railway tracks using a camera and infrared sensors. A GSM module sends an alert with the GPS location of each crack to the maintenance team. We propose a vision-based crack detection pipeline that runs on a microcontroller, so the robot does not need a cloud connection. We will evaluate it on a test track with artificial cracks of known width.

When it finishes, check each section of the result:

| # | Section | Expected |
|---|---|---|
| RP.3 | Pipeline | Agent Activity shows: intake → literature → indexer → knowledge_graph → retriever → comparison → gaps → novelty → citation → synthesis. |
| RP.4 | **Your project, as read** | Title and problem match your text. Methods include camera / infrared sensors / microcontroller. Stated contributions are the robot and the on-microcontroller pipeline. "We will evaluate…" is a **goal**, not a contribution. It says whether the model or rules read it, and how many items were dropped as unsupported. |
| RP.5 | Search keywords | Technical phrases only (e.g. *railway track inspection*, *crack detection*) — no filler such as "slow" or "manual". |
| RP.6 | **What was searched** | As TS.1–TS.5. Kept papers are about railway inspection or crack detection, not generic robotics. |
| RP.7 | Comparison table | Several dimensions across at least two papers; every filled cell has a citation chip that opens the supporting passage. |
| RP.8 | Research gaps | Either quoted gaps with their source sentence, or the note "No gap in these passages could be tied to a quotable sentence…". **Graph signals must not be empty**: expect *under-represented concepts* and/or *uncompared methods* (e.g. Gabor transform vs YOLOv5). |
| RP.9 | Coverage in this project | One entry per stated contribution, labelled "from your project's stated contributions", each with a verdict (*covered* / *partly touched on* / *not found*), a wording-overlap %, the nearest passage with a citation, and the reason field novelty was **not assessed**. |
| RP.10 | Final answer | Starts with "**Your project, as MAIROS read it**", then "**Searched:** …" with any warnings. |
| RP.11 | Overclaim check | Search the whole result (Ctrl+F) for *is novel*, *novel in the field*, *no prior work*, *first to*, *never been done*. **None may appear.** |
| RP.12 | References | One APA reference per kept paper, with a `doi.org` link where a published version exists. |
| RP.13 | Agent Activity, retriever line | Reads "… graph relations used (*n* chunks boosted)" with *n* > 0 once the graph has concepts. |

**Routing check.** In a fresh project, paste the same description into
**Search & Upload → Topic search** (no workflow chosen) and click Search. In
Agent Activity the routing line should read *Routing to 'project' flow (rule)*.
A short question such as `Is my project idea new?` must **not** route to
`project`.

### Patent awareness

| # | Step | Expected |
|---|---|---|
| PA.1 | Open **Patents** for the synthetic-corpus project | The research-support disclaimer is visible before anything else, in every state (loading, empty, results). |
| PA.2 | Add a patent with a title and pasted claim text (e.g. "1. A method for retrieving passages using a knowledge graph… 2. The method of claim 1, wherein…") | Saved; the detail view shows the claims segmented, with claim 2 marked dependent on claim 1. |
| PA.3 | Set its link to `https://example.com/patent` | Rejected with a message listing the allowed public registries. A `patents.google.com` link is accepted. MAIROS never fetches the link. |
| PA.4 | Run the patent workflow | Overlaps are located to a claim, ranked by a score whose components are shown. The wording never says "infringe", "clear to use", "patentable" or "safe". |
| PA.5 | Export Markdown and CSV, open the printable view | Each contains the full disclaimer. |

### Export data

| # | Step | Expected |
|---|---|---|
| EX.1 | Workspace → **Export data** → ZIP, without originals | A ZIP downloads containing `README.txt`, `manifest.json`, `project.json`, `chunks.jsonl`, `chunks.csv`, `graph.json`, `tasks.jsonl`, `evaluation.json`, `patents.json`. |
| EX.2 | Open `manifest.json` | Lists every file with a SHA-256 hash and a count. |
| EX.3 | Export again with **Include original PDFs** | An `originals/` folder holds the uploaded PDFs. |
| EX.4 | Export as JSON | One JSON file with the same content (no originals). |

## Failure handling

| # | Step | Expected |
|---|---|---|
| F.1 | Upload a scanned (image-only) PDF; separately, a text file renamed to `.pdf` | Scanned PDF: HTTP 422 with a message that it looks like a scanned image and OCR is not supported. Renamed file: a readable error. In both cases no document is added. |
| F.2 | Stop the API (Ctrl+C), then use the app | The sidebar reads **Backend offline**; actions show a readable error instead of a blank screen. Restart the API: the project, documents and task history are all still there. |
| F.3 | Run two workflows back to back without waiting | If Groq returns 429, the trace says which step was rate-limited and the run still completes (e.g. references fall back to the built-in APA formatter). |
| F.4 | Turn off Wi-Fi and run a Topic search | All three sources are reported *not reached*; the warning says nothing was searched; the run completes without a crash. |

## Responsive check

At a 375 px wide window (browser dev tools → phone size), open Workspace →
Workflows, a finished run in Agent Activity, and the Patents page. **Expected:**
no horizontal scrolling; the Review-my-project box, coverage report and
comparison table stay readable (the table scrolls inside its own frame).

## Tabs and task-overlap check

- **Tasks:** run history. Submit each prompt once and expect one new run entry per action. Repeating the same question intentionally creates another run; similar titles with different run IDs/timestamps are separate executions, not duplicate pipeline stages. If one submission appears twice with the same run identity, capture that as a UI duplication bug.
- **Agent Activity:** select a run to inspect its ordered agent/stage events, statuses, timestamps, and errors. A stage is part of the selected run; it should not appear as an additional task row.
- **Knowledge Graph:** after successful indexing/analysis, inspect project-scoped paper/concept nodes and edges. It should reflect this project's indexed sources, not establish that a concept is absent from the whole research field.
- **Provider errors:** a `429`/rate-limit event means the configured model provider rejected that request. The run should be visibly failed with a readable error; uploaded and indexed documents should remain. Retry when provider quota is available or use the project's offline mode for deterministic workflow checks.

## Final Evaluation and deletion

1. Run Evaluation again after uploading the three synthetic papers. Confirm all 10 golden cases remain supported and all reported retrieval metrics are within 0–1. Scores may differ from the earlier run because the project corpus changed.
2. In Projects, delete `MAIROS Full-Feature Manual Test` and `Railway Review Test` (and any routing-check project) and confirm each. The test project should disappear. Check that its documents, chunks, graph, papers, and task history are no longer available.

## Automated tests

Run these too; they need no API key and no internet:

```bash
cd mairos && .venv\Scripts\python.exe -m pytest -q
```

```bash
cd mairos\apps\web && npm test
```

**Expected:** 652 backend tests pass (9 Postgres tests skipped) and 144
frontend tests pass.

## Results checklist

Mark each row **Pass**, **Fail** or **N/A**, and note anything unexpected
(a screenshot of failures helps).

| Area | Cases | Result | Notes |
|---|---|---|---|
| Pre-flight | 0.1–0.3 | | |
| Empty-project guard | Setup step 2 | | |
| Upload + Evaluation | Setup steps 3–4 | | |
| Chat & Q&A | SYN-A figures, citations | | |
| Topic Search + coverage | TS.1–TS.8 | | |
| Compare / Gaps / Hypotheses / Experiments | One run each | | |
| Novelty | Field novelty *not assessed* | | |
| Literature review | Chained report | | |
| Review my project | RP.1–RP.13 + routing check | | |
| Patent awareness | PA.1–PA.5 | | |
| Export data | EX.1–EX.4 | | |
| Failure handling | F.1–F.4 | | |
| Responsive | 375 px | | |
| Tasks / Agent Activity / Graph | Tab checks | | |
| Final Evaluation + deletion | Both projects deleted | | |
| Automated tests | Backend + frontend | | |

## What a successful run proves

This test checks that the web app creates and scopes a project, ingests and cites files, routes workflow actions, searches three literature sources and reports the limits of that search, reads a project description into a checkable brief, records agent events, builds a project graph that feeds gaps and retrieval, evaluates retrieval against the included golden set, keeps the patent and novelty boundaries, exports the project, survives failures, and deletes the test projects. It does not validate scientific claims: three comparison papers are fictional test fixtures, the evaluation labels use the app's keyword proxy, and live search results depend on the network and the sources on the day.
