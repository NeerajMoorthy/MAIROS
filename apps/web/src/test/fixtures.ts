import type {
  Citation,
  ComparisonResult,
  EvalReport,
  EvaluationStatus,
  ExperimentResult,
  GapResult,
  GoldenSetResponse,
  HypothesisResult,
  LiteratureCoverage,
  NoveltyResult,
  Project,
  ProjectBrief,
  ProjectDetail,
  ProjectStats,
  RetrievalResult,
  Task,
  TaskEvent,
  TaskResult,
} from "@/lib/api";

export const aProject = (overrides: Partial<Project> = {}): Project => ({
  id: "p1",
  name: "Retrieval survey",
  description: "A project about RAG",
  created_at: "2026-09-01T10:00:00Z",
  document_ids: ["d1"],
  paper_ids: [],
  num_documents: 1,
  num_papers: 0,
  ...overrides,
});

export const aProjectDetail = (overrides: Partial<ProjectDetail> = {}): ProjectDetail => ({
  ...aProject(),
  documents: [
    {
      id: "d1",
      filename: "attention.pdf",
      title: "Attention Is All You Need",
      num_pages: 9,
      num_chunks: 42,
      ingested_at: "2026-09-01T10:05:00Z",
    },
  ],
  ...overrides,
});

export const someStats = (overrides: Partial<ProjectStats> = {}): ProjectStats => ({
  documents: 1,
  papers: 2,
  chunks: 42,
  graph: { nodes: 12, edges: 9 },
  tasks: 3,
  task_counts: { queued: 0, running: 1, completed: 2, failed: 0 },
  ...overrides,
});

export const anEvent = (overrides: Partial<TaskEvent> = {}): TaskEvent => ({
  task_id: "t1",
  timestamp: "2026-09-01T10:10:00Z",
  agent_name: "orchestrator",
  stage: "orchestrating",
  status: "running",
  message: "Task accepted",
  ...overrides,
});

export const aCitation = (overrides: Partial<Citation> = {}): Citation => ({
  document_id: "d1",
  chunk_id: "c1",
  document_name: "attention.pdf",
  text: "Self-attention lets the model weigh every position at once, which removes the sequential dependency recurrence imposes on training.",
  page: 3,
  score: 0.82,
  ...overrides,
});

export const aSource = (overrides: Partial<RetrievalResult> = {}): RetrievalResult => ({
  chunk_id: "c1",
  document_id: "d1",
  document_name: "attention.pdf",
  page: 3,
  text: "Retrieval augmented generation grounds answers in retrieved passages and reduces hallucination in open domain question answering.",
  score: 0.77,
  graph_hit: true,
  ...overrides,
});

export const aTaskResult = (overrides: Partial<TaskResult> = {}): TaskResult => ({
  answer: "Retrieval grounds the answer in the source text [attention.pdf, p. 3].",
  citations: [aCitation()],
  references: ["Vaswani, A. (2017). Attention Is All You Need. arXiv."],
  papers: [],
  analysis: null,
  routing: {
    flow: "answer",
    agents: ["retriever", "synthesis", "citation"],
    reason: "Question can be answered from the indexed library.",
    decided_by: "heuristic",
  },
  graph_stats: { nodes: 12, edges: 9 },
  agent_trace: [],
  comparison: null,
  gaps: null,
  hypotheses: null,
  experiments: null,
  patent_awareness: null,
  novelty: null,
  ...overrides,
});

export const aCoverage = (overrides: Partial<LiteratureCoverage> = {}): LiteratureCoverage => ({
  searched_on: "2026-10-22",
  queries: [
    { text: "retrieval-augmented question answering", written_by: "rules" },
    { text: "open-domain QA with a retriever", written_by: "model" },
  ],
  query_note: "",
  sources: [
    { source: "arxiv", name: "arXiv", status: "ok", returned: 2, detail: "" },
    { source: "openalex", name: "OpenAlex", status: "ok", returned: 4, detail: "" },
    {
      source: "semantic_scholar",
      name: "Semantic Scholar",
      status: "rate_limited",
      returned: 0,
      detail: "The service asked MAIROS to slow down (HTTP 429). Set SEMANTIC_SCHOLAR_API_KEY to raise the limit.",
    },
  ],
  records_returned: 6,
  papers_found: 4,
  papers_kept: 4,
  duplicates_merged: 2,
  papers_by_source: { arXiv: 2, OpenAlex: 3 },
  year_range: [2017, 2020],
  full_text_read: false,
  warnings: [
    "Semantic Scholar did not answer, so this search covers arXiv, OpenAlex only.",
    "Only 4 paper(s) were found. That is too few for a gap or 'not found' result to say much about the field — broaden the topic or add papers by hand.",
  ],
  scope_note:
    "This is a targeted search of paper titles and abstracts, not a systematic review. Full texts were not read, and work outside these sources, or phrased differently from these queries, may be missing.",
  ...overrides,
});

