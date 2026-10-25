import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";
import { pathToFileURL } from "node:url";

const REPO = "C:/Users/moort/SEM THREE/AI_ML/Project/mairos";
const BUILD_DIR = `${REPO}/tmp/presentation-build-20261013`;
const SKILL_DIR = "C:/Users/moort/.codex/plugins/cache/openai-primary-runtime/presentations/26.1011.11113/skills/presentations";
const DRAFT = `${BUILD_DIR}/MAIROS_Project_Walkthrough_draft.pptx`;
const PREVIEW_DIR = `${BUILD_DIR}/rendered`;

const C = {
  bg: "#F7F8F5",
  ink: "#172623",
  body: "#354741",
  muted: "#65756F",
  accent: "#007F73",
  accent2: "#C65D36",
  line: "#CBD5D0",
  pale: "#E7EFEB",
  white: "#FFFFFF",
};
const FONT = "Arial";
const W = 1280;
const H = 720;
const LEFT = 76;
const CONTENT_W = 1128;
const TOTAL = 16;

await fs.mkdir(BUILD_DIR, { recursive: true });
await fs.mkdir(PREVIEW_DIR, { recursive: true });

const { makeNativeBulletParagraphs } = await import(pathToFileURL(
  path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs"),
).href);

const deck = Presentation.create({ slideSize: { width: W, height: H } });

function textbox(slide, name, text, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: 24,
    color: C.body,
    alignment: "left",
    verticalAlignment: "top",
    wrap: "square",
    autoFit: "none",
    insets: 0,
    lineSpacing: 1.08,
    ...style,
  };
  return shape;
}

function bulletBlock(slide, name, items, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = makeNativeBulletParagraphs(items, {
    marginLeftPoints: 20,
    hangingPoints: 10,
    spaceAfterPoints: 10,
  });
  shape.text.style = {
    typeface: FONT,
    fontSize: 23,
    color: C.body,
    alignment: "left",
    verticalAlignment: "top",
    wrap: "square",
    autoFit: "none",
    insets: 0,
    lineSpacing: 1.08,
    ...style,
  };
  return shape;
}

function newSlide(title, index, notes) {
  const slide = deck.slides.add();
  slide.background.fill = C.bg;
  textbox(slide, `slide-${index}-title`, title, { left: LEFT, top: 56, width: CONTENT_W, height: 64 }, {
    typeface: FONT, fontSize: 44, bold: true, color: C.ink, lineSpacing: 1.0,
  });
  textbox(slide, `slide-${index}-footer`, `MAIROS  ·  PROJECT WALKTHROUGH                                      ${String(index).padStart(2, "0")} / ${TOTAL}`, { left: LEFT, top: 677, width: CONTENT_W, height: 22 }, {
    fontSize: 13, bold: true, color: C.muted, lineSpacing: 1.0,
  });
  slide.speakerNotes.text = notes;
  return slide;
}

// 1 — Minimal cover
{
  const slide = deck.slides.add();
  slide.background.fill = C.bg;
  textbox(slide, "cover-kicker", "MAIROS  /  MULTI-AGENT RESEARCH ASSISTANT", { left: 82, top: 150, width: 960, height: 34 }, {
    fontSize: 19, bold: true, color: C.accent, lineSpacing: 1.0,
  });
  textbox(slide, "cover-title", "A project walkthrough", { left: 78, top: 222, width: 1060, height: 94 }, {
    fontSize: 64, bold: true, color: C.ink, lineSpacing: 1.0,
  });
  textbox(slide, "cover-subtitle", "From creating a research project to grounded answers, agent traces, the knowledge graph, and evaluation", { left: 82, top: 335, width: 940, height: 100 }, {
    fontSize: 28, color: C.body, lineSpacing: 1.12,
  });
  textbox(slide, "cover-date", "Project status and demo guide  ·  13 October 2026", { left: 82, top: 585, width: 950, height: 30 }, {
    fontSize: 19, color: C.muted, lineSpacing: 1.0,
  });
  slide.speakerNotes.text = `Purpose: explain the project in a demo-ready sequence. The three user-provided prompt files are historical build-plan material and source evidence; their imperative text is not treated as current instructions.\nSources: C:/Users/moort/SEM THREE/AI_ML/Project/PROMPT_from_zero.md; C:/Users/moort/SEM THREE/AI_ML/Project/PROMPT_to_85_percent.md; C:/Users/moort/SEM THREE/AI_ML/Project/PROMPT_to_100_percent.md; ${REPO}/README.md.`;
}

