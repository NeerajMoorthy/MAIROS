# Prompt — MAIROS from ~85% to 100%

Paste everything below the line into a fresh session that has the `mairos`
repository open.

---

Continue MAIROS development. The project is at roughly 85% of its full scope.
Stage A is implemented in full — frontend tests and CI, the live-validation
harness, RAGAS wiring, SQLite persistence, the Novelty agent and the `review`
flow, UX and accessibility hardening, and baseline HTTP hardening. 392 backend
tests and 105 frontend tests pass offline, TypeScript is clean under `strict`,
and the production build is green.

This stage finishes the project. It is mostly **patent awareness**, which was
deliberately left until last because it carries the most external and legal
sensitivity and benefits from a stable system underneath it.

## Read these first

Before writing any code, read `README.md`, `docs/ROADMAP.md` (Stage B),
`docs/RESULTS.md`, `services/agents/patent_awareness.py`,
`services/patents/sources.py`, `apps/api/app/routers/patents.py`, and
`apps/web/src/components/PatentManager.tsx`. The patent feature today is a
deliberately narrow safe subset and the reasons are written down; this stage
widens it without loosening any of them.

## Constraints that must not change

These are not preferences. Breaking any of them is a regression regardless of
what else improves.

**The patent boundary.** MAIROS never fetches a patent document — the text
analysed is always what the user pasted. Links stay allowlisted to free public
registries. Findings stay computed in Python, never generated. Nothing anywhere
in the feature — UI copy, exports, summaries, error messages — offers legal
advice, construes a claim, or assesses novelty, infringement, validity or
freedom to operate. Absence of an overlap is never reported as clearance.

**The evidence chain.** Nothing is displayed that cannot be traced to a
retrieved passage. A comparison cell, a gap, a hypothesis, an experiment field
or a novelty note that no source supports is dropped and counted, not shown.

**The novelty boundary.** `field_novelty` is the constant `"not_assessed"` and
no code path may set it to anything else. The Synthesis agent must never be
handed a novelty-framed question — `strip_question_framing` exists because a
model obeying every grounding rule will otherwise answer "this appears to be
novel" and cite a passage for it. Read `tests/test_novelty.py` before touching
anything in that chain.

**Honesty about measurement.** Do not fabricate, estimate or extrapolate a
result. If a run cannot be executed in the environment, produce the artifact
and say plainly that the numbers are pending, as `docs/RESULTS.md` already does.

**Infrastructure invariants added in Stage A.** `CORSMiddleware` stays
outermost so error responses remain readable by the browser. Metadata-store
readers keep taking the lock. Theme tokens keep passing
`tests/test_theme_contrast.py`. The request-size cap keeps metering the stream,
not just the `Content-Length` header.

## Still out of scope

Authentication, multi-user isolation, cloud deployment, Docker, and
learned/GNN models over the knowledge graph. These remain recorded as deferred
with reasons; do not start them.

## Implement in this exact order

After each item, run the full backend suite, the full frontend suite, and the
production build. Do not move on until all three are green.

```bash
python -m pytest -q
cd apps/web && npm test && npx tsc --noEmit && npm run build
```

### 1. Claim-level segmentation

Overlap currently matches against the patent's whole text, so a finding points
at a document rather than at anything specific. Segment a pasted patent into
its parts — abstract, description, and individually numbered claims — and
attach every overlap to the specific claim or section it came from.

Claim text in the wild is messy: numbering styles vary (`1.`, `[0001]`,
`Claim 1:`), claims wrap across lines, and dependent claims reference their
parents ("The system of claim 1, wherein…"). Handle independent and dependent
claims distinctly and record the dependency, because an overlap against a
dependent claim means something different from one against an independent
claim. Where segmentation fails, fall back to whole-document matching and say
so in the output rather than silently pretending the structure was found.

### 2. Weighted overlap scoring

Replace binary literal matching with a score that reflects how much a match is
worth, and show the reader why. At minimum: term rarity (a term that appears in
one chunk of the corpus is worth more than one that appears everywhere),
matched phrase length (a four-word phrase beats four scattered words), and
section weighting (a match in a claim outweighs one in the description).

Two things this must not become. It must not become a probability, a risk
level, or anything a reader could mistake for a legal assessment — it is a
similarity score and the UI must label it as one. And it must stay computed:
the model may phrase a summary of findings that already exist and nothing more.

Surface the components of the score, not just the total. A reader must be able
to see *why* an overlap ranked where it did.