export const aProjectBrief = (overrides: Partial<ProjectBrief> = {}): ProjectBrief => ({
  title: "Retrieval-augmented question answering for course notes",
  problem: "Students struggle to find answers in long lecture notes, and manual search is slow.",
  domain: "",
  methods: ["dense passage retrieval"],
  datasets: [],
  goals: ["We will evaluate it on questions written by teaching assistants."],
  contributions: [
    "We propose a retrieval-augmented generation system that answers questions from the course notes with citations.",
  ],
  keywords: ["retrieval-augmented question answering", "dense passage retrieval"],
  search_text: "Retrieval-augmented question answering for course notes.",
  extracted_by: "model",
  dropped_ungrounded: 2,
  note: "",
  ...overrides,
});

export const aTask = (overrides: Partial<Task> = {}): Task => ({
  id: "t1",
  project_id: "p1",
  request: "How does retrieval reduce hallucination?",
  flow: "answer",
  document_id: null,
  status: "completed",
  current_stage: "completed",
  created_at: "2026-09-01T10:09:00Z",
  updated_at: "2026-09-01T10:11:00Z",
  events: [anEvent(), anEvent({ agent_name: "retriever", stage: "retrieving", status: "completed", message: "5 chunks retrieved" })],
  result: aTaskResult(),
  error: null,
  ...overrides,
});

export const aFailedTask = (): Task =>
  aTask({
    id: "t-failed",
    status: "failed",
    current_stage: "failed",
    result: null,
    error: "RuntimeError: the vector store is unreachable",
    events: [anEvent({ status: "failed", message: "Task aborted" })],
  });

export const aComparison = (overrides: Partial<ComparisonResult> = {}): ComparisonResult => ({
  sources: [
    { key: "S1", document_id: "d1", document_name: "attention.pdf", chunk_count: 2 },
    { key: "S2", document_id: "d2", document_name: "rag.pdf", chunk_count: 2 },
  ],
  dimensions: ["Focus of the work"],
  rows: [
    {
      dimension: "Focus of the work",
      cells: [
        {
          source_key: "S1",
          document_name: "attention.pdf",
          value: "Parallel sequence processing with self-attention.",
          citation: {
            chunk_id: "c1",
            document_id: "d1",
            document_name: "attention.pdf",
            page: 1,
            quote: "The transformer relies on self attention to process sequences in parallel.",
          },
        },
      ],
    },
  ],
  agreements: [],
  contradictions: [],
  gaps: [],
  uncited_cells_dropped: 2,
  ...overrides,
});

export const someGaps = (overrides: Partial<GapResult> = {}): GapResult => ({
  gaps: [
    {
      id: "GAP1",
      gap: "Memory cost limits long sequences.",
      kind: "stated_limitation",
      source_document: "attention.pdf",
      evidence_quote: "memory grows quadratically with sequence length",
      citation: {
        chunk_id: "c1",
        document_id: "d1",
        document_name: "attention.pdf",
        page: 4,
        quote: "memory grows quadratically with sequence length",
      },
    },
  ],
  graph_signals: [
    {
      signal: "under_represented_concepts",
      detail: "Mentioned by only one source in this project.",
      entities: ["Curriculum Pretraining"],
    },
  ],
  ...overrides,
});

export const someHypotheses = (overrides: Partial<HypothesisResult> = {}): HypothesisResult => ({
  hypotheses: [
    {
      id: "HYP1",
      statement: "Sparse attention keeps accuracy while cutting memory.",
      rationale: "Follows from the stated quadratic memory limitation.",
      testable_prediction: "Matches dense attention within one point at half the memory.",
      grounded_in_gap: "GAP1",
      gap_text: "Memory cost limits long sequences.",
      citation: {
        chunk_id: "c1",
        document_id: "d1",
        document_name: "attention.pdf",
        page: 4,
        quote: "memory grows quadratically with sequence length",
      },
    },
  ],
  ...overrides,
});

export const someExperiments = (overrides: Partial<ExperimentResult> = {}): ExperimentResult => ({
  experiments: [
    {
      id: "EXP1",
      hypothesis_id: "HYP1",
      hypothesis: "Sparse attention keeps accuracy while cutting memory.",
      objective: "Test whether sparse attention matches dense attention at half the memory.",
      datasets: ["WikiText-103"],
      baselines: ["Dense transformer"],
      metrics: ["Perplexity"],
      procedure: ["Reproduce the baseline", "Swap in sparse attention", "Compare perplexity"],
      controls: ["Identical splits and seeds"],
      threats_to_validity: ["Baseline may not reproduce"],
    },
  ],
  ...overrides,
});