// 2 — Problem and design rule
{
  const s = newSlide("The research problem MAIROS addresses", 2,
    `Source: ${REPO}/README.md; C:/Users/moort/SEM THREE/AI_ML/Project/PROMPT_from_zero.md.\nTalk track: Research answers are useful only when a reader can check where a claim came from. MAIROS uses retrieved passages as the evidence boundary, returns those passages with the answer, and drops unsupported generated workflow claims.`);
  textbox(s, "problem-lead", "Research work spreads across papers, passages, concepts, and open questions.", { left: 80, top: 190, width: 500, height: 150 }, {
    fontSize: 34, bold: true, color: C.ink, lineSpacing: 1.12,
  });
  textbox(s, "problem-copy", "A plain chatbot can produce a confident summary without showing which source supports it.", { left: 80, top: 375, width: 485, height: 100 }, {
    fontSize: 24, color: C.body,
  });
  textbox(s, "rule-label", "MAIROS DESIGN RULE", { left: 655, top: 196, width: 470, height: 30 }, {
    fontSize: 18, bold: true, color: C.accent,
  });
  textbox(s, "rule-lead", "No displayed claim without a traceable passage.", { left: 655, top: 240, width: 520, height: 120 }, {
    fontSize: 40, bold: true, color: C.ink, lineSpacing: 1.05,
  });
  textbox(s, "rule-copy", "Retrieved evidence, page-level citations, and explicit uncertainty make the answer auditable. If the corpus does not support an answer, MAIROS says so.", { left: 655, top: 395, width: 520, height: 145 }, {
    fontSize: 24, color: C.body,
  });
}

// 3 — Complete lifecycle
{
  const s = newSlide("One research run, from project to evidence", 3,
    `Source: ${REPO}/README.md; ${REPO}/docs/DEMONSTRATION.md.\nExplain the sequence as the user's single end-to-end test case. Each step creates data that the next step uses. The project contains separate workflows, but they share ingestion, retrieval, evidence and task tracing.`);
  textbox(s, "lifecycle", "Create project  →  Search or upload  →  Extract and chunk\n\nEmbed and index  →  Orchestrate agents  →  Return cited output\n\nReview the task trace  →  Inspect the graph  →  Evaluate retrieval", { left: 84, top: 190, width: 1100, height: 260 }, {
    fontSize: 31, bold: true, color: C.ink, alignment: "center", lineSpacing: 1.15,
  });
  textbox(s, "lifecycle-note", "Persistent project data includes document metadata, indexed chunks, graph structure, and task history. The answer includes its grounding passages so the evidence can be checked.", { left: 180, top: 505, width: 920, height: 85 }, {
    fontSize: 24, color: C.body, alignment: "center",
  });
}

// 4 — Architecture
{
  const s = newSlide("System architecture", 4,
    `Source: ${REPO}/README.md (Architecture; How RAG is wired in; How the knowledge graph is wired in).\nThe workflow decision is made by a registry-based router. ChromaDB is embedded; the per-project NetworkX graph is stored as JSON; project metadata is stored in SQLite. Groq is optional because an offline deterministic model is available.`);
  textbox(s, "architecture", "Next.js + TypeScript interface\n↓  REST requests\nFastAPI project and workflow API\n↓\nRouter + registry-based agent orchestrator\n↓\nChromaDB vectors  ·  NetworkX project graph  ·  SQLite metadata\n↓\nGroq language model  /  deterministic offline fallback", { left: 150, top: 155, width: 980, height: 420 }, {
    fontSize: 29, bold: true, color: C.ink, alignment: "center", lineSpacing: 1.1,
  });
  textbox(s, "architecture-note", "No Docker or separate database server is required for the local demo.", { left: 200, top: 605, width: 880, height: 30 }, {
    fontSize: 20, color: C.muted, alignment: "center",
  });
}