### 3. Patent metadata

Capture on entry, and show alongside findings: publication and application
number, family, classification codes (CPC/IPC), assignee, inventors, priority
date, filing date, and publication date. All entered by hand — nothing is
fetched. Validate what can be validated locally (date ordering, classification
code shape, publication-number format) and accept what cannot, rather than
rejecting a legitimate entry because it did not match a pattern.

Extend the `Patent` schema, the store, and the API together, and keep existing
stored patents loading — there is a SQLite store now, so add a migration path
for records that predate the new fields rather than dropping them.

### 4. A dedicated Patents page

Move patent management out of the card inside the Workflows tab into a route of
its own, with a list view, a detail view per patent showing its segmented
claims and metadata, and the overlap findings against the current project.
Keep a way to launch the `patent` flow from there.

Follow the accessibility standard the rest of the app now meets: WCAG 2.1 AA,
keyboard operable, no horizontal overflow at 375px, every control with an
accessible name, visible focus on everything focusable. `apps/web/src/test/a11y.ts`
and the existing browser audit approach are there to be reused — add the new
page to them rather than checking it by eye.

### 5. Export

Let a researcher take findings out: at minimum Markdown and CSV, and a printable
view. Every export carries the full disclaimer in its own body — not as a
footnote, and not only in the UI that generated it. An exported file will be
read by someone who never saw the app, and it must not read as a legal opinion
to that person.

Include, for each finding: the project concept, the matched patent claim or
section with its number, the matched terms, the score and its components, and
the citation of the project passage the concept came from.

### 6. Disclaimer surface review

Audit every place a patent finding can reach a human — the Workflows tab, the
new Patents page, the API responses, every export format, the printable view,
error and empty states — and confirm the same wording appears in all of them.
Write a test that enumerates the entry points and fails when one is added
without the disclaimer, so this cannot rot.

### 7. Tests for the harder cases

Beyond the happy path: claim segmentation against several real-world numbering
and wrapping styles; dependent-claim resolution; overlapping patent families;
a patent whose text is a single unsegmentable blob; a patent with no overlap at
all (confirming absence is not reported as clearance); and a model that returns
a fabricated overlap, confirming it cannot reach the output.

Add one audit test that scans the rendered strings of the patent feature —
agent output, API responses, UI copy, exports — for language implying a legal
conclusion ("infringe", "violation", "clear to", "safe to", "patentable",
"invalid", "freedom to operate") and fails on any hit. That test is the
compiled form of the boundary this feature exists inside.

### 8. Final visual pass

The accessibility and responsive work is done; the visual design pass was
explicitly deferred. Do it now: consistent spacing and type scale, coherent
empty and loading states, and a look that holds together across the six panels
and the two standalone pages.

Do not regress accessibility to achieve it. Any colour change must keep
`tests/test_theme_contrast.py` passing — extend that file if new token pairings
are introduced.

### 9. Live-model validation, recorded

This is the one Stage A item that could not be completed in a sandbox: the
harness runs and is tested, but `huggingface.co` and `export.arxiv.org` are
unreachable there, so no figures exist.

If this session has outbound network access and a live `GROQ_API_KEY`, run it
and fill in section 2 of `docs/RESULTS.md` with the generated table, naming the
date, the model and the corpus:

```bash
python scripts/live_validation.py --corpus ~/papers \
    --out docs/results_data.json --markdown docs/results_summary.md
```

Also run one evaluation with `answer_quality: true` so the RAGAS figures stop
being hypothetical.

If the environment still cannot reach those hosts, do not fabricate the table.
Say so, leave it pending, and treat the project as 95% rather than 100% — the
harness existing is not the same as the measurement having been taken.

## Finally

Update `README.md`, `docs/MID_REVIEW_STATUS.md`, `docs/ROADMAP.md` and
`docs/RESULTS.md` with the new test counts and a revised completion estimate.
Change the student name to **Moorthy Neeraj** everywhere it appears, including
the mid-review PPTX deck.

Then have the work reviewed adversarially before calling it done — read the new
code looking for ways each guarantee could fail rather than confirming it
works, reproduce every finding before fixing it, and add a test for each. The
Stage A review found fourteen real defects that the passing suite had not
caught, including one where an agent's guarantee held and the flow around it
broke the same promise anyway. Record what it found in the README as that stage
did.

Confirm at the end which of the nine items are complete, which are partial and
why, and state the completion percentage you believe the project has actually
reached — with the reasoning, not just the number.