export const anEvaluationStatus = (
  overrides: Partial<EvaluationStatus> = {},
): EvaluationStatus => ({
  status: "ready",
  retrieval_metrics_available: true,
  retrieval_metrics: ["recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"],
  answer_metrics_available: false,
  answer_metrics_reason: "ragas_not_installed_and_no_live_llm",
  answer_metrics_note:
    "Answer-quality metrics need both the optional `ragas` package and a live LLM; neither is configured.",
  ragas_installed: false,
  llm_live: false,
  golden_set_configured: true,
  golden_set_size: 10,
  golden_set_name: "MAIROS core retrieval golden set",
  relevance_policy: "term_match",
  metrics: ["faithfulness", "answer_relevancy", "context_precision", "context_recall"],
  note: "RAGAS is not installed.",
  ...overrides,
});

export const aGoldenSet = (overrides: Partial<GoldenSetResponse> = {}): GoldenSetResponse => ({
  metadata: { notes: "Curated by hand for the demo corpus." },
  size: 1,
  cases: [
    {
      id: "rag-001",
      question: "How does retrieval-augmented generation reduce hallucination?",
      expected_answer: "Retrieving passages grounds the answer in source text.",
      required_entities: ["retrieval", "hallucination"],
      source_documents: [],
      difficulty: "single-hop",
      tags: ["rag"],
      policy: "term_match",
    },
  ],
  ...overrides,
});

export const anEvalReport = (overrides: Partial<EvalReport> = {}): EvalReport => ({
  k: 5,
  project_id: "p1",
  corpus_chunks: 42,
  golden_set: { size: 10, path: "golden_set.json", name: "MAIROS core retrieval golden set" },
  aggregates: { recall_at_5: 0.8, precision_at_5: 0.32, mrr: 0.75, ndcg_at_5: 0.77, cases_evaluated: 4 },
  ragas: {
    available: false,
    metrics: ["faithfulness", "answer_relevancy", "context_precision", "context_recall"],
    scores: null,
    per_case: [],
    judged_by: null,
    reason: "ragas_not_installed_and_no_live_llm",
    note: "Answer-quality metrics need both the optional `ragas` package and a live LLM.",
    kind: "model_judged",
  },
  cases: [
    {
      id: "rag-001",
      question: "How does retrieval-augmented generation reduce hallucination?",
      difficulty: "single-hop",
      tags: ["rag"],
      policy: "term_match",
      supported: true,
      note: "",
      relevant_in_corpus: 2,
      retrieved: [
        {
          chunk_id: "c1",
          document_name: "rag.pdf",
          page: 2,
          score: 0.81,
          relevant: true,
          snippet: "Retrieval grounds answers and reduces hallucination.",
        },
      ],
      metrics: { recall_at_5: 0.5, precision_at_5: 0.2, reciprocal_rank: 1.0, ndcg_at_5: 0.63 },
    },
    {
      id: "kg-001",
      question: "How can a knowledge graph support retrieval?",
      difficulty: "multi-hop",
      tags: ["knowledge-graph"],
      policy: "term_match",
      supported: false,
      note: "No passage in this project satisfies the case's relevance rule. Excluded from the aggregates.",
      relevant_in_corpus: 0,
      retrieved: [],
      metrics: {},
    },
  ],
  cases_total: 2,
  cases_evaluated: 1,
  cases_unsupported: 1,
  ...overrides,
});

export const aNoveltyReport = (overrides: Partial<NoveltyResult> = {}): NoveltyResult => ({
  scope: "2 document(s) retrieved from this project",
  field_novelty: "not_assessed",
  uncited_notes_dropped: 1,
  limits:
    "These verdicts describe coverage within 2 document(s) retrieved from this project. " +
    "'Not found in this project's sources' means MAIROS found no supporting passage in what " +
    "it searched — it is not a finding of originality, and it does not become one by being repeated.",
  assessments: [
    {
      claim: "Self-attention processes sequences in parallel.",
      origin: "question",
      verdict: "covered_in_corpus",
      verdict_label: "Already covered by this project's sources",
      corpus_overlap: 0.82,
      field_novelty: "not_assessed",
      field_novelty_reason:
        "Novelty in the field was not assessed. MAIROS compared this claim against 2 document(s) " +
        "retrieved from this project only. Establishing that nothing in the published record " +
        "anticipates a claim requires a systematic search MAIROS has not performed, so no " +
        "statement about novelty in the field can be made from this evidence.",
      nearest_prior_work: [
        {
          document_name: "attention.pdf",
          note: "Closest passage in the corpus by wording overlap.",
          citation: {
            chunk_id: "c1",
            document_id: "d1",
            document_name: "attention.pdf",
            page: 1,
            quote: "The transformer relies on self attention to process sequences in parallel.",
          },
        },
      ],
    },
    {
      claim: "Quantum annealing improves ribosome kinetics.",
      origin: "hypothesis",
      verdict: "not_found_in_corpus",
      verdict_label: "Not found in this project's sources",
      corpus_overlap: 0,
      field_novelty: "not_assessed",
      field_novelty_reason:
        "Novelty in the field was not assessed. MAIROS compared this claim against 2 document(s) " +
        "retrieved from this project only.",
      nearest_prior_work: [],
    },
  ],
  ...overrides,
});
