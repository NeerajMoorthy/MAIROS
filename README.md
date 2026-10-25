# MAIROS — Multi-Agent Intelligent Research & Orchestration System

An AI research assistant that combines **retrieval-augmented generation**, a
**knowledge graph**, and a **multi-agent orchestrator** to answer research
questions with citations you can check.

Beyond question answering it runs seven research workflows — paper comparison,
gap detection, hypothesis generation, experiment design, patent awareness,
novelty checking, and a full literature review — each one grounded in passages
it can quote, plus an evaluation dashboard that measures retrieval quality with
real IR metrics.

**Everything below runs end to end today**, offline if necessary: 652 backend
tests and 144 frontend tests pass with no API key, no model download, and no
network (plus 9 Postgres contract tests that run when a test database is
configured — they pass against PostgreSQL 16).

It runs locally with no accounts and no services by default. For a multi-user
deployment the same code switches on, by configuration only, **Better Auth**
sign-in, a **Supabase** Postgres store, **Cloudflare** hosting for the
frontend, **Fly.io** for the API and **Google Analytics** — see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## Quick start

### Prerequisites

| Tool    | Version |
|---------|---------|
| Python  | ≥ 3.11  |
| Node.js | ≥ 20    |

No Docker, no database server. ChromaDB runs embedded and the knowledge graph
is a NetworkX object persisted to JSON.

### 1. Configure the environment

```bash
cd mairos
cp .env.example .env
```