// 5 — Test project and corpus
{
  const s = newSlide("Test case setup: create a project and add sources", 5,
    `Source: ${REPO}/docs/DEMONSTRATION.md; ${REPO}/README.md; ${REPO}/output/pdf/e2e-rag-evaluation-source.pdf.\nDemo project name: RAG Literature Demo. Description: Evidence-grounded question answering on retrieval-augmented generation and scientific QA. The existing fixture is synthetic and intended to verify ingestion/evaluation deterministically. It is not a scholarly paper; use at least two real papers for comparison and gap analysis.`);
  textbox(s, "project-label", "PROJECT DETAILS", { left: 84, top: 168, width: 400, height: 28 }, {
    fontSize: 18, bold: true, color: C.accent,
  });
  textbox(s, "project-details", "Name\nRAG Literature Demo\n\nDescription\nEvidence-grounded question answering on retrieval-augmented generation and scientific QA.", { left: 84, top: 210, width: 500, height: 250 }, {
    fontSize: 25, color: C.ink, lineSpacing: 1.13,
  });
  textbox(s, "corpus-label", "CORPUS FOR THE TEST", { left: 670, top: 168, width: 500, height: 28 }, {
    fontSize: 18, bold: true, color: C.accent,
  });
  bulletBlock(s, "corpus-list", [
    "Topic search: retrieval-augmented generation for scientific question answering.",
    "Upload the 10-page synthetic fixture to verify PDF extraction and the 10-chunk path.",
    "Add two text-based research PDFs for paper comparison and literature workflows.",
  ], { left: 670, top: 210, width: 510, height: 300 }, { fontSize: 22 });
  textbox(s, "corpus-caveat", "Use the fixture for predictable ingestion and evaluation checks; do not present it as a research source.", { left: 670, top: 540, width: 510, height: 70 }, {
    fontSize: 20, italic: true, color: C.muted,
  });
}

// 6 — Topic search and Chat
{
  const s = newSlide("Topic search and Chat & Q&A", 6,
    `Sources: ${REPO}/docs/DEMONSTRATION.md; ${REPO}/services/evaluation/golden_set.json.\nExact golden-set question: “How does retrieval-augmented generation reduce hallucination?” Expected idea: retrieving relevant passages before generation grounds the answer in the source text. Check that the UI presents source/page and the retrieved passage. Search requires reachable arXiv for external discovery; local PDF upload remains the fallback.`);
  textbox(s, "search-label", "TOPIC SEARCH", { left: 86, top: 174, width: 470, height: 28 }, {
    fontSize: 18, bold: true, color: C.accent,
  });
  textbox(s, "search-prompt", "retrieval-augmented generation for scientific question answering", { left: 86, top: 221, width: 500, height: 160 }, {
    fontSize: 30, bold: true, color: C.ink,
  });
  textbox(s, "search-detail", "The Literature agent finds papers; Indexer adds their text to the project's searchable corpus.", { left: 86, top: 411, width: 500, height: 110 }, {
    fontSize: 23, color: C.body,
  });
  textbox(s, "chat-label", "CHAT & Q&A QUESTION", { left: 680, top: 174, width: 500, height: 28 }, {
    fontSize: 18, bold: true, color: C.accent,
  });
  textbox(s, "chat-prompt", "How does retrieval-augmented generation reduce hallucination?", { left: 680, top: 221, width: 510, height: 130 }, {
    fontSize: 29, bold: true, color: C.ink,
  });
  textbox(s, "chat-check", "Expected idea: retrieve relevant source passages before generation. Verify the answer's citation and open its supporting passage.", { left: 680, top: 390, width: 510, height: 135 }, {
    fontSize: 23, color: C.body,
  });
}

