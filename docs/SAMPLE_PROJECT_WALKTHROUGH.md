# Sample-project walkthrough: RailGuard Lite, start to finish

**Test ID:** MAIROS-WALKTHROUGH-01
**What it is:** one sample project, followed through every feature of MAIROS:
create it, upload its papers, ask questions, run every research workflow,
search the web for related work, review the project description, add a
patent, inspect the graph and the run history, evaluate, export, test the
error handling, and delete it. Every file you need is provided, every piece of
text you need to type is given below, and every step says what you should see.

**Time:** 60–75 minutes with the live model. Mark each step in the
[results checklist](#results-checklist) as you go.

**Where:** on the live demo, **https://mairos.vercel.app**, or on your own
machine at http://localhost:3000 (README, *Run it*). The steps are the same.

> **Before you start**
>
> - **The sample papers are fictional.** Their authors, data and results are
>   invented so that every step has a known right answer. Use them only to
>   test MAIROS, never as sources.
> - **The live demo has no sign-in.** Anyone with the link can see the test
>   project while it exists. Use only the sample files, and delete the
>   project at the end (Part 12).
> - **Live model or offline.** The expectations are written for the live
>   model (Groq). Where the offline stand-in behaves differently, the step
>   says so. The sidebar shows which one is running.
> - **Groq's free tier allows about 8,000 tokens a minute.** Wait about a
>   minute between workflow runs. A run that hits the limit still finishes,
>   with the affected step falling back.
> - **Fixed issues.** Four defects turned up while this walkthrough was being
>   prepared and were fixed the same day ([list](#fixed-issues)). The steps
>   below describe the fixed behaviour; if the old behaviour comes back, mark
>   the step **Fail**.

## The files

All in `mairos/output/sample-project/`. To recreate them:
`.venv\Scripts\python scripts\generate_sample_project.py`.

They are also in the app: **Settings → Sample files** downloads each one, and
**Settings → Load example data** creates the project *RailGuard Lite
(example)* with the three papers already indexed and the patent stored, plus a
*Try every feature* list with an input for each feature. That is the quick way
to look around; this walkthrough still starts from an empty project so that
the upload steps are tested too. **Settings → Clear workspace** deletes every
project after a confirmation.

| File | What it is | Used in |
|---|---|---|
| `paper-a-camera-cnn.pdf` | *Lightweight CNN Crack Detection on Rail Heads*: camera images and a small neural network on a single-board computer. 2 pages. | Part 2 onwards |
| `paper-b-ultrasonic-guided-waves.pdf` | *Ultrasonic Guided Waves for Rail Weld Flaws*: ultrasonic inspection of rail welds. 2 pages. | Part 2 onwards |
| `paper-c-vibration-alerts.pdf` | *Vibration Monitoring and GPS Alerts for Track Defects*: accelerometers, plus alerts sent over GSM with a GPS position. 2 pages. | Part 2 onwards |
| `project-description.txt` | The RailGuard Lite project description: a camera-and-infrared crack-detection robot with GSM alerts. | Part 5 |
| `patent-sample.txt` | A fictional patent: a rail inspection trolley with a camera and vibration sensing, 4 claims. | Part 6 |
| `scanned-page.pdf` | An image-only page, like a scan. It has no text to extract. | Part 10 |
| `broken-file.pdf` | A text file renamed to `.pdf`. | Part 10 |

What the papers say, so you can check answers against them:

| | Paper A: camera + CNN | Paper B: ultrasonic guided waves | Paper C: vibration + GPS alerts |
|---|---|---|---|
| Page 1 | CNN with 1.2 million parameters on a Raspberry Pi 4 at 14 frames/s; 2,400 images, 600 with cracks | 50 kHz guided waves locate a flaw to within 15 cm; 120 welds, 40 with flaws | Accelerometers at 2 kHz; 0.5 s windows; a GSM module texts each alert with its GPS position; 6 km track, 46 defects |
| Results (page 2) | Recall 0.91, precision 0.88 in daylight; recall 0.64 at dusk; cracks under 0.5 mm found in 22% of cases | 38 of 40 flawed welds found (95%), 3 false alarms; 1 km inspected in about 40 minutes; 7 of 12 shallow flaws missed | 40 of 46 defects flagged (87%); about one false alarm every 3 km; 9 s median alert delay; weak GSM coverage delayed 12% of alerts by over a minute |
| Limitation (page 2) | All training images were taken in daylight | Transducers need direct contact and a gel couplant, which slows inspection | Only one 6 km test track was used |
| Open question (page 2) | Can infrared illumination restore recall at night? | Can guided-wave results be combined with camera images? | How to fuse vibration alerts with visual confirmation |

---

## Part 0 — Pre-flight

| # | Do this | Expected |
|---|---|---|
| 0.1 | Open the site. | The Projects page loads. The sidebar shows **Backend online** and the model. On the live demo the model is `openai/gpt-oss-120b`; offline, the header reads **Running in offline LLM mode**. |
| 0.2 | Open `/api/health` on the same site (for example https://mairos.vercel.app/api/health). | `"status": "ok"`. With the live model: `"live": true`. |
| 0.3 | If the sidebar says **Backend offline** on the live demo | The API on the owner's PC is not running. Start it with `.venv\Scripts\python scripts\publish_demo.py` ([LIVE_DEMO.md](LIVE_DEMO.md)) and reload. |

## Part 1 — Create the project

| # | Do this | Expected |
|---|---|---|
| 1.1 | **Projects → New Project**. Name: `RailGuard Lite - Track Crack Detection`. Description: `Sample project for a manual test of MAIROS: railway crack detection, from upload to export.` Click **Create project**. | The workspace opens with the name and description at the top. Every counter is 0. |
| 1.2 | **Chat & Q&A**, ask: `What recall did the lightweight CNN reach in daylight?` | *"I cannot answer this based on the provided documents — nothing in this project matched the question. Upload a PDF or run a topic search first."* No citations. A new project must not borrow evidence from another project. |

## Part 2 — Upload the three papers

| # | Do this | Expected |
|---|---|---|
| 2.1 | **Search & Upload → Upload a PDF**, choose `paper-a-camera-cnn.pdf`. | *Uploaded "paper-a-camera-cnn.pdf" — 2 pages, 4 chunks indexed.* An analysis run starts and its progress appears below the upload box. |
| 2.2 | Upload `paper-b-ultrasonic-guided-waves.pdf`, then `paper-c-vibration-alerts.pdf`, one at a time. | Each: 2 pages, 4 chunks indexed. |
| 2.3 | Wait until the three analysis runs finish (about 10–40 s each live), then read the counters at the top. | Documents uploaded **3**, Indexed chunks **12**, Graph nodes / edges above 0, Tasks completed **3**. |
| 2.4 | **Agent Activity**: open one analysis run. | The steps in order — loader → analysis → knowledge graph → citation — each with a status and time. Live: a summary of that paper's contributions and method. *Offline: the summary only repeats the paper's first lines.* |

## Part 3 — Ask questions (Chat & Q&A)

Each question runs the `answer` flow — retriever, synthesis and citation agents — and appears in
**Agent Activity** like any workflow. Every answer must cite the paper and page it came from. Click a citation to
see the passage.

| # | Ask | Expected |
|---|---|---|
| 3.1 | `What recall and precision did the lightweight CNN reach in daylight, and what happened at dusk?` | Recall **0.91** and precision **0.88** in daylight; recall fell to **0.64** on 300 images taken at dusk. Cites paper A, page 2. |
| 3.2 | `How long did the ultrasonic crew take to inspect 1 km of track?` | About **40 minutes**. Cites paper B, page 2. |
| 3.3 | `Which paper sends GPS alerts, and what share of alerts did weak GSM coverage delay?` | Paper C (*Vibration Monitoring and GPS Alerts for Track Defects*): **12%** of alerts were delayed by more than a minute. Cites paper C, page 2 (and page 1 for the GSM module). |
| 3.4 | `What does this project's corpus say about drone-based track inspection?` | Live: says the indexed papers do not cover drone-based inspection. **It must not invent drone results.** *Offline: lists the closest passages, none of them about drones.* |

## Part 4 — Research workflows on the three papers

Open **Workflows**. Each card has a box for an optional focus and a **Run**
button; an empty box uses the card's default question. Results appear in the
**Run progress** panel below the cards. Wait about a minute between runs.

| # | Do this | Expected |
|---|---|---|
| 4.1 | **Compare papers**: leave the box empty, click **Run**. | A table across the three papers. Every filled cell has a citation chip (paper and page), and the values match the papers: A 0.91 / 0.88 and 0.64 at dusk; B 38 of 40 (95%) and about 40 minutes per km; C 40 of 46 (87%), 9 s alert delay, GSM text with GPS position. Cells with no supporting passage are left out and counted. *Offline: three rows — Focus of the work, Approach described, Reported outcome — and nine cells.* |
| 4.2 | **Detect research gaps**: leave the box empty, click **Run**. | Gaps quoted from the papers, each with its source sentence, paper and page 2. Expect at least two of: A — *"A limitation of this study is that all training images were captured in daylight…"* or *"It remains unclear whether infrared illumination can restore recall at night."*; B — *"The main limitation is that the transducers need direct contact with the rail and a gel couplant…"* or *"Future work should test whether guided-wave results can be combined with camera images…"*; C — *"A limitation of this study is that it used a single 6 km test track…"* or *"An open problem is how to fuse vibration alerts with visual confirmation…"*. Below them, **structural signals from the knowledge graph** (for example under-represented concepts). No gap appears without a quote. |
| 4.3 | Optional: run **Detect research gaps** again with `Limitations of the camera, ultrasonic and vibration methods`. | A different selection of the same quoted sentences. The step reads the five passages closest to the question, so the wording decides which papers appear. |
| 4.4 | **Generate hypotheses**: leave the box empty, click **Run**. | One hypothesis per gap, each marked *from GAPn* and carrying that gap's citation. Live: testable statements, such as night-time recall with infrared illumination. *Offline: each hypothesis restates its gap, sometimes cut off mid-sentence.* The answer text checks **each hypothesis** against the project's sources: a verdict and a wording overlap per hypothesis, marked *from a generated hypothesis*. Your question itself must never appear as a checked claim (fixed issue K1). |
| 4.5 | **Design experiments**: type `Budget: one 500 m test track, two weeks, no cloud computing.` and click **Run**. | One design per hypothesis, each with objective, datasets, baselines, metrics, an ordered procedure, controls and threats to validity. A design without a deciding metric is dropped. Live: the designs respect the budget. *Offline: generic placeholders such as "The dataset used by the cited baseline".* |
| 4.6 | **Check what is new here**: type `A lightweight CNN running on a single-board computer detects rail-head cracks from camera images.` and click **Run**. | **Already covered by this project's sources**, about **92%** wording overlap. The nearest passage is from paper A, page 1. Field novelty: *not assessed*, with the reason. |
| 4.7 | **Check what is new here** again: `Drone-mounted LiDAR maps ballast erosion along the track.` | **Not found in this project's sources**, about **25%** overlap, with the explanation that this means MAIROS found nothing, not that nothing exists. |
| 4.8 | Overclaim check: press Ctrl+F on the results of 4.6 and 4.7 and search for *is novel*, *first to*, *no prior work*, *never been done*. | None of them appear. |

## Part 5 — Related work from the web

These steps search arXiv, OpenAlex and Semantic Scholar, so the papers you get
depend on the day. Check the structure, not particular titles. They add
papers to the project, which is why they come after Part 4.

| # | Do this | Expected |
|---|---|---|
| 5.1 | **Search & Upload → Topic search**: `railway track crack detection deep learning`, click **Search**. | A *Retrieved papers* list with no title twice. Each paper shows source badges (*arXiv*, *OpenAlex*, *Semantic Scholar*) and, where known, venue and year. Links are labelled *View publication*, *View on arXiv*, *View on OpenAlex* or *View on Semantic Scholar*. Hover each one: the address is on `doi.org`, `arxiv.org`, `openalex.org` or `semanticscholar.org` only. |
| 5.2 | **Agent Activity**: select the search run and read its **What was searched** section. | Each source is named with its status in words: *searched*, *rate limited* or *not reached*. Without a `SEMANTIC_SCHOLAR_API_KEY`, Semantic Scholar is usually *rate limited*, with a message naming that setting. The section also shows the queries, "papers kept *n* of *m*" (8 at most), the year range, the date, and the note that this is not a systematic review and full texts were not read. |
| 5.3 | **Workflows → Review my project**: type `A robot for railway cracks.` | **Review project** stays disabled; the hint reads "*n* / 200 characters minimum". |
| 5.4 | Replace it with the whole of `project-description.txt` and click **Review project**. | The run takes 1–2 minutes live. The progress panel shows intake → literature → indexer → knowledge graph → retriever → comparison → gaps → novelty → citation → synthesis. |
| 5.5 | **Your project, as read**. | Title: *RailGuard Lite: a low-cost railway track crack detection robot*. Problem: the slow, expensive manual inspection sentence. **Two stated contributions:** *"We propose a camera and infrared crack detector that runs on a microcontroller."* and *"We build an alerting module that sends the GPS position of each crack over GSM."* The 500 m test is listed as a **goal**, not a contribution. It says whether the model or the rules read the description, and how many items were dropped as unsupported. |
| 5.6 | **Searched** and the search keywords. | As 5.2. Live: the queries are written by the model and are technical phrases. *Offline: the rules can produce a filler query such as "often missed until they" (see offline note O4).* |
| 5.7 | **Coverage in this project**. | One entry per contribution, labelled as coming from your stated contributions, each with a verdict, a wording-overlap %, the nearest passage with its citation, and why field novelty was not assessed. In the offline check the GSM/GPS alert module was **Already covered** (70%), nearest passage paper C page 1, and the camera-and-infrared detector was **Partly touched on** (57%). Live verdicts can differ with the papers fetched. Neither may be called novel. |
| 5.8 | Comparison table, research gaps and references in the same result. | A comparison across at least two papers, every cell cited. Either quoted gaps, or the note that no gap could be tied to a quotable sentence. **Graph signals are not empty.** One APA reference per kept paper, with a `doi.org` link where one exists. |
| 5.9 | Overclaim check: Ctrl+F across the whole result for *is novel*, *novel in the field*, *no prior work*, *first to*, *never been done*. | None of them appear. |
| 5.10 | **Literature review**: type `Review recent work on automated railway track crack detection` and click **Run**. | The long chain runs: search → index → retrieve → compare → novelty → synthesis. Expect a cited comparison table of the fetched papers and a coverage statement that starts *"Checked against … abstract(s) …"* and says it is not a judgement of novelty in the field. |

## Part 6 — Patents

| # | Do this | Expected |
|---|---|---|
| 6.1 | Click **Patents** at the top of the workspace. | The research-support disclaimer is visible before anything else, and stays visible in every state (loading, empty, results). |
| 6.2 | **Add a patent**. **Title (required):** the title line in `patent-sample.txt`. **Patent text:** everything between the two dashed lines in that file. Click **Add patent**. | Saved. The detail view shows the abstract and **4 claims**. Claim 1 is independent, claims 2 and 3 depend on claim 1, and claim 4 depends on claim 3. |
| 6.3 | Edit the patent and set **Public registry link** to `https://example.com/patent`. | Refused, with a message that lists the public registries allowed (for example `patents.google.com`, `patentscope.wipo.int`, `ppubs.uspto.gov`). MAIROS never fetches a patent link. |
| 6.4 | Read **Wording overlaps with this project**. | Overlaps ranked by a similarity score. Each is placed in a claim or the abstract, shows the project passage it matches, and breaks the score into term rarity × phrase length × section weight. Live: expect matches such as *accelerometer*, *convolutional neural network* or *GSM* in claims 1–4. *Offline: few matches, for example "Defects" in the abstract.* |
| 6.5 | Export the findings as Markdown and as CSV, and open the printable view. | Each contains the full disclaimer. |
| 6.6 | **Workflows → Patent awareness → Run**. | The same kind of overlaps inside the run result. Nowhere does the wording say *infringe*, *clear to use*, *patentable* or *safe*. |

## Part 7 — Graph, activity and history

| # | Do this | Expected |
|---|---|---|
| 7.1 | **Knowledge Graph** tab. | Nodes for the papers and their concepts, now including the fetched papers. Click a node: its name, type and "Mentioned *n*×" appear. Live concepts look like *convolutional neural network*, *guided waves*, *accelerometer*, *GSM*. *Offline: single keywords such as "Crack" or "Alerts".* |
| 7.2 | **Agent Activity**: select the Review my project run. | Every stage from 5.4, in order, with its status. The retriever line reads "… graph relations used (*n* chunks boosted)" with *n* above 0. |
| 7.3 | **Tasks** in the sidebar. | One row per run you started: 18, or 19 with the optional step 4.3 — the 5 chat questions (1.2 and 3.1–3.4, each an `answer` run), 3 analyses, 6 workflow runs in Part 4, 3 runs in Part 5 and the patent run. Each has its own id and time. One action never appears twice under the same id. |

## Part 8 — Evaluation

| # | Do this | Expected |
|---|---|---|
| 8.1 | Sidebar → **Evaluation**, choose *RailGuard Lite - Track Crack Detection*, click **Run evaluation**. | The built-in golden set has ten questions about retrieval-augmented generation and transformers, so none of them can be answered from railway papers. *Per-case results* shows the badges **0 scored** and **10 not in corpus**, and each case says no passage in this project satisfies its relevance rule. The four metric cards show **—**, not 0.000, with the note that no metric could be computed (fixed issue K3). |
| 8.2 | Answer-quality section. | Either the answer-quality scores, marked as model-judged, or a message naming what is missing (the optional RAGAS package or a live model). Never a placeholder score. |

For an evaluation that does score, use the separate test case in
[TEST_CASE_PROJECT_TO_EVALUATION.md](TEST_CASE_PROJECT_TO_EVALUATION.md),
with its own PDF.

## Part 9 — Export

| # | Do this | Expected |
|---|---|---|
| 9.1 | Workspace → **Export data** → **ZIP archive**, original PDFs off. | A ZIP with `README.txt`, `manifest.json`, `project.json`, `chunks.jsonl`, `chunks.csv`, `graph.json`, `tasks.jsonl`, `patents.json` and `evaluation.json`. |
| 9.2 | Open `manifest.json`. | Every file listed with a SHA-256 hash and a count. |
| 9.3 | Export again with the original PDFs included. | An `originals/` folder holding the three sample papers. |
| 9.4 | Export as **Single JSON file**. | One JSON document with the same data and no PDFs. |

## Part 10 — Error handling

Use a separate, throwaway project so the errors cannot affect the main one:
**New Project**, name `RailGuard scratch (errors)`.

| # | Do this | Expected |
|---|---|---|
| 10.1 | Upload `scanned-page.pdf`. | Refused: *"No text could be extracted from this PDF. It is probably a scanned image — OCR is not part of the mid-review build."* The project still has 0 documents. |
| 10.2 | Upload `broken-file.pdf`. | Refused: *"This file is not a readable PDF. It may be damaged, or another kind of file renamed to .pdf."* The project still has 0 documents (fixed issue K2). A password-protected PDF is refused the same way, with a message saying it is password-protected. |
| 10.3 | Run two workflows back to back without waiting (live model only). | If Groq refuses with a rate limit (429), the run's activity says which step was limited, and the run still completes. |
| 10.4 | Local runs only: stop the API (Ctrl+C), then use the app; start it again. | While it is stopped, the sidebar reads **Backend offline** and actions show a readable error, not a blank page. After the restart the project, its documents and its run history are all still there. On the live demo, skip this step unless you are running the PC. |
| 10.5 | Turn off the network and run a Topic search (local runs only). | All three sources are reported *not reached*, and the run finishes without a crash. |

## Part 11 — Phone-width check

Make the browser window 375 px wide (developer tools → device toolbar), then
open Workspace → Workflows, the Review my project result, and the Patents
page. **Expected:** no sideways scrolling of the page. Wide tables scroll
inside their own frame.

## Part 12 — Clean up

| # | Do this | Expected |
|---|---|---|
| 12.1 | **Projects** → the bin icon on *RailGuard Lite - Track Crack Detection* → confirm **Delete project**. | The project disappears. Its runs are gone from **Tasks**, and its documents, graph and papers are gone with it. |
| 12.2 | Delete *RailGuard scratch (errors)* the same way. | It disappears straight away, even right after step 10.2 (fixed issue K2). |

---

## Results checklist

Mark each row **Pass**, **Fail** or **N/A**. Note anything unexpected; a
screenshot of each failure helps.

| Part | Steps | Result | Notes |
|---|---|---|---|
| 0 Pre-flight | 0.1–0.3 | | |
| 1 Create the project, empty-project guard | 1.1–1.2 | | |
| 2 Upload the papers | 2.1–2.4 | | |
| 3 Chat & Q&A | 3.1–3.4 | | |
| 4 Workflows | 4.1–4.8 | | |
| 5 Related work and Review my project | 5.1–5.10 | | |
| 6 Patents | 6.1–6.6 | | |
| 7 Graph, activity, history | 7.1–7.3 | | |
| 8 Evaluation | 8.1–8.2 | | |
| 9 Export | 9.1–9.4 | | |
| 10 Error handling | 10.1–10.5 | | |
| 11 Phone width | 375 px | | |
| 12 Clean up | 12.1–12.2 | | |

## Fixed issues

Found on 25 October 2026 while this walkthrough was checked, and fixed the
same day. Each fix has a regression test that fails on the old code. K2 and
K3 were also re-checked on the live site, and K1 on the sample papers.

| # | Where it showed | What happened | Fix | Regression tests |
|---|---|---|---|---|
| K1 | 4.4 Generate hypotheses | The answer opened with a coverage verdict on your question instead of on the hypotheses. | The novelty step reads the hypothesis step's real output (`{"hypotheses": [...]}`) and never scores the request in their place. Its old unit test passed because it supplied a bare list. | `tests/test_novelty.py` (the real agents chained), `tests/test_workflows.py` (the flow end to end) |
| K2 | 10.2 and 12.2 | A text file renamed to `.pdf` gave a generic 500 error. On Windows the file stayed behind, locked, so deleting the project right afterwards could fail. | PDFs are opened from memory, so a rejected file is never held open. A file that is not a readable PDF, or is password-protected, gets a 400 with a message saying so, and a failed clean-up is logged instead of replacing that message. | `tests/test_extractor.py`, `tests/test_project_lifecycle.py` |
| K3 | 8.1 Evaluation | With no applicable case, the metric cards showed 0.000. | A metric with no case to average is `null` in the API, and the page shows "—" with a note. | `tests/test_evaluation.py`, `apps/web/src/app/evaluation/page.test.tsx` |
| K4 | Real papers | Extracted text kept typographic ligatures (*ﬁ*, *ﬂ*), so "flagged" was stored as "ﬂagged" and a search for the word could miss it. | The extractor expands ligatures into plain letters. | `tests/test_extractor.py` |

**Offline only** (the live model does not show these):

| # | What happens |
|---|---|
| O1 | The analysis of an uploaded paper repeats its first lines instead of summarising it. |
| O2 | Hypotheses restate their gap and can stop at a line break in the PDF. |
| O3 | Graph concepts are single frequent words ("Crack", "Alerts"). |
| O4 | Search queries written by the rules can include filler, such as "often missed until they" from the project description. |

## How this walkthrough was checked

On 25 October 2026 the whole sequence was run through the API on a fresh copy
of the backend using the offline model, including the web searches. The page
and chunk counts, the answers in Part 3, the comparison values, the quoted
gaps, the novelty verdicts (92% and 25%), the claim segmentation, the
coverage report and the export contents above come from that run. With the
live model the wording changes and the papers fetched from the web change from
day to day, so the steps check what must hold either way: the numbers in the
papers, the citations, the verdict structure, and the absence of overclaims.

After the four fixes above, Generate hypotheses was run again on the sample
papers (each of the three hypotheses was checked, and the request was not),
and the live site was checked for the bad-file and password-protected uploads,
an immediate project deletion afterwards, and the "—" on the Evaluation page.