Open `.env` and set your Groq key (free tier: <https://console.groq.com/keys>):

```
GROQ_API_KEY=gsk_...
```

> Without a key the backend still runs. It falls back to a deterministic
> offline model so the pipeline stays demoable — answers become extractive
> quotes from your documents rather than generated prose, and `/api/health`
> reports `"live": false`.

### 2. Backend

```bash
cd apps/api
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API on <http://localhost:8000> · interactive docs at
<http://localhost:8000/docs>.

> First run downloads the `all-MiniLM-L6-v2` embedding model (~90 MB). Allow a
> minute and make sure you are not behind a proxy that blocks huggingface.co.

### 3. Frontend

```bash
cd apps/web
npm install
npm run dev
```

UI on <http://localhost:3000>. Next.js proxies `/api/*` to port 8000, so there
is no CORS setup and no base URL to configure.

### 4. Verify

```bash
curl http://localhost:8000/api/health
# {"status":"ok","llm":{"provider":"groq","model":"llama-3.3-70b-versatile","live":true}, ...}

cd mairos && python -m pytest -q     # 652 tests, no network or API key needed
```

---

## Environment variables

Set in `mairos/.env`. Every value has a working default except the API key.

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | *(empty)* | Groq API key. Empty ⇒ offline fallback model. |
| `DEFAULT_LLM` | `llama-3.3-70b-versatile` | Reasoning, analysis, synthesis. |
| `FAST_LLM` | `llama-3.1-8b-instant` | Routing and structured extraction. |
| `ALLOW_OFFLINE_LLM` | `true` | `false` ⇒ a missing key is a hard error. |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `512` / `64` | Chunking. |
| `DEFAULT_TOP_K` | `5` | Passages retrieved per question. |
| `LITERATURE_SOURCES` | `arxiv,openalex,semantic_scholar` | Sources each literature search queries. |
| `LITERATURE_MAX_RESULTS` | `8` | Papers kept per search, after merging sources and queries. |
| `LITERATURE_QUERY_COUNT` / `LITERATURE_PER_QUERY` | `4` / `5` | Queries per search; results per query per source. |
| `SEMANTIC_SCHOLAR_API_KEY` | *(empty)* | Optional. Without it Semantic Scholar often rate-limits (HTTP 429); the coverage report says when it did. |
| `OPENALEX_MAILTO` | *(empty)* | Optional email for OpenAlex's faster polite pool. |
| `DATA_DIR` | `apps/api/data` | Moves uploads, Chroma, graphs and SQLite under one directory (a Fly.io volume). |
| `DATABASE_URL` | *(empty)* | Empty ⇒ SQLite. A `postgres://` URL (Supabase) moves the metadata store to Postgres. |
| `AUTH_JWKS_URL` | *(empty)* | Empty ⇒ local single-user mode. Set to `https://<site>/api/auth/jwks` to require Better Auth tokens and isolate projects per user. |
| `AUTH_ISSUER` / `AUTH_AUDIENCE` | *(empty)* | The claims the API checks on those tokens — the site's base URL. |

Frontend (`apps/web`, build time): `MAIROS_API_URL` (where `/api` is
proxied), `NEXT_PUBLIC_AUTH_ENABLED`, `NEXT_PUBLIC_GA_MEASUREMENT_ID`,
`NEXT_PUBLIC_AUTH_SOCIAL`; server secrets `BETTER_AUTH_SECRET`,
`BETTER_AUTH_URL`, `DATABASE_URL`. All optional for local use.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Next.js UI  Search · Chat · Workflows · Tasks · Graph · Eval │
└───────────────────────────┬───────────────────────────────────┘
                            │  REST (/api/*)
┌───────────────────────────▼───────────────────────────────────┐
│  FastAPI   projects · ingest · query · chat · graph · tasks   │
│            evaluation · patents                               │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│  Agent Orchestrator                                           │
│    Router decides the flow, then runs agents in order         │
│                                                               │
│  Intake · Literature · Indexer · Loader · Retriever           │
│  Analysis · Knowledge Graph · Citation · Synthesis            │
│  Comparison · Gaps · Hypothesis · Experiment · Patent         │
│  (registered, off by default: Planner)                        │
└───────┬──────────────────────────────┬────────────────────────┘
        │                              │
┌───────▼─────────┐          ┌─────────▼──────────┐   ┌─────────┐
│ ChromaDB        │          │ NetworkX graph     │   │ Groq    │
│ (embedded)      │          │ (JSON per project) │   │ LLM API │
└─────────────────┘          └────────────────────┘   └─────────┘
```

### Why no LangGraph

The spec offered LangGraph or a lightweight orchestrator. **We use a custom
registry-based orchestrator**, because MAIROS's flows are short, linear, and
fully determined by a single routing decision made up front — there is no
cyclic state machine, no conditional re-entry, and no checkpointing
requirement at this scale. A LangGraph `StateGraph` would add a dependency and
an indirection layer without removing any of the logic in
`services/agents/orchestrator.py`.

The property that actually matters — adding agents without restructuring — is
preserved by the registry: an agent is a `BaseAgent` subclass, registered by
name, and named in a flow. If the final build needs cycles (an agent that
re-plans after a failed retrieval, say), `AgentOrchestrator.run` is the single
function that changes.

---

## The agents

Each is a distinct class in `services/agents/`, callable by the orchestrator.

| Agent | File | Role |
|---|---|---|
| **Router** | `router.py` | Classifies the request into a flow via the LLM, with a keyword heuristic as fallback. This is what makes the orchestrator decide rather than branch on a flag. |
| **Intake** | `intake.py` | Reads a pasted project description into a brief — problem, methods, datasets, goals, stated contributions, search keywords. Every item except the keywords must be supported by the description's own words, or it is dropped and counted. |
| **Literature** | `literature.py` | Searches arXiv, OpenAlex and Semantic Scholar with several queries (written by the live model, rule-based otherwise), merges duplicates across sources, ranks by agreement and topical overlap, and records a **coverage report** of what was and was not searched. Metadata and abstracts only; links allowlisted. See `services/literature/`. |
| **Indexer** | `indexer.py` | Chunks and embeds retrieved papers into ChromaDB so they become answerable. |
| **Loader** | `indexer.py` | Pulls an uploaded document's chunks back out for analysis. |
| **Retriever** | `indexer.py` | Hybrid retrieval — dense vector search fused with graph traversal. |
| **Analysis** | `analysis.py` | Extracts key contributions, methodology, summary, concepts, limitations. |
| **Knowledge Graph** | `kg_agent.py` | Adds papers, authors, and extracted concepts as nodes/edges after each run. |
| **Citation** | `citations.py` | Formats sources as APA 7th references, with a deterministic non-LLM formatter as fallback. |
| **Synthesis** | `synthesis.py` | Writes the final answer, grounded strictly in retrieved passages. |
| **Comparison** | `comparison.py` | Builds a comparison table across documents where every cell carries the passage supporting it. |
| **Gaps** | `gaps.py` | Detects research gaps, each quoted from the sentence that states it, plus structural signals from the graph. |
| **Hypothesis** | `hypothesis.py` | Proposes falsifiable hypotheses, each attached to an evidenced gap. |
| **Experiment** | `experiment.py` | Turns a hypothesis into a runnable protocol: objective, data, baselines, metric, procedure, threats. |
| **Patent Awareness** | `patent_awareness.py` | Locates project concepts in user-supplied patent text down to the claim, and ranks each overlap by an explainable similarity score. Research support only. |
| Planner | `planner.py` | Decomposes multi-hop questions. Registered, not in a default flow. |

Shared helper: `evidence.py` groups retrieved chunks into labelled sources and
attaches the passage that best supports a generated claim. It is the reason the
research workflows can drop anything they cannot cite.

### The flows

Defined in `services/agents/router.py` and exposed at `GET /api/flows`:

```python
FLOWS = {
    "search":     ["literature", "indexer", "knowledge_graph", "citation", "synthesis"],
    "analyze":    ["loader", "analysis", "knowledge_graph", "citation"],
    "answer":     ["retriever", "synthesis", "citation"],
    "compare":    ["retriever", "comparison", "citation", "synthesis"],
    "gaps":       ["retriever", "gaps", "citation", "synthesis"],
    "hypothesis": ["retriever", "gaps", "hypothesis", "citation", "synthesis"],
    "experiment": ["retriever", "gaps", "hypothesis", "experiment", "citation", "synthesis"],
    "patent":     ["retriever", "patent_awareness", "citation", "synthesis"],
}
```

The Router picks one from the request. Callers can force a flow with
`{"flow": "compare"}` on `POST /api/projects/{id}/tasks`; PDF upload always
forces `analyze`. The endpoint validates against this registry directly, so a
newly registered flow is callable the moment it is added — there is no second
list to keep in sync.

Note the chaining: `hypothesis` runs gap detection first because a hypothesis
must attach to an evidenced gap, and `experiment` runs the whole chain because
a protocol exists to test a specific hypothesis. That dependency is expressed
in the flow definition rather than inside the agents, so each agent stays
independently testable.

Failure is contained: every agent runs through `safe_run`, so one failing agent
logs an error event and degrades the answer instead of aborting the run. If a
literature source is unreachable or rate-limited mid-demo, the search carries
on with the others, and both the activity log and the result's "What was
searched" report name the source that did not answer.

---

## How RAG is wired in

1. **Ingest** — `services/ingestion/`: PyMuPDF extracts text per page →
   `RecursiveChunker` splits on paragraph → line → sentence → word boundaries
   at 512 chars with 64 overlap → ChromaDB embeds with `all-MiniLM-L6-v2`.
2. **Metadata** — every chunk carries `document_id`, `document_name`,
   `project_id`, `page`, `chunk_index`, `source`. The page number is what makes
   `[paper.pdf, p. 4]` citations verifiable.
3. **Retrieve** — `HybridRetriever` runs dense search filtered by
   `project_id`, scores hits with Reciprocal Rank Fusion, and multiplies the
   score of any chunk also reachable in the knowledge graph (`graph_hit: true`
   in the response, shown as a badge in the UI).
4. **Generate** — `services/generation/llm.py` builds numbered `--- SOURCE n
   [doc, p. N] ---` blocks and instructs the model to use **only** those
   passages, to end factual sentences with a source marker, and to reply
   `"I cannot answer this based on the provided documents."` when the context
   does not cover the question.

`POST /api/projects/{id}/query` returns the answer *and* the exact passages
that produced it, so grounding is auditable in the UI rather than asserted.

## How the knowledge graph is wired in

- **Store** — `services/knowledge_graph/networkx_store.py`. One `DiGraph` per
  project, persisted to `apps/api/data/graphs/<project>.json` via an atomic
  temp-file swap.
- **Write** — after each paper is processed, the KG agent adds the paper and
  its authors structurally (`AUTHORED_BY`), then LLM-extracts concepts and
  typed relations (`USES`, `EXTENDS`, `COMPARES_TO`, `PART_OF`,
  `EVALUATED_ON`, `IMPROVES`, `RELATED_TO`). Extraction output is validated:
  unknown relation types collapse to `RELATED_TO`, and a relation endpoint
  missing from the entity list is promoted to one so the graph stays connected.
- **Merge** — re-mentioning an entity increments `mentions` rather than
  duplicating the node, so the graph accumulates across uploads and searches.
- **Read** — `GET /api/projects/{id}/graph` returns
  `{nodes: [{id, name, group, val}], links: [{source, target, label}]}`,
  exactly the shape `react-force-graph-2d` expects.
- **Back into retrieval** — entity nodes remember the chunks they came from
  (`source_chunk_ids`), which is what lets graph traversal boost vector hits.

---

## The research workflows

All seven run through the same orchestrator, emit real events to the Tasks
trace, and are reachable from the **Workflows** tab of a project (or by POSTing
a task with the matching `flow`). What they share is a refusal to ship a claim
they cannot point at.

| Workflow | Flow | What it produces | What it will not do |
|---|---|---|---|
| **Paper comparison** | `compare` | A table of dimensions × documents; each cell quotes the passage behind it | Show a cell no retrieved passage supports — those are dropped and counted |
| **Gap detection** | `gaps` | Gaps quoted from the sentence that states them, plus graph signals (thinly covered concepts, never-compared methods) | Report a gap whose wording cannot be located in a passage |
| **Hypothesis generation** | `hypothesis` | Falsifiable hypotheses, each carrying the citation of the gap it descends from | Generate a hypothesis attached to no evidenced gap, or one with no testable prediction |
| **Experiment design** | `experiment` | Objective, datasets, baselines, deciding metric, ordered procedure, controls, threats to validity | Ship a design with no metric or no procedure — it would decide nothing |
| **Patent awareness** | `patent` | Overlaps between project concepts and patent text you pasted, located to the claim or section and ranked by a similarity score with its components shown, under a standing disclaimer; Markdown/CSV export and a printable view | Fetch a patent, construe claims, or assess novelty or infringement |
| **Novelty check** | `novelty` | Whether a claim is already covered by this project's passages, scored by wording overlap and cited | Say anything is novel *in the field* — `field_novelty` is the constant `"not_assessed"`, and no code path can change it |
| **Literature review** | `review` | The long chain: find papers, index them, retrieve them back, contrast them in a cited table, then report what is new to this project | Substitute for a systematic review; it sees only what it retrieved |
| **Review my project** | `project` | A pasted project description read into a brief, a multi-source search built from it, a cited comparison, the gaps those papers state, and each stated contribution checked for coverage — headed by what was searched and every coverage warning | Call a contribution novel, or present a thin search as a thorough one: the coverage report states sources, counts, years and warnings beside the findings |

Every flow that searches the literature (`search`, `review`, `project`) also
returns a **coverage report**: which sources answered (and why any did not),
the queries run and who wrote them, papers found vs kept, duplicates merged,
the year range, and warnings when the set is too small, too old or only
partly searched. It is computed from the search — no model writes it.

The evidence chain is explicit and traceable in the UI:

```
passage → quoted gap → hypothesis → experiment design
```

### Safety notes for patent awareness

Patents have their own page (**Patents** in the sidebar, or
`/projects/{id}/patents`): a list, a detail view per patent with its metadata
and segmented claims, the computed findings for the project, Markdown and CSV
export, a printable view, and a button that runs the `patent` flow.

What the feature now does, all in `services/patents/`:

- **Claim-level segmentation** (`segmentation.py`). Pasted text is split into
  abstract, description and numbered claims. `1.`, `1)`, `(1)`, `[1]`,
  `[0001]`, `Claim 1:` and `[Claim 1]` are recognised; a marker only counts if
  it carries the next expected number, so a wrapped line starting `2.5 mm` or
  `claim 1, wherein` is never read as a new claim. Dependencies ("of claim 1",
  "any one of claims 1 to 3") are resolved to earlier claims only; anything else
  is kept as an unresolved reference. Unstructured text falls back to
  whole-document matching **and says so**.
- **Explainable scoring** (`scoring.py`). `similarity = term rarity × phrase
  length × section weight`, each 0–1. Rarity is measured against the project's
  own indexed passages; a four-word phrase outweighs a single word; an
  independent claim (1.0) outweighs a dependent claim (0.85), the abstract
  (0.6) and the description (0.4). Repetition inside the patent is shown but
  not scored, so boilerplate cannot outrank a rare phrase. The UI labels it
  *"Similarity score (shared wording only)"* and shows each component.
- **Metadata** (`metadata.py`): publication and application number, family,
  CPC/IPC, assignee, inventors, priority/filing/publication dates — typed by
  hand. Dates must parse and run priority → filing → publication; CPC/IPC codes
  must have the international shape; an unfamiliar publication-number format is
  accepted with a warning, not rejected. Records stored before these fields
  existed load with them blank.
- **One computation, every surface** (`findings.py`). The agent, the Patents
  page, both exports and the printable view all report from the same function,
  so an export cannot disagree with the screen.
- **Exports carry the full disclaimer in their own body** (`export.py`) — at
  the top and bottom of the Markdown, and as a column on every CSV row, because
  a CSV has no comment syntax a spreadsheet respects.
- **A wording audit** (`wording.py`) lists the language that would imply a
  legal conclusion ("infringe", "violation", "clear to", "safe to",
  "patentable", "invalid", "freedom to operate", "low risk"…). Tests run it over
  agent output, every API response, every error message, both exports and the
  rendered UI; the only exceptions are the exact reviewed disclaimer sentences,
  never "any sentence containing *not*". A model-written summary that trips it
  is replaced by the deterministic one.

The boundary itself has not moved, and lives in `services/patents/sources.py`:

- **MAIROS never fetches a patent.** The text analysed is what the user pasted.
  A URL is stored as a reference for a human to open, never requested by the
  server — so there is no request-forgery surface and no scraping of commercial
  databases.
- **Links are allowlisted** to free public registries (Google Patents,
  Espacenet, PATENTSCOPE, USPTO, PatentsView, Indian Patent Search). Anything
  else is rejected with an explanation.
- **Findings are computed, not generated.** Segmentation, matching and scoring
  are Python; a model is used only to phrase a summary of findings that already
  exist, and cannot add, remove, or re-score one.
- **Every response carries the disclaimer:** *Research-support only. Not legal
  advice or a patentability assessment.* Absence of an overlap is explicitly
  not reported as clearance. A test enumerates every patent route from the
  OpenAPI schema and fails if one is added without it.

### Safety notes for novelty

"Is this novel?" is an unbounded negative claim: supporting it means showing
that nothing in the published record anticipates the idea. MAIROS has read a
handful of PDFs, so it answers the narrower question it can answer and refuses
the wider one out loud rather than silently.

- **The verdict is computed, not generated.** Coverage is content-word overlap
  between the claim and the retrieved passages, in Python. A model asked "is
  this novel?" will oblige; it is never asked. `tests/test_novelty.py` includes
  a deliberately sycophantic model that calls everything unprecedented, and
  asserts that not one verdict moves.
- **`field_novelty` is the constant `"not_assessed"`.** There is no branch that
  assigns anything else, the TypeScript type is the string literal, and the
  React component's only field-level output is the sentence explaining why it
  was not assessed.
- **"Not found in this project's sources" is not a finding of originality,**
  and the report says so in those words, next to the exact scope that was
  searched.
- **Model-written notes are dropped unless citable**, on the same rule as every
  other agent: a note that no retrieved passage supports is counted and
  discarded rather than displayed.
- **The model is never given the novelty question.** This is the subtlest part.
  `NoveltyAgent` is not the last agent in the flow — `synthesis` runs after it
  and writes the headline prose. Handed "is my idea of X novel?" over passages
  that do not mention X, a model obeying every rule in the grounding prompt
  answers "none of the passages describe X, so this appears to be novel" and
  cites a passage for it. So the question is stripped of its framing before it
  reaches the generator (`strip_question_framing`), the answer is composed from
  the computed report rather than generated, and the model's contribution is
  confined to a section describing what the sources say about the topic.
- **Coverage is scored on the idea, not the phrasing.** The overlap ratio
  divides by the claim's own token count, so every word typed only to ask the
  question is a token the corpus can never match — and the drift runs towards
  "not found in this project's sources", the one verdict that reads like a
  novelty signal. The same stripper runs before scoring, and "covered" also
  requires a minimum number of words to actually match, so a table caption
  cannot reach the threshold on three incidental hits.

---

## Accessibility and responsiveness

Verified rather than asserted. A Playwright pass over every route at 375 px,
768 px and 1440 px checks for horizontal overflow, undersized targets, missing
accessible names and missing focus indicators; axe-core runs the WCAG 2.1 AA
ruleset against the populated result views inside the Vitest suite; and
`tests/test_theme_contrast.py` computes the contrast ratio of every theme token
pair straight from `globals.css`.

What that turned up and fixed:

| Found | Fix |
|---|---|
| The sidebar opened at 240 px on a 375 px phone, pushing the page 193 px off-screen | It starts closed below `md` and overlays instead of squeezing |
| A collapsed sidebar still held five nav buttons in the tab order | `invisible` when closed on a phone, so they leave the tab order with it |
| `text-success` at 3.31:1 and the warning icon at 2.49:1 in light mode | Tokens darkened to 4.59:1 and 3.67:1; hue and chroma unchanged |
| The offline and patent banners at 1.12:1 in dark mode — effectively invisible | The warning colour now carries only the border and tint; text sits at full contrast |
| The destructive badge at 3.34:1 in dark mode | Its foreground darkened to 5.15:1, leaving `text-destructive` alone |
| Every bare `<button>` disclosure had no focus indicator and no `aria-expanded` | A shared `.focus-ring` utility and explicit expanded state |
| Six inputs labelled by placeholder alone | Real `aria-label`s |
| The evaluation project picker collapsed to 20 px tall when stacked | `flex-1` scoped to the row layout, so `h-9` applies |
| Animations ran regardless of `prefers-reduced-motion` | Honoured, including the indefinite status-dot pulse |

---

## What an adversarial review of this work found

The seven items above were reviewed against their own claims before being
called done. The review read the new code looking for ways each guarantee could
fail, and every finding below was reproduced before it was fixed and is now
covered by a test. They are listed because the failures are more instructive
than the features:

| Found | Why it mattered | Fix |
|---|---|---|
| The `synthesis` agent still received the raw "is this novel?" question | `NoveltyAgent`'s guarantee held, and the flow broke it anyway: the headline prose above the hedged novelty card could read "this appears to be novel" | The question is stripped of novelty framing before any model sees it, and the answer is composed from the computed report |
| Coverage scored the user's phrasing, not the idea | The more carefully someone worded a novelty question, the more likely they were to be told the idea was not in their corpus | The same stripper runs before scoring |
| A four-word claim reached "already covered" on three incidental word hits | A table caption was presented as prior coverage, with a citation | "Covered" now needs a minimum of matched words, not just a high proportion |
| `isinstance(exc, OSError)` treated `FileNotFoundError` as a dependency outage, and the implicit `__context__` chain spread it | A `KeyError` after any handled file lookup became a 503 with retry advice — the exact failure the module was written to prevent | Narrow exception types, and only the explicit `__cause__` chain is followed |
| Every LLM outage was reported as a vector-store outage | A bad `GROQ_API_KEY` sent the reader off to check their disk | The failing dependency is identified from the exception and gets its own advice |
| A chunked request has no `Content-Length`, so it skipped the size cap entirely | It landed on the old post-`read()` check — the 40 MB-in-memory request the cap exists to prevent | The body is metered as it streams, not just checked from the header |
| `CORSMiddleware` was innermost, so no rejection carried CORS headers | Every 413, 429 and 503 reached the browser as `TypeError: Failed to fetch`; none of the carefully worded messages was readable | CORS is outermost, and the generic handler became middleware so it sits inside it |
| `/retrieve` drew on the read budget; anything ending `/health` was unlimited | A full embedding pass had 12× its intended throughput, and `/anything/health` was a free unlimited endpoint | Exact path matching for the exemption, and `/retrieve` and `DELETE` on the write budget |
| Every list and count in the metadata store read the dicts without the lock | `RuntimeError: dictionary changed size during iteration` on ordinary concurrent use, surfacing as a bare 500 | Readers snapshot under the same lock writers hold |
| "find recent papers on the Raft consensus **protocol**" routed to experiment design | Subject-matter nouns in the hint lists captured discovery requests — and only once the project had documents, so the same request behaved differently on day two | Explicit discovery intent is checked first, and the hint lists are multi-word |
| The mobile sidebar did not close on navigation | It covered the page the user had just asked for, with the toggle painted under the backdrop | Nav buttons close it where it overlays |
| The mobile sidebar painted open, then animated shut, on every load | The server-rendered HTML is painted before hydration decides | It renders closed below `md` by CSS until the client has decided |
| `NoveltyAgent`'s hypothesis branch was unreachable | The more useful check — "is this hypothesis already in the corpus?" — never ran | `novelty` now runs after `hypothesis` in that flow |
| The `review` flow counted its own fetched arXiv abstracts as "documents from this project" | On a project with no uploads, "absent from one arXiv query" was presented as a statement about the user's library | Fetched abstracts are identified by document id and reported separately |

Smaller ones, also fixed: `Database.close()` closed only the calling thread's
connection; a transient database-open failure permanently poisoned the store;
the rate limiter's counter table had no eviction; `RouterAgent.run` passed a
chunk count where a document count was meant.

### Found while adding multi-source literature search

| Found | Why it mattered | Fix |
|---|---|---|
| Literature search queried arXiv only, with the first six words of the request | Journals, conferences and anything phrased differently were never seen, and nothing said so | arXiv, OpenAlex and Semantic Scholar, several queries per search, and a coverage report on every result |
| Rank fusion alone put an off-topic robotics benchmark above "Railway Track Crack Detection Vehicle" in a live search | A broad query agrees with itself across sources about papers that are not on the topic | The fused rank is blended with each paper's wording overlap with the topic; on the same live search 6 of 8 kept papers became on-topic |
| Offline, the last quoted passage ran on into the user's question | A pasted project description was quoted as if a paper had said it | The offline model quotes from the sources message only |
| Coverage notes could quote an abstract's "Title: … Authors: …" header | Metadata was presented as the passage that relates to a claim | Line breaks end a sentence and header lines are skipped |
| Graph hits never boosted a fetched abstract — a live run used 21 graph relations and boosted 0 passages | The graph cites an abstract by its document id; the index holds it as `<id>_0`, `_1`, so chunk ids never matched (this predates multi-source search) | A graph source id also matches a chunk's document id; an upload is still matched chunk by chunk |
| In the `project` flow the knowledge graph was built after `gaps` | Live, the gap agent's graph signals came from an empty graph and the section was blank | The graph is built straight after indexing; the same live run then showed thin-coverage and never-compared-method signals |
| `ARXIV_MAX_RESULTS` / `ARXIV_TIMEOUT` named one source | They no longer described what a search does | Replaced by `LITERATURE_*` settings; the old names are ignored |

### Found in the independent review of literature search and project review

An adversarial review of the new code (25 October 2026), read for ways each
guarantee could fail. All fifteen findings were reproduced before they were
fixed, and each has a regression test in `tests/test_review_fixes.py`: run
against the reviewed commit, 27 of its 30 tests fail, at least one per finding
(the other three guard against a fix overreaching).

| Found | Why it mattered | Fix |
|---|---|---|
| Fetched-paper chunk ids carried no project | A second project fetching the same paper took over the first one's copy in the index; the first silently lost it, and deleting the second deleted it outright (this predates multi-source search) | Chunk ids are project-scoped |
| A model field given as one string ("camera, infrared sensors") was read letter by letter | The brief's keywords became "r", "a", "i"… and the search was run for single letters | String fields are split into items (commas for short fields, not for sentences); single characters are never a query |
| Contributions were checked only against the retriever's top five passages for the whole description | Live: 8 papers kept, contributions compared with 4 — all from one source — while the answer said 8 were searched | Each claim is checked against every abstract the run fetched plus a retrieval for that claim; the scope names what was checked, including abstracts from earlier searches |
| A paper's id was its first source's id | Found through OpenAlex one day and arXiv the next, a paper was listed and indexed twice | One stable id (versionless arXiv id, else DOI, else the source's id); re-indexing replaces copies under any other id the paper is known by, including the ids earlier builds wrote |
| The brief's grounding check ignored short numbers | An invented "detects 95% of cracks" was shown as the user's own claim | Every number in an extracted item must appear in the description |
| Any request of 800+ characters was routed to `project` before the model router | A long patent-overlap request became a literature search | An explicit patent or analysis ask in the opening wins; for long text without first-person wording, so does any research ask |
| Records were merged only when they matched one already seen | A preprint and its published version stayed two papers even after a third record carried both ids | Union-find over every shared identifier |
| Every concept was attributed to the same first ten passages | With fetched abstracts boostable, the graph boost lifted all of them equally and meant nothing | Concepts point at the passages that mention them; papers link to the concepts their own abstract mentions |
| Two-character words were dropped from search terms | "AI in healthcare" searched for "healthcare" | Acronyms (capitalised, or with a digit) are kept, in rule-based queries and arXiv terms |
| arXiv's in-band error feed (HTTP 200, title "Error") was parsed as a paper | A paper titled "Error" could be indexed, graphed and cited | Error entries are skipped; a feed of nothing else marks arXiv as failed with its own message |
| An empty or misspelled `LITERATURE_SOURCES` was reported as "none could be reached" | The reader was sent to check the network, and a model call was spent on queries nothing would run | The report says no source is configured, names unknown ones, and skips the model call |
| Semantic Scholar's sequential queries each waited the full timeout | A stalled service could hold a search for 80 seconds | A per-search deadline (`LITERATURE_SOURCE_DEADLINE`, 40 s); what arrived in time is kept |
| A failed token-cap retry discarded the first reply | Live, the retry hit Groq's per-minute limit; an agent without a fallback would then lose its partial answer | If the retry fails, the cut-off reply is returned; only a failed first call raises |
| If the novelty step failed, a project answer lost its header and sent the whole description as its question | The reader no longer saw what was checked | The header is added whenever there is a brief, and the question is the brief's focus |
| The literature package kept two stopword lists that disagreed | A word dropped from a query could still become an arXiv term | One list, shared by query building and arXiv terms (evidence matching keeps its own list by design) |

### Found while completing patents and the deployment stack

The same approach — reproduce, fix, add a test — applied to this pass. Each is
covered by a test or was confirmed in a browser:

| Found | Why it mattered | Fix |
|---|---|---|
| Upload paths embedded the user's original filename | A long PDF name overflowed Windows' 260-character path limit and the upload failed as a bare 500 (reproduced in the browser check) | Files are stored as `<uuid>.pdf`; the name lives only in metadata |
| PDF extraction and embedding ran on the event loop | Every other request — including the UI's task polling — froze for the whole embedding pass of an upload | Ingestion runs in the threadpool |
| Background dispatch chose its mode with `"pytest" in sys.modules`, duplicated in two routers | Production behaviour depended on which modules happened to be imported | One `dispatch_pipeline` helper driven by a `run_tasks_inline` setting |
| Agent Activity never rendered a novelty result | A novelty run looked empty in the Tasks view | One shared `TaskResultView` for Workflows and Tasks |
| The same prompt run twice showed two identical rows | Two genuine runs read as one run listed twice (the reported "duplicate") | Each row shows its flow, run id and start time; a test pins one row per run with its own events |
| Expanded passages were tracked by index for the whole panel | Opening passage 2 of one run left passage 2 of the next run open | Expansion state lives on each passage; the detail pane is keyed by run |
| A slow task-list poll could land after a faster, newer one | The list briefly reverted to older state | Polls are numbered; stale responses are dropped |
| The run list and detail shared one fixed height below `lg` | On a phone the detail card was clipped | The tab scrolls below `lg` and the list is capped at 40vh |
| The header said "offline LLM mode" before health had answered | Every page load flashed a false warning with a live model configured (seen in the browser) | Unknown is not "offline": the banner waits for the first response |
| A long registry URL in patent metadata was an unwrappable `inline-flex` link | The Patents page was 487px wide on a 375px phone (measured) | Plain inline link with `break-all`; 375/375 re-measured |
| The printable view rendered `new Date()` on the server and the client | A hydration mismatch that switched the whole page to client rendering | The timestamp is set when the findings load |
| A model-written patent summary was shown if parseable | A model asked for a neutral sentence could still volunteer "your work is safe to commercialise" | The summary passes the legal-wording audit or the deterministic one is used |
| A claim citing a later claim ("claim 3 … of claim 5") read as independent | Its section weight — and score — rose to an independent claim's | Worded-as-dependent stays dependent; the reference is kept as unresolved |
| A PATCH sending `""` for a date was dropped as "no change" | A wrong date could not be cleared | Empty string clears; explicit `null` means "leave as is" |
| `better-auth/cookies` in the edge middleware | Pulled the whole JWT library into the edge bundle with runtime warnings, to compare two cookie names | The middleware reads the two cookie names directly |
| Evaluation reports existed only in the HTTP response | Nothing could be exported, compared or reviewed later | The latest report is persisted per project (new `evaluations` table, both backends) and deleted with the project |
| `all_chunks` stops at 2,000 rows by default | An export of a large project would have been silently incomplete | The export reads without a limit; a test indexes 2,050 chunks |
| Graph extraction with the configured `gpt-oss-120b` added "+0 nodes" on every upload, with no error | The knowledge graph — and graph-boosted retrieval — stayed empty, and nothing said why | Diagnosed with one live call: extraction works, but a 330-character input already used 1,156 of the 1,400-token cap (683 on hidden reasoning); the real 1,600–1,800-character inputs ran out mid-JSON. Extraction now has its own budget (`LLM_EXTRACTION_MAX_TOKENS`, 4,096) and asks for compact JSON; a reply cut off at the cap is reported as such, and a complete entity list in it is kept. A stray `"` in the prompt was removed too |
| Every other agent still ran on the 1,400-token default, with both configured models being gpt-oss reasoning models | A comparison, gap or hypothesis reply could end mid-JSON and be discarded as unparseable, leaving an empty section with no error | `BaseAgent.invoke_llm` now checks the provider's `finish_reason`; a reply stopped at the cap is retried once with `LLM_RETRY_MAX_TOKENS` (4,096) and logged. `tests/test_agent_token_cap.py` |
| Graph names from `gpt-oss` used U+2011 non-breaking hyphens ("retrieval‑augmented approach"), seen in the live confirmation run | They never matched "retrieval-augmented" in a document or question, so graph-boosted retrieval skipped them, and a second spelling could become a duplicate node | Names are folded to ASCII hyphens and spaces (`services/common/text.py`) wherever the graph is written or queried; graph files saved earlier merge their look-alike nodes on load, summing mentions |
| The export dialog returned focus to `<body>` on close | A keyboard user lost their place in the page | Focus returns to the control that opened it |

---

## Authentication (optional)

Off by default: locally MAIROS is a single-researcher tool with no login. Set
`AUTH_JWKS_URL` (and `NEXT_PUBLIC_AUTH_ENABLED=true` on the frontend) and it
becomes multi-user:

- **Better Auth** runs inside Next.js (`/api/auth/*`): email and password, plus
  GitHub/Google when configured, with users and sessions in Supabase.
- Its **JWT plugin** issues 15-minute tokens signed with a key published at
  `/api/auth/jwks`. The browser sends them as bearer tokens; **FastAPI verifies
  signature, expiry, issuer and audience** (`apps/api/app/auth.py`) without any
  access to the auth database. HS* algorithms are refused, so a public key can
  never be used as an HMAC secret.
- **Isolation is one dependency on every router.** It checks ownership from the
  path (`project_id`, or a `task_id`'s project). Everything MAIROS stores is
  scoped by project, so that single check covers documents, chunks, graphs,
  patents, tasks and evaluations. A project you do not own answers 404.
- Projects created before auth was enabled belong to nobody until assigned
  (`scripts/assign_project_owner.py`), rather than to everybody.
- The rate limiter buckets signed-in users by user, not by address — behind the
  Cloudflare proxy every user would otherwise share one budget.

## Baseline hardening

What is in place protects against the failure mode that applies with or
without auth: one client or a runaway loop exhausting the box
(`apps/api/app/middleware.py`, `apps/api/app/errors.py`).

- **Body caps** are checked from `Content-Length` before anything reads the
  body — 1 MB for JSON routes, 40 MB for uploads. The upload route's own check
  ran *after* `await file.read()`, which is exactly the request you most want
  to refuse early.
- **Rate limits** are a fixed window per client address: 240 reads/minute, and
  20/minute for anything that starts agent work. In-process, so per worker —
  the docstring says that rather than implying a distributed guarantee.
  `/health` is never limited, because a throttled probe looks like an outage.
- **CORS** takes an explicit origin list from configuration, never `*`, with
  credentials off (the API authenticates by bearer header, never cookies) and
  methods and headers enumerated.
- **Structured logging** emits one JSON line per request with a correlation id
  returned as `X-Request-ID`, so a reported failure can be found in the log. A
  client-supplied id is sanitised before it reaches log output.
- **Outages degrade to 503** with a sentence naming the dependency and what to
  do; a genuine bug stays a 500 and its stack trace stays in the log rather
  than going to the caller.

---

## Evaluation

`GET /api/evaluation/status` · `GET /api/evaluation/golden-set` ·
`POST /api/projects/{id}/evaluation/run` — and the **Evaluation** page in the UI.

Four retrieval metrics are computed live against a project's own indexed
chunks, with no LLM involved:

| Metric | Definition |
|---|---|
| **Recall@5** | relevant passages found in the top 5 ÷ all relevant passages in the corpus |
| **Precision@5** | relevant passages in the top 5 ÷ 5 (divided by *k*, so returning fewer is penalised) |
| **MRR** | mean of 1 ÷ rank of the first relevant hit |
| **nDCG@5** | log₂-discounted gain ÷ the best achievable ranking |

Three decisions make the numbers defensible rather than decorative:

1. **A curated golden set** ships in `services/evaluation/golden_set.json` — ten
   hand-written cases across single-hop, multi-hop, and comparison difficulty.
   The dashboard shows every case, so a reviewer can read what is being asked
   before trusting a score.
2. **A real Recall denominator.** The runner scans the project's whole indexed
   corpus with the case's own relevance rule to count how many relevant
   passages exist, instead of assuming one per question.
3. **Unsupported cases are excluded, not zeroed.** If a case's evidence does
   not exist in the project at all, the retriever never had a chance to find
   it; the case is reported as "not in this corpus" and kept out of the
   averages.

Relevance uses a documented keyword proxy (a passage must contain every term a
case declares, after punctuation and case are normalised) because MAIROS ships
no human chunk-level labels — the policy is named in the UI rather than passed
off as a human judgment. A case can instead declare `source_documents` for
exact document-level labels, which take priority when present.

**When RAGAS is unavailable** — it is an optional dependency — the dashboard
says so plainly, lists the four answer-quality metrics it *would* compute, and
shows an em dash instead of a number. Retrieval metrics need no LLM and are
unaffected. Install with `pip install "ragas>=0.2,<1"` to enable the rest.

---

## End-to-end demo flow

1. Create a project.
2. **Search a topic** *or* **upload a PDF** (Search & Upload tab).
3. The Orchestrator routes: topic → Literature agent; PDF → Analysis agent.
4. Retrieved/analysed content is chunked and embedded into ChromaDB.
5. The Knowledge Graph agent adds nodes and edges.
6. The Citation agent produces APA references.
7. Ask a question in **Chat & Q&A** → RAG retrieves and answers with inline
   citations and the source passages beneath.

Watch every step live in the **Agent Activity** tab — which agent ran, at what
stage, what it produced — and see the accumulated graph in **Knowledge Graph**.

The full demonstration sequence, including the research workflows and the
evaluation dashboard, is in **[docs/DEMONSTRATION.md](docs/DEMONSTRATION.md)**.

---

## Stage 1 UI/UX

A usability pass over the working system above — no new agents, no schema
changes to the working flows, no visual redesign. The goal was to make the
existing pipeline easy to follow, not to change what it does.

- **Navigation** — the sidebar now covers all five areas (Projects,
  Workspace, Tasks, Knowledge Graph, Evaluation) with the active page always
  highlighted. Workspace and Knowledge Graph are project-scoped, so they
  deep-link into the current project (or send you to pick one).
- **Project Overview** — the workspace header shows documents, indexed
  chunks, papers discovered, graph nodes/edges, and a running/completed/
  failed task breakdown at a glance (`GET /projects/{id}/stats` now returns
  `task_counts`).
- **Upload & search** — PDF upload shows real transfer progress (an
  `XMLHttpRequest` progress event, not a simulated bar) followed by a live
  compact pipeline trace tied to the background task; both actions surface
  explicit success/error banners, and an empty project shows a short
  "get started" prompt instead of two silent empty cards.
- **Algorithm trace** — a new ordered stage tracker (Router → Retrieval/
  Analysis → Indexing → Knowledge Graph → Citation → Synthesis) sits above
  the existing chronological event log in the Tasks view, with per-stage
  status colours/icons derived only from real `TaskEvent`s — a stage outside
  the task's actual flow reads "not in this flow" rather than stuck pending.
- **Citations** — both Chat and Tasks now show a retrieval score and a
  numbered, left-accented card per citation, with a "show full passage"
  toggle instead of a hard 3-line clamp.
- **Knowledge graph legend** — always shows all known entity types (not just
  the ones currently present), and `Person` reads as **Author** in the UI
  while the API/graph schema is untouched. `Patent` is now an allowed entity
  type, reserved for a future patent-analysis agent.
- **System-state notices** — a reusable `SystemNotice` component reports
  offline/demo LLM mode (sidebar, header, and Chat) and carries a
  ready-to-use patent-research disclaimer ("Research-support only. Not
  legal advice or a patentability assessment.") that renders wherever a
  `Patent`-type node is selected.
- **Evaluation** — a new page reports the real state of the RAGAS scaffold
  (`GET /evaluation/status`): whether `ragas` is installed, whether a golden
  set is configured, and the four metric names — with no invented scores,
  since none have been computed yet.

None of this touches `services/`, the agent flows, or the API contracts
documented above — every endpoint in [API reference](#api-reference) still
means what it meant before; `stats` and `evaluation/status` are additive.

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Status + which LLM provider is live |
| `POST` | `/api/projects` | Create a project |
| `GET` | `/api/projects` | List projects (bare array) |
| `GET` | `/api/projects/{id}` | Project detail + documents |
| `DELETE` | `/api/projects/{id}` | Delete a project |
| `GET` | `/api/projects/{id}/export?format=zip\|json&include_originals=` | Download all project data (chunks, graph, tasks, evaluation, patents; PDFs optional) |
| `GET` | `/api/projects/{id}/stats` | Document / paper / graph counts |
| `GET` | `/api/projects/{id}/papers` | Papers found by the Literature agent |
| `POST` | `/api/projects/{id}/documents` | Upload a PDF (returns `task_id`) |
| `POST` | `/api/projects/{id}/query` | RAG: answer + grounding passages |
| `POST` | `/api/projects/{id}/retrieve` | Retrieval only, no generation |
| `POST` | `/api/projects/{id}/chat` | Streaming answer (SSE) |
| `POST` | `/api/projects/{id}/tasks` | Run the multi-agent pipeline (any registered `flow`) |
| `GET` | `/api/flows` | Registered flows and the agents each one runs |
| `GET` | `/api/tasks` · `/api/tasks/{id}` | Task list / live state |
| `GET` | `/api/projects/{id}/graph` | Knowledge graph as JSON |
| `DELETE` | `/api/projects/{id}/graph` | Reset the graph |
| `GET` | `/api/evaluation/status` | What can and cannot be measured right now |
| `GET` | `/api/evaluation/golden-set` | The curated test cases and their relevance rules |
| `POST` | `/api/projects/{id}/evaluation/run` | Recall@k, MRR, Precision@k, nDCG@k for this project |
| `GET` | `/api/patents/sources` | Allowlisted public registries + disclaimer |
| `GET` · `POST` | `/api/projects/{id}/patents` | List / add a patent (manual text + metadata) |
| `GET` · `PATCH` · `DELETE` | `/api/projects/{id}/patents/{patent_id}` | One patent with its segmentation / edit it / remove it |
| `GET` | `/api/projects/{id}/patents/findings` | Computed, scored overlaps for the project — no model involved |
| `GET` | `/api/projects/{id}/patents/findings/export?format=markdown\|csv` | Download findings, full disclaimer in the file body |

The research workflows are driven through `POST /api/projects/{id}/tasks` with
`flow` set to `compare`, `gaps`, `hypothesis`, `experiment`, `patent`,
`novelty`, or `review` — one entry point for every agent pipeline, which is
what keeps the orchestrator the only thing that decides what runs. `GET
/api/flows` reads the same registry, so a new flow appears in the UI without a
frontend change.

### Try it with curl

```bash
BASE=http://localhost:8000/api

PID=$(curl -s -X POST $BASE/projects -H 'Content-Type: application/json' \
      -d '{"name":"Demo"}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Topic search — the Router picks the "search" flow
TASK=$(curl -s -X POST $BASE/projects/$PID/tasks -H 'Content-Type: application/json' \
       -d '{"question":"retrieval augmented generation for scientific QA"}' \
       | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

sleep 20 && curl -s $BASE/tasks/$TASK | python -m json.tool

# Upload a PDF — forces the "analyze" flow
curl -s -X POST $BASE/projects/$PID/documents -F "file=@paper.pdf"

# Ask a grounded question
curl -s -X POST $BASE/projects/$PID/query -H 'Content-Type: application/json' \
     -d '{"question":"How does RAG reduce hallucination?"}' | python -m json.tool

curl -s $BASE/projects/$PID/graph | python -m json.tool

# Research workflows — same endpoint, different flow
curl -s -X POST $BASE/projects/$PID/tasks -H 'Content-Type: application/json' \
     -d '{"question":"compare these papers","flow":"compare"}'
curl -s -X POST $BASE/projects/$PID/tasks -H 'Content-Type: application/json' \
     -d '{"question":"what is still open?","flow":"experiment"}'

# Retrieval quality
curl -s -X POST $BASE/projects/$PID/evaluation/run -H 'Content-Type: application/json' \
     -d '{"k":5}' | python -m json.tool

# Patent awareness — text is pasted, never fetched
curl -s -X POST $BASE/projects/$PID/patents -H 'Content-Type: application/json' \
     -d '{"title":"Example","url":"https://patents.google.com/patent/US1234567B2/en",
          "text":"dense retrieval over an embedding index"}'
curl -s -X POST $BASE/projects/$PID/tasks -H 'Content-Type: application/json' \
     -d '{"question":"any overlap?","flow":"patent"}'
```

---

## Repository layout

```
mairos/
├── .env.example                # copy to .env
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── main.py             # entry point (uvicorn main:app)
│   │   ├── app/
│   │   │   ├── bootstrap.py    # sys.path setup for the monorepo
│   │   │   ├── config.py       # pydantic-settings
│   │   │   ├── store.py        # projects/documents/papers/patents/tasks (cached)
│   │   │   ├── db.py           # SQLite or Supabase Postgres behind one surface
│   │   │   ├── auth.py         # optional Better Auth JWT verification + isolation
│   │   │   ├── dependencies.py # singletons (Chroma, orchestrator, generation)
│   │   │   └── routers/        # projects, ingest, query, chat, graph, tasks, patents, evaluation
│   │   ├── Dockerfile          # Fly.io image (build from repo root)
│   │   └── data/               # chroma/, graphs/, uploads/, mairos.db (gitignored)
│   └── web/                    # Next.js 14 + Tailwind v4 + shadcn/ui
│       └── src/
│           ├── app/            # routes
│           ├── components/     # AppShell, SearchUpload, ChatPanel,
│           │                   # AgentActivity, GraphViewer, ui/*
│           └── lib/api.ts      # typed API client
├── packages/shared-types/      # Pydantic schemas (the API contract)
├── services/
│   ├── agents/                 # orchestrator, router, and each agent
│   ├── ingestion/              # extractor, chunker, pipeline
│   ├── retrieval/              # vector_store, graph_retriever, hybrid, reranker
│   ├── knowledge_graph/        # entity_extractor, networkx_store
│   ├── generation/             # provider (LLM), llm (grounded answers)
│   ├── common/                 # tolerant JSON parsing for LLM output
│   ├── patents/                # allowlist, segmentation, scoring, findings, export, wording audit
│   └── evaluation/             # metrics, curated golden set, runner
├── tests/                      # 392 tests, fully offline
└── docs/
```

---

## Completed and deferred

**Completed** (all registered through the orchestrator, all with offline tests):

| # | Feature | Where |
|---|---|---|
| 1 | Evaluation dashboard — Recall@5, MRR, Precision@5, nDCG@5, curated golden set, transparent RAGAS handling | `services/evaluation/`, `/evaluation/*`, Evaluation page |
| 2 | Paper comparison with cited comparison tables | `agents/comparison.py`, flow `compare` |
| 3 | Evidence-based research gap detection | `agents/gaps.py`, flow `gaps` |
| 4 | Hypothesis generation chained to evidenced gaps | `agents/hypothesis.py`, flow `hypothesis` |
| 5 | Experiment design per hypothesis | `agents/experiment.py`, flow `experiment` |
| 6 | Safe patent awareness (manual text, allowlisted public links, standing disclaimer) | `agents/patent_awareness.py`, `services/patents/`, flow `patent` |
| 7 | Novelty checking — corpus coverage only, never a claim of novelty in the field | `agents/novelty.py`, flow `novelty` |
| 8 | Auto literature review — `search` chained into `comparison`, novelty and synthesis | flow `review` in `agents/router.py` |
| 9 | SQLite persistence with a one-time `state.json` migration | `app/db.py`, `app/store.py` |
| 10 | Frontend test suite and CI (Vitest + Testing Library + axe-core) | `apps/web/src/**/*.test.tsx`, `.github/workflows/ci.yml` |
| 11 | Baseline HTTP hardening — rate limits, body caps, configured CORS, structured logging, graceful outages | `app/middleware.py`, `app/errors.py` |
| 12 | Live-model validation harness and an honest results document | `scripts/live_validation.py`, `docs/RESULTS.md` |
| 13 | Patent awareness completed: claim segmentation, explainable scoring, metadata, dedicated page, Markdown/CSV export, printable view, disclaimer and wording audits | `services/patents/`, `/projects/{id}/patents` |
| 14 | Optional Better Auth sign-in with per-user project isolation | `apps/web/src/lib/auth.ts`, `apps/api/app/auth.py` |
| 15 | Supabase Postgres metadata store behind the unchanged store surface | `apps/api/app/db.py`, `infra/supabase/` |
| 16 | Cloudflare (OpenNext) frontend, Fly.io API container, optional GA4 | `apps/web/wrangler.jsonc`, `fly.toml`, `apps/api/Dockerfile`, `docs/DEPLOYMENT.md` |
| 17 | Project-wide data export: ZIP or JSON with provenance-preserving chunks, graph, tasks, latest evaluation, patents, optional original PDFs, README and SHA-256 manifest | `apps/api/app/export.py`, **Export data** in the workspace |
| 18 | Multi-source literature search (arXiv, OpenAlex, Semantic Scholar) with model-written queries, cross-source de-duplication and a coverage report | `services/literature/`, `agents/literature.py`, "What was searched" in every result |
| 19 | Project-description intake: paste a project, get related work, stated gaps and a coverage check of each contribution | `agents/intake.py`, flow `project`, **Review my project** workflow |

Earlier milestones: the mid-review MVP (RAG, knowledge graph, orchestrator,
four-panel UI) and the Stage 1 UI/UX pass documented above.

**Deferred, and why:**

| Deferred | Reason |
|---|---|
| GNN training over the knowledge graph | The graph is hundreds of nodes — far below where a learned model beats traversal. |
| Vectors in Supabase `pgvector` | ChromaDB on the Fly.io volume works and is tested; moving vectors is a retrieval change, not a deployment one. |
| Live patent-database integration | Would require fetching from commercial sources; the manual/allowlisted design is the safe subset. |
| Live-model benchmark and RAGAS numbers | The harness exists and runs; the figures need a run over 15–20 real papers with your model key, which was not done here. `docs/RESULTS.md` says so rather than estimating. |

### Where the next agent goes

| Planned feature | Where it goes |
|---|---|
| Research planning | `PlannerAgent` already exists — add `"planner"` to a flow. |
| Persistent memory across sessions | The SQLite store is in place; a memory agent would read prior tasks from the `tasks` table. |
| Neo4j instead of NetworkX | Reimplement `ProjectGraph`'s five methods; `GraphRetriever` keeps its interface. |
| Cross-encoder re-ranking | `CrossEncoderReranker` exists — pass it to `HybridRetriever(reranker=...)`. |

---

## Testing

```bash
cd mairos
python -m pytest -q            # 652 backend tests (+9 Postgres, skipped without a test DB)
python -m pytest tests/test_agents.py -v

# Run the store contract against a real Postgres too:
MAIROS_TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_database_contract.py

cd apps/web && npm test        # 144 frontend tests (Vitest + Testing Library)
npx tsc --noEmit && npm run build
```

The suite is fully offline: no API key, no model download, no network. A
hashing embedder replaces sentence-transformers (it preserves relative
similarity, so retrieval ranking is actually asserted), the offline chat model
replaces Groq, and every literature source is stubbed with a recorded-shape
response (arXiv Atom, OpenAlex and Semantic Scholar JSON) so the parsing is
really exercised. A shared fixture refuses all outbound connections, so no test
can reach a real service by accident.

| File | Covers |
|---|---|
| `test_api.py` | All endpoints; the full search and analyze flows end to end |
| `test_agents.py` | Routing, APA formatting, entity extraction, graph store |
| `test_ingestion.py` | PDF extraction, chunking, ingest → retrieve |
| `test_literature.py` | arXiv parsing, indexing fetched papers |
| `test_literature_sources.py` | OpenAlex and Semantic Scholar parsing, the link allowlist, cross-source merging and ranking, query planning (model and rules), the coverage report, rate-limited and unreachable sources |
| `test_project_flow.py` | The Intake agent's grounding rule, project-description routing, and the `project` flow end to end through the API |
| `test_agent_token_cap.py` | Agent replies cut off at the output token cap are retried once with a larger budget |
| `test_review_fixes.py` | One regression test per finding of the independent review of literature search and project review |
| `test_evaluation.py` | Metric arithmetic against hand-worked values, golden-set relevance rules, runner behaviour, evaluation API |
| `test_workflows.py` | Evidence linking, flow registration, the research workflows, patent safety boundary, end-to-end flow runs |
| `test_novelty.py` | The novelty boundary (corpus coverage may be claimed, field novelty never is), the `review` chain, router changes |
| `test_persistence.py` | Restart durability, the one-time `state.json` migration, concurrent writes |
| `test_security.py` | Body caps, rate limits, CORS configuration, request logging, outage handling |
| `test_theme_contrast.py` | WCAG AA contrast of every theme token, computed from `globals.css` |
| `test_live_validation.py` | The live-run harness itself, against a fake HTTP client |
| `test_patents.py` | Claim segmentation variants, score components and ordering, metadata and migration, families, no-match, fabricated model overlaps, exports, the disclaimer on every route, the legal-wording audit, frontend/backend copy parity |
| `test_auth.py` | Real Ed25519 JWTs: bad tokens refused, cross-user access is 404 everywhere, task and project lists scoped, rate-limit keying |
| `test_database_contract.py` | One contract for SQLite and Postgres; backend selection; `DATA_DIR` relocation |
| `test_project_lifecycle.py` | Deletion cascade (memory and database), upload storage naming, the empty-project evidence boundary |
| `test_entity_names.py` | Typographic hyphens and spaces in graph names: folding rules, extractor, store writes and lookups, graph retrieval, merging graphs saved earlier |
| `test_kg_extraction_budget.py` | The empty-graph failure diagnosed live, replayed offline: per-call extraction budget, replies cut off at the token cap, entity salvage, and the run explaining itself |
| `test_project_export.py` | Export contents and caveats, chunk provenance, no truncation past 2,000 chunks, manifest hashes, originals byte-for-byte, JSON format, cross-project and cross-user isolation |

The workflow tests assert MAIROS's own guarantees rather than model output: a
comparison cell no passage supports is dropped, a gap whose quote cannot be
located is dropped, a hypothesis attached to no gap is dropped, an experiment
with no deciding metric is dropped, and a model that returns a fabricated
patent overlap cannot get it into the report.

---

## Known limits

- **Auth is opt-in.** In local mode projects are namespaced but unprotected;
  with auth on they are isolated per user (see above).
- **Persistence is SQLite** (`apps/api/data/mairos.db`) by default, written one
  row per mutation with WAL enabled, or Supabase Postgres via `DATABASE_URL`.
  An existing `state.json` is imported once on first start and then left alone.
- **The deployment path is built and tested piecewise, not deployed.** The
  Cloudflare bundle builds, the Postgres store passes its contract against
  PostgreSQL 16, and JWT verification is tested with real signatures; an actual
  deploy needs your Cloudflare, Fly.io and Supabase accounts.
- **No OCR.** Scanned PDFs return HTTP 422 with an explanatory message.
- **Tasks run in-process** via FastAPI `BackgroundTasks`; a restart mid-run
  loses that run's progress.
- **Answer-quality metrics need RAGAS**, which is optional and not installed by
  default. Retrieval metrics are computed regardless; the dashboard states
  plainly which half is missing rather than showing a placeholder.
- **Relevance judgments are a documented keyword proxy**, not human labels.
  The policy is shown in the UI next to the scores, and a case can carry
  explicit document labels instead.
- **Other agents share the 1,400-token default.** Knowledge-graph extraction
  now has its own budget because a live call showed a reasoning model
  (`gpt-oss`) overrunning it. The other JSON-producing agents (analysis,
  comparison, gaps, hypotheses, experiments) have not been measured the same
  way; with a reasoning model, raising `LLM_MAX_TOKENS` is the safe default.
- **Workflow quality tracks the model.** In offline mode, comparisons, gaps,
  hypotheses, and experiment designs are derived deterministically from the
  retrieved text, so they are conservative and repetitive by design. The
  validation rules (drop what cannot be cited) hold either way.
- **Patent awareness is wording overlap, not legal analysis.** It locates shared
  wording to a claim and scores it; it cannot construe a claim, and absence of
  an overlap is not clearance. Segmentation is pattern-based: an unusual
  numbering scheme falls back to whole-text matching, and says so.