// 7 — Compare papers
{
  const s = newSlide("Compare papers", 7,
    `Source: ${REPO}/README.md (research workflows); ${REPO}/docs/DEMONSTRATION.md.\nEnter the exact prompt shown. The comparison should use two or more actual papers in the project. Each supported table cell should carry a citation; unsupported cells should be omitted and counted rather than guessed. The synthetic fixture is not a paper and should not be used as one of the comparison documents.`);
  textbox(s, "compare-label", "PROMPT TO ENTER", { left: 84, top: 164, width: 400, height: 28 }, {
    fontSize: 18, bold: true, color: C.accent,
  });
  textbox(s, "compare-prompt", "Compare these papers across their research question, method, datasets, reported results, and stated limitations. Cite every cell; omit any cell the sources do not support.", { left: 84, top: 210, width: 1090, height: 190 }, {
    fontSize: 31, bold: true, color: C.ink, lineSpacing: 1.13,
  });
  textbox(s, "compare-output", "Expected output: a dimension-by-paper table. Each visible cell links to its source passage; missing evidence stays blank or is reported as unsupported.", { left: 84, top: 455, width: 1000, height: 100 }, {
    fontSize: 24, color: C.body,
  });
  textbox(s, "compare-prereq", "Prerequisite: at least two papers with overlapping subject matter.", { left: 84, top: 592, width: 1050, height: 32 }, {
    fontSize: 20, bold: true, color: C.accent2,
  });
}

// 8 — Gaps
{
  const s = newSlide("Detect research gaps", 8,
    `Sources: ${REPO}/README.md (gap detection and knowledge graph); ${REPO}/docs/DEMONSTRATION.md.\nThe workflow quotes paper-stated limitations. The Knowledge Graph can add separate coverage signals, such as a concept appearing in only one paper or methods the corpus never compares. Those signals describe this project's corpus; they are not proof that a field-wide gap exists.`);
  textbox(s, "gap-label", "PROMPT TO ENTER", { left: 84, top: 164, width: 400, height: 28 }, {
    fontSize: 18, bold: true, color: C.accent,
  });
  textbox(s, "gap-prompt", "Identify the explicitly stated open problems and limitations across these papers. Quote the sentence supporting each gap, and separate graph-derived coverage signals from paper-reported gaps.", { left: 84, top: 210, width: 1090, height: 190 }, {
    fontSize: 30, bold: true, color: C.ink, lineSpacing: 1.13,
  });
  textbox(s, "gap-output", "Read the two result types separately: quoted limitations are findings in the papers; graph signals are prompts for further reading.", { left: 84, top: 455, width: 1020, height: 100 }, {
    fontSize: 24, color: C.body,
  });
}

// 9 — Literature review
{
  const s = newSlide("Run a literature review", 9,
    `Sources: ${REPO}/README.md; ${REPO}/docs/DEMONSTRATION.md; ${REPO}/docs/MID_REVIEW_STATUS.md.\nThe review flow chains paper search, indexing, retrieval, comparison, project-scoped novelty coverage, graph update and synthesis. It is a bounded review of discovered and indexed material; it is not a systematic review and does not claim field-level novelty.`);
  textbox(s, "review-label", "PROMPT TO ENTER", { left: 84, top: 164, width: 400, height: 28 }, {
    fontSize: 18, bold: true, color: C.accent,
  });
  textbox(s, "review-prompt", "Review recent work on retrieval-augmented generation for scientific question answering. Find and index papers, compare methods and findings, surface evidence-backed gaps, and report what is new to this project. Do not claim field-level novelty.", { left: 84, top: 210, width: 1090, height: 205 }, {
    fontSize: 28, bold: true, color: C.ink, lineSpacing: 1.14,
  });
  textbox(s, "review-chain", "Search  →  Index  →  Retrieve  →  Compare  →  Check project coverage  →  Synthesize with citations", { left: 84, top: 485, width: 1090, height: 82 }, {
    fontSize: 24, bold: true, color: C.accent,
  });
}

// 10 — Task / Agent Activity
{
  const s = newSlide("Tasks and Agent Activity", 10,
    `Sources: ${REPO}/README.md (Tasks and workflows); ${REPO}/packages/shared-types/schemas.py (Task and TaskEvent schemas); ${REPO}/apps/web/src/components/AgentActivity.tsx.\nDefinition: a Task is a complete request/workflow run, with an id, project, request, flow, status, current stage, timestamps, events, result, and error. A TaskEvent is one dated agent/stage update. The Tasks view lets a user select the run; Agent Activity / pipeline detail explains progress inside it. Persisted task history can survive a restart, while in-process work can be interrupted by one.`);
  textbox(s, "task-definition-label", "TASK = THE WHOLE RUN", { left: 84, top: 177, width: 500, height: 32 }, {
    fontSize: 20, bold: true, color: C.accent,
  });
  textbox(s, "task-definition", "One accepted request, such as a question, paper search, upload analysis, comparison, or evaluation run.\n\nThe record tracks its project, flow, status, timestamps, result, and any error.", { left: 84, top: 225, width: 510, height: 245 }, {
    fontSize: 24, color: C.ink,
  });
  textbox(s, "event-definition-label", "AGENT ACTIVITY = THE STEPS", { left: 680, top: 177, width: 500, height: 32 }, {
    fontSize: 20, bold: true, color: C.accent,
  });
  textbox(s, "event-definition", "Timestamped events show which agent ran, what stage it reached, and its message or failure.\n\nUse the trace to see why a run completed, slowed down, or failed.", { left: 680, top: 225, width: 510, height: 245 }, {
    fontSize: 24, color: C.ink,
  });
  textbox(s, "task-summary", "One task can contain many agent events. The task answers “what happened to my request?”; the trace answers “what did each step do?”", { left: 160, top: 540, width: 960, height: 75 }, {
    fontSize: 23, bold: true, color: C.body, alignment: "center",
  });
}

// 11 — Knowledge graph
{
  const s = newSlide("Knowledge Graph", 11,
    `Source: ${REPO}/README.md (How the knowledge graph is wired in).\nThe graph is per project and persists to JSON. It stores paper, author, concept, and patent nodes plus typed edges such as AUTHORED_BY, USES, EXTENDS, COMPARES_TO, and EVALUATED_ON. Concepts link back to their source chunk ids, so graph traversal can boost relevant dense-retrieval results. A sparse graph is not evidence that no work exists outside this project.`);
  textbox(s, "graph-role", "A connected map of what this project's sources discuss.", { left: 84, top: 168, width: 1060, height: 70 }, {
    fontSize: 34, bold: true, color: C.ink,
  });
  textbox(s, "graph-example", "Paper  ── AUTHORED_BY ──  Author\n  │\n  └── USES / EXTENDS / EVALUATED_ON ──  Concept or method", { left: 120, top: 295, width: 700, height: 170 }, {
    fontSize: 29, bold: true, color: C.accent, lineSpacing: 1.25,
  });
  textbox(s, "graph-use", "WHY IT HELPS\n\nTraversal can surface related concepts and passages that a vector match alone may miss. Those passages are fused into retrieval; citations still point to source text.", { left: 850, top: 274, width: 330, height: 220 }, {
    fontSize: 23, color: C.body,
  });
  textbox(s, "graph-limit", "Graph coverage signals are scoped to the indexed project corpus; they are not field-wide conclusions.", { left: 120, top: 560, width: 1000, height: 54 }, {
    fontSize: 21, italic: true, color: C.muted,
  });
}

// 12 — Evaluation role and metrics
{
  const s = newSlide("Evaluation: what it measures", 12,
    `Sources: ${REPO}/README.md (Evaluation); ${REPO}/docs/RESULTS.md; ${REPO}/services/evaluation/golden_set.json.\nEvaluation checks retrieval ranking against ten curated questions and their required terms. It measures whether the retriever finds relevant chunks, not whether every generated answer is true or useful. Four deterministic IR metrics are computed without an LLM.`);
  textbox(s, "eval-question", "Is the retriever finding the evidence the project's questions need?", { left: 84, top: 150, width: 1090, height: 80 }, {
    fontSize: 31, bold: true, color: C.ink,
  });
  textbox(s, "metric-1", "Recall@5\nShare of relevant corpus passages found in the top five.", { left: 84, top: 276, width: 500, height: 115 }, {
    fontSize: 24, color: C.body,
  });
  textbox(s, "metric-2", "Precision@5\nRelevant results among the five returned passages.", { left: 665, top: 276, width: 500, height: 115 }, {
    fontSize: 24, color: C.body,
  });
  textbox(s, "metric-3", "MRR\nHow high the first relevant passage ranks, averaged over cases.", { left: 84, top: 435, width: 500, height: 115 }, {
    fontSize: 24, color: C.body,
  });
  textbox(s, "metric-4", "nDCG@5\nRanking quality with extra weight on relevant results near the top.", { left: 665, top: 435, width: 500, height: 115 }, {
    fontSize: 24, color: C.body,
  });
  textbox(s, "eval-limit", "These are retrieval metrics, not a model-quality grade.", { left: 84, top: 598, width: 1090, height: 30 }, {
    fontSize: 21, bold: true, color: C.accent2,
  });
}

// 13 — Evaluation flow and interpretation
{
  const s = newSlide("Evaluation: run and interpret it", 13,
    `Sources: ${REPO}/docs/DEMONSTRATION.md; ${REPO}/docs/RESULTS.md; ${REPO}/docs/MID_REVIEW_STATUS.md; ${REPO}/services/evaluation/golden_set.json.\nDemo: open Evaluation, select RAG Literature Demo, run evaluation, expand one case to inspect its returned passages and relevance decision. The golden set's required-entity matching is a transparent keyword proxy. Cases unsupported by the current corpus are excluded from aggregate metrics, not counted as retrieval failures. RAGAS metrics are optional and currently wired but not measured.`);
  bulletBlock(s, "eval-steps", [
    "Open Evaluation, choose the project, and run the ten-case golden set.",
    "Expand a case to inspect returned chunks and why a chunk counted as relevant.",
    "Compare Recall@5, Precision@5, MRR, and nDCG@5 across runs on the same corpus.",
  ], { left: 90, top: 170, width: 1060, height: 245 }, { fontSize: 25 });
  textbox(s, "eval-method", "Relevance is a keyword proxy: every required term must appear in a corpus chunk after case and punctuation normalization. It is not human relevance labelling.", { left: 100, top: 455, width: 1040, height: 83 }, {
    fontSize: 22, color: C.body,
  });
  textbox(s, "eval-caveat", "Unsupported cases are excluded. RAGAS answer-quality metrics need an optional package and live judge; no RAGAS score has been measured yet.", { left: 100, top: 565, width: 1040, height: 73 }, {
    fontSize: 21, italic: true, color: C.muted,
  });
}

// 14 — Other workflow and evidence limits
{
  const s = newSlide("Other workflows and their boundaries", 14,
    `Sources: ${REPO}/README.md (research workflows and safety notes); ${REPO}/docs/ROADMAP.md.\nNovelty means “covered by this project's sources,” never “novel in the field.” Patent awareness is only a manual text overlap prototype: it does not fetch documents, interpret claims, or give legal advice. Literature review is bounded to what it finds and retrieves, not a systematic review. These limits are product behavior, not footnotes.`);
  bulletBlock(s, "workflow-list", [
    "Hypotheses: falsifiable ideas attached to an evidence-backed gap.",
    "Experiment design: objective, data, baselines, deciding metric, steps, controls, and threats.",
    "Novelty: corpus coverage only; field-level novelty remains not assessed.",
    "Patent awareness: manual text and literal term overlap, with a research-only disclaimer.",
    "Literature review: cited synthesis of retrieved papers, not a systematic review.",
  ], { left: 92, top: 166, width: 1070, height: 390 }, { fontSize: 23 });
  textbox(s, "workflow-evidence-chain", "Evidence chain: passage  →  quoted gap  →  hypothesis  →  experiment", { left: 92, top: 589, width: 1070, height: 40 }, {
    fontSize: 22, bold: true, color: C.accent,
  });
}

// 15 — Progress since mid-semester
{
  const s = newSlide("Project progress since the mid-semester review", 15,
    `Sources: C:/Users/moort/SEM THREE/AI_ML/Project/PROMPT_to_85_percent.md; C:/Users/moort/SEM THREE/AI_ML/Project/PROMPT_to_100_percent.md; ${REPO}/docs/MID_REVIEW_STATUS.md; ${REPO}/docs/ROADMAP.md; ${REPO}/docs/RESULTS.md; ${REPO}/README.md.\nThe historical 85-percent prompt records a roughly 76-percent baseline and 183 offline tests. Current status documents report about 84-percent scope and 502 offline automated tests (392 backend + 110 frontend). Since the mid-review: frontend tests/CI, SQLite persistence, live-validation harness, optional RAGAS wiring, novelty and review flows, accessibility/responsive hardening and baseline HTTP security. Stage A live-model figures remain pending because outbound access to the embedding/model and arXiv hosts was unavailable. Stage B patent claim-level enhancements are roadmap work, not completed. Older prompt/roadmap snapshots list 105/108 frontend tests; this deck uses the latest README/status/results count of 110.`);
  textbox(s, "baseline-number", "≈76%", { left: 98, top: 183, width: 300, height: 86 }, {
    fontSize: 62, bold: true, color: C.muted, lineSpacing: 1.0,
  });
  textbox(s, "baseline-copy", "Mid-review baseline\n183 offline tests reported in the 85% build prompt", { left: 100, top: 280, width: 405, height: 90 }, {
    fontSize: 22, color: C.body,
  });
  textbox(s, "current-number", "≈84%", { left: 684, top: 183, width: 330, height: 86 }, {
    fontSize: 62, bold: true, color: C.accent, lineSpacing: 1.0,
  });
  textbox(s, "current-copy", "Latest documented status\n392 backend + 110 frontend = 502 offline tests", { left: 686, top: 280, width: 470, height: 90 }, {
    fontSize: 22, color: C.body,
  });
  bulletBlock(s, "progress-list", [
    "Added persistence, CI/frontend coverage, accessibility and HTTP hardening.",
    "Added project-scoped novelty and the chained literature review flow; connected RAGAS, without claiming measured scores.",
    "Still pending: a real live-model validation run. Advanced patent work remains in Stage B.",
  ], { left: 94, top: 425, width: 1080, height: 210 }, { fontSize: 21 });
}

// 16 — Demo close and export decision
{
  const s = newSlide("End-to-end demo checklist", 16,
    `Sources: ${REPO}/docs/DEMONSTRATION.md; ${REPO}/docs/ROADMAP.md; ${REPO}/output/pdf/e2e-rag-evaluation-source.pdf; ${REPO}/README.md.\nRun the demonstration in order: create RAG Literature Demo; search the RAG scientific QA topic; upload the synthetic ten-page fixture and verify the ten-chunk ingest; add two real text-based papers; ask the chat golden-set question; run compare, gaps, and literature review; inspect the selected Task's events and graph; finish with Evaluation. The full project test fixture is synthetic, while the compare and literature workflows require real source papers.\nProduct decision on data download: recommend a project export because it supports reproducibility and backup. Start with a ZIP containing a manifest plus JSON metadata/tasks/evaluation/graph and CSV extracted chunks; make original PDFs an explicit optional inclusion. Project-wide export is not documented as shipped in the current UI. The roadmap's planned export refers to the future dedicated Patents page. Treat this as a recommendation, not an implemented feature.`);
  bulletBlock(s, "demo-checklist", [
    "Create RAG Literature Demo; search the topic and upload the 10-page / 10-chunk synthetic fixture.",
    "Add two real RAG papers; ask the chat question; run comparison, gaps, and literature review.",
    "Inspect the whole Task and its agent events; open Knowledge Graph; run Evaluation last.",
  ], { left: 88, top: 158, width: 1080, height: 220 }, { fontSize: 23 });
  textbox(s, "export-question", "Should users be able to download extracted project data?", { left: 88, top: 425, width: 1080, height: 50 }, {
    fontSize: 29, bold: true, color: C.ink,
  });
  textbox(s, "export-answer", "Recommended: yes. Offer a project archive with metadata, tasks, graph, evaluation results, and extracted chunks; include original PDFs only by choice. It helps backup and reproducibility. This export is a proposal, not a current feature.", { left: 88, top: 493, width: 1080, height: 110 }, {
    fontSize: 22, color: C.body,
  });
}

async function saveBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

for (let i = 0; i < deck.slides.items.length; i += 1) {
  const slide = deck.slides.items[i];
  const png = await deck.export({ slide, format: "png", scale: 1 });
  await saveBlob(`${PREVIEW_DIR}/slide-${String(i + 1).padStart(2, "0")}.png`, png);
}
const montage = await deck.export({ format: "webp", montage: true, scale: 0.5 });
await saveBlob(`${BUILD_DIR}/montage.webp`, montage);
await (await PresentationFile.exportPptx(deck)).save(DRAFT);
console.log(JSON.stringify({ draft: DRAFT, slideCount: deck.slides.items.length, previews: PREVIEW_DIR, montage: `${BUILD_DIR}/montage.webp` }));
