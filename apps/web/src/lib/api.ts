/**
 * Typed client for the MAIROS FastAPI backend.
 *
 * All requests go to the relative `/api` path; `next.config.js` rewrites that
 * to the FastAPI backend (127.0.0.1:8000 locally, Fly.io in production), so
 * there is no CORS preflight and no base URL to configure in the browser.
 *
 * When authentication is enabled every request carries a Better Auth bearer
 * token (see `authToken.ts`); a 401 sends the browser to sign in.
 */

import { authHeaders, clearApiToken, redirectToSignIn } from "@/lib/authToken";
import { AUTH_ENABLED } from "@/lib/config";

const BASE = "/api";

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  document_ids: string[];
  paper_ids: string[];
  num_documents: number;
  num_papers: number;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  title: string | null;
  num_pages: number;
  num_chunks: number;
  ingested_at: string;
}

export interface ProjectDetail extends Project {
  documents: DocumentSummary[];
}

export interface Paper {
  id: string;
  project_id: string;
  title: string;
  authors: string[];
  abstract: string;
  year: string;
  url: string;
  pdf_url: string;
  source: string;
  /** Every source that returned this paper (arXiv, OpenAlex, Semantic Scholar). */
  sources?: string[];
  doi?: string;
  venue?: string;
  citation_count?: number | null;
  reference: string;
  added_at: string;
}

export interface RetrievalResult {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page: number | null;
  text: string;
  score: number;
  graph_hit: boolean;
}

export interface QueryAnswer {
  question: string;
  answer: string;
  results: RetrievalResult[];
  graph_context: { entity: string; relation: string; related_entity: string }[];
  /** The agent run (answer flow) that produced this answer; see Agent Activity. */
  task_id?: string | null;
}

export interface TaskEvent {
  task_id: string;
  timestamp: string;
  agent_name: string;
  stage: string;
  status: string;
  message: string;
}

export interface Citation {
  document_id: string;
  chunk_id: string;
  document_name: string;
  text: string;
  page: number | null;
  score: number | null;
}

/** A passage that supports a generated claim. */
export interface EvidenceCitation {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page: number | null;
  quote: string;
}

export interface ComparisonCell {
  source_key: string;
  document_name: string;
  value: string;
  citation: EvidenceCitation;
}

export interface ComparisonRow {
  dimension: string;
  cells: ComparisonCell[];
}

export interface ComparisonResult {
  sources: { key: string; document_id: string; document_name: string; chunk_count: number }[];
  dimensions: string[];
  rows: ComparisonRow[];
  agreements: { claim: string; sources: string[] }[];
  contradictions: {
    claim: string;
    positions: { document_name: string; position: string; citation: EvidenceCitation | null }[];
  }[];
  gaps: string[];
  uncited_cells_dropped?: number;
  note?: string;
}

export interface FlowInfo {
  name: string;
  agents: string[];
  description: string;
}

/** Research Gap Detection — every gap carries the passage it came from. */
export interface ResearchGap {
  id: string;
  gap: string;
  kind: string;
  source_document: string;
  citation: EvidenceCitation | null;
  evidence_quote: string;
}

export interface GapResult {
  gaps: ResearchGap[];
  graph_signals: { signal: string; detail: string; entities: string[] }[];
  note?: string;
}

/** Hypothesis Generation — each hypothesis is tied to a detected gap. */
export interface Hypothesis {
  id: string;
  statement: string;
  rationale: string;
  testable_prediction: string;
  grounded_in_gap: string;
  gap_text: string;
  citation: EvidenceCitation | null;
}

export interface HypothesisResult {
  hypotheses: Hypothesis[];
  note?: string;
}

/** Experiment Design — one protocol per hypothesis. */
export interface ExperimentDesign {
  id: string;
  hypothesis_id: string;
  hypothesis: string;
  objective: string;
  datasets: string[];
  baselines: string[];
  metrics: string[];
  procedure: string[];
  controls: string[];
  threats_to_validity: string[];
}

export interface ExperimentResult {
  experiments: ExperimentDesign[];
  note?: string;
}

/** Patent awareness — research-support only, never a legal assessment. */
export interface PatentMetadata {
  /** Publication number (kept under its original field name). */
  number: string;
  application_number: string;
  family_id: string;
  cpc_codes: string[];
  ipc_codes: string[];
  assignee: string;
  inventors: string[];
  /** ISO dates (YYYY-MM-DD) or null. */
  priority_date: string | null;
  filing_date: string | null;
  publication_date: string | null;
}

export interface PatentRecord extends PatentMetadata {
  id: string;
  project_id: string;
  title: string;
  url: string;
  text: string;
  source: string;
  added_at: string;
  updated_at?: string | null;
  segmented?: boolean;
  claim_count?: number;
  warnings?: string[];
  disclaimer?: string;
}

/** What a user types into the patent form; dates as YYYY-MM-DD strings. */
export interface PatentInput {
  title: string;
  text?: string;
  url?: string;
  number?: string;
  application_number?: string;
  family_id?: string;
  cpc_codes?: string[];
  ipc_codes?: string[];
  assignee?: string;
  inventors?: string[];
  priority_date?: string;
  filing_date?: string;
  publication_date?: string;
}

export interface PatentSection {
  id: string;
  kind: "abstract" | "description" | "claim" | "document";
  label: string;
  text: string;
  start: number;
  end: number;
  number: number | null;
  independent: boolean | null;
  depends_on: number[];
  unresolved_references: number[];
}

export interface PatentSegmentation {
  segmented: boolean;
  notes: string[];
  claim_count: number;
  independent_claims: number[];
  dependent_claims: number[];
  sections: PatentSection[];
}

export interface PatentDetail {
  disclaimer: string;
  patent: PatentRecord;
  segmentation: PatentSegmentation;
}

/** Why a finding scored what it did. Similarity of wording — nothing more. */
export interface ScoreComponents {
  term_rarity: number;
  phrase_length: number;
  section_weight: number;
  corpus_chunks: number;
  chunks_containing_term: number;
  phrase_words: number;
  occurrences_in_section: number;
}

export interface PatentOverlap {
  patent_id: string;
  patent_title: string;
  patent_number: string;
  patent_url: string;
  patent_family_id?: string;
  concept: string;
  overlap: string;
  matched_terms: string[];
  citation: EvidenceCitation | null;
  // Present on every finding produced since claim-level scoring; optional so
  // task results stored by the earlier build still render.
  score?: number;
  score_label?: string;
  components?: ScoreComponents;
  section?: {
    id: string;
    kind: PatentSection["kind"];
    label: string;
    number: number | null;
    independent: boolean | null;
    depends_on: number[];
    excerpt: string;
  };
  also_in?: string[];
}

export interface PatentAwarenessResult {
  disclaimer: string;
  full_disclaimer?: string;
  patents_checked: number;
  concepts_checked: number;
  corpus_chunks?: number;
  overlaps: PatentOverlap[];
  summary?: string;
  note?: string;
  notes?: string[];
  score_label?: string;
  score_explanation?: string;
  section_weights?: Record<string, number>;
  patents?: {
    patent_id: string;
    title: string;
    number: string;
    family_id: string;
    segmented: boolean;
    segmentation_notes: string[];
    claim_count: number;
    findings: number;
  }[];
}

/**
 * Novelty — coverage within THIS project's corpus.
 *
 * `field_novelty` is typed as the literal `"not_assessed"` on purpose: there is
 * no value the backend can send that would let the UI render a claim of
 * novelty in the field, and TypeScript will reject any attempt to add one.
 */
export interface NoveltyPriorWork {
  document_name: string;
  note: string;
  citation: EvidenceCitation;
}

export interface NoveltyAssessment {
  claim: string;
  origin: "hypothesis" | "question" | "project";
  verdict: "covered_in_corpus" | "partially_covered" | "not_found_in_corpus";
  verdict_label: string;
  corpus_overlap: number;
  nearest_prior_work: NoveltyPriorWork[];
  field_novelty: "not_assessed";
  field_novelty_reason: string;
}

export interface NoveltyResult {
  scope: string;
  assessments: NoveltyAssessment[];
  field_novelty: "not_assessed";
  uncited_notes_dropped?: number;
  limits?: string;
  note?: string;
}

/** One literature source's part in a search. */
export interface CoverageSource {
  source: "arxiv" | "openalex" | "semantic_scholar";
  name: string;
  status: "ok" | "failed" | "rate_limited";
  returned: number;
  detail: string;
}

/**
 * What a literature search looked at — computed from the search, never
 * written by a model. Rendered beside the results it qualifies.
 */
export interface LiteratureCoverage {
  searched_on: string;
  queries: { text: string; written_by: "rules" | "model" }[];
  query_note: string;
  sources: CoverageSource[];
  records_returned: number;
  papers_found: number;
  papers_kept: number;
  duplicates_merged: number;
  papers_by_source: Record<string, number>;
  year_range: [number, number] | null;
  full_text_read: false;
  warnings: string[];
  scope_note: string;
}

/** A pasted project description, read into a brief. */
export interface ProjectBrief {
  title: string;
  problem: string;
  domain: string;
  methods: string[];
  datasets: string[];
  goals: string[];
  contributions: string[];
  keywords: string[];
  search_text: string;
  extracted_by: "rules" | "model";
  dropped_ungrounded: number;
  note: string;
}

export interface TaskResult {
  answer: string;
  citations: Citation[];
  references: string[];
  papers: Record<string, unknown>[];
  analysis: Record<string, unknown> | null;
  routing: { flow: string; agents: string[]; reason: string; decided_by: string } | null;
  graph_stats: { nodes: number; edges: number } | null;
  agent_trace: string[];
  comparison: ComparisonResult | null;
  gaps: GapResult | null;
  hypotheses: HypothesisResult | null;
  experiments: ExperimentResult | null;
  patent_awareness: PatentAwarenessResult | null;
  novelty: NoveltyResult | null;
  literature_coverage?: LiteratureCoverage | null;
  project_brief?: ProjectBrief | null;
}

export interface Task {
  id: string;
  project_id: string;
  request: string;
  flow: string | null;
  document_id: string | null;
  status: "queued" | "running" | "completed" | "failed";
  current_stage: string;
  created_at: string;
  updated_at: string;
  events: TaskEvent[];
  result: TaskResult | null;
  error: string | null;
}

export interface GraphNode {
  id: string;
  name: string;
  group: string;
  description: string;
  mentions: number;
  val: number;
}

export interface GraphLink {
  source: string;
  target: string;
  label: string;
  confidence: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats: { nodes: number; edges: number };
}

export interface HealthInfo {
  status: string;
  version: string;
  llm: { provider: string; model: string; live: boolean };
  projects: number;
}

export interface TaskCounts {
  queued: number;
  running: number;
  completed: number;
  failed: number;
}

export interface ProjectStats {
  documents: number;
  papers: number;
  chunks: number;
  graph: { nodes: number; edges: number };
  tasks: number;
  task_counts: TaskCounts;
}

export interface EvaluationStatus {
  status: "ready" | "no_golden_set";
  retrieval_metrics_available: boolean;
  retrieval_metrics: string[];
  /** True only when RAGAS is installed *and* a live model can judge answers. */
  answer_metrics_available: boolean;
  answer_metrics_reason: string;
  answer_metrics_note: string;
  ragas_installed: boolean;
  llm_live: boolean;
  golden_set_configured: boolean;
  golden_set_size: number;
  golden_set_name: string;
  relevance_policy: string;
  metrics: string[];
  note: string;
}

/** Model-judged answer quality — never a computed quantity. */
export interface AnswerQuality {
  available: boolean;
  metrics: string[];
  scores: Record<string, number> | null;
  per_case: Record<string, unknown>[];
  judged_by: string | null;
  reason: string;
  note: string;
  kind: "model_judged";
}

export interface GoldenCase {
  id: string;
  question: string;
  expected_answer: string;
  required_entities: string[];
  source_documents: string[];
  difficulty: string;
  tags: string[];
  policy: "term_match" | "document_label";
}

export interface GoldenSetResponse {
  metadata: Record<string, unknown>;
  size: number;
  cases: GoldenCase[];
}

export interface EvalRetrievedItem {
  chunk_id: string;
  document_name: string;
  page: number | null;
  score: number;
  relevant: boolean;
  snippet: string;
}

export interface EvalCaseResult {
  id: string;
  question: string;
  difficulty: string;
  tags: string[];
  policy: string;
  supported: boolean;
  note: string;
  relevant_in_corpus: number;
  retrieved: EvalRetrievedItem[];
  metrics: Record<string, number>;
}

export interface EvalReport {
  k: number;
  project_id: string;
  corpus_chunks: number;
  golden_set: { size: number; path: string; name?: string; relevance_policy?: string; notes?: string };
  /** A metric is null when no case could be scored: nothing was measured. */
  aggregates: Record<string, number | null>;
  ragas: AnswerQuality;
  cases: EvalCaseResult[];
  cases_total: number;
  cases_evaluated: number;
  cases_unsupported: number;
}

/** Thrown for any non-2xx response, carrying the backend's `detail` message. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    /** Seconds the server asked us to wait, from `Retry-After` (429 / 503). */
    public retryAfterSeconds: number | null = null,
    /** The server's correlation id, so a report can be matched to a log line. */
    public requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /**
   * Whether retrying the same request could plausibly succeed.
   *
   * 0 is an unreachable backend, 429 is the rate limiter, 503 is a dependency
   * outage — all temporary. A 4xx is the caller's own fault and retrying it
   * unchanged just burns rate budget, so those are not transient.
   */
  get isTransient(): boolean {
    return this.status === 0 || this.status === 429 || this.status === 503;
  }
}

const UNREACHABLE = "Cannot reach the MAIROS backend. Is it running on port 8000?";

async function send(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(await authHeaders())) headers.set(key, value);

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }

  if (response.status === 401 && AUTH_ENABLED) {
    // The token expired or was revoked: drop it and go and get a new one.
    clearApiToken();
    redirectToSignIn();
  }
  if (!response.ok) await throwFor(response);
  return response;
}

async function throwFor(response: Response): Promise<never> {
  let detail = `Request failed (${response.status})`;
  let requestId = response.headers.get("X-Request-ID");
  try {
    const body = await response.json();
    if (body?.detail) detail = String(body.detail);
    if (body?.request_id) requestId = String(body.request_id);
  } catch {
    /* non-JSON error body */
  }

  const retryAfter = Number(response.headers.get("Retry-After"));
  throw new ApiError(
    detail,
    response.status,
    Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    requestId,
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Fetch a file from the API and hand it to the browser as a download. */
async function download(path: string, fallbackName: string): Promise<string> {
  const response = await send(path);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoke after the click has been handled, not synchronously.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return filename;
}

function json(body: unknown, method = "POST"): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  health: () => request<HealthInfo>("/health"),

  // -- Projects -------------------------------------------------------
  listProjects: () => request<Project[]>("/projects"),
  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  createProject: (name: string, description = "") =>
    request<Project>("/projects", json({ name, description })),
  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: "DELETE" }),
  projectStats: (id: string) => request<ProjectStats>(`/projects/${id}/stats`),
  /** Download all of a project's data. Originals are ZIP-only. */
  exportProject: (id: string, format: "zip" | "json", includeOriginals = false) =>
    download(
      `/projects/${id}/export?format=${format}${
        format === "zip" && includeOriginals ? "&include_originals=true" : ""
      }`,
      `project-export.${format}`,
    ),
  listPapers: (id: string) => request<Paper[]>(`/projects/${id}/papers`),

  // -- Ingestion ------------------------------------------------------
  uploadDocument: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{
      document_id: string;
      filename: string;
      num_pages: number;
      num_chunks: number;
      task_id: string | null;
    }>(`/projects/${projectId}/documents`, { method: "POST", body: form });
  },

  // -- RAG ------------------------------------------------------------
  query: (projectId: string, question: string, topK = 5) =>
    request<QueryAnswer>(
      `/projects/${projectId}/query`,
      json({ question, top_k: topK }),
    ),

  // -- Multi-agent tasks ----------------------------------------------
  createTask: (projectId: string, question: string, flow?: string) =>
    request<Task>(`/projects/${projectId}/tasks`, json({ question, flow })),
  listFlows: () => request<{ flows: FlowInfo[] }>("/flows"),
  listTasks: (projectId?: string) =>
    request<Task[]>(projectId ? `/projects/${projectId}/tasks` : "/tasks"),
  getTask: (taskId: string) => request<Task>(`/tasks/${taskId}`),

  // -- Knowledge graph ------------------------------------------------
  getGraph: (projectId: string) =>
    request<GraphData>(`/projects/${projectId}/graph`),
  clearGraph: (projectId: string) =>
    request<void>(`/projects/${projectId}/graph`, { method: "DELETE" }),

  // -- Patents (manual entry; MAIROS never fetches patent documents) ----
  patentSources: () =>
    request<{
      disclaimer: string;
      full_disclaimer: string;
      fetches_documents: boolean;
      sources: { domain: string; name: string }[];
      notes: string[];
    }>("/patents/sources"),
  listPatents: (projectId: string) =>
    request<{ disclaimer: string; full_disclaimer?: string; patents: PatentRecord[] }>(
      `/projects/${projectId}/patents`,
    ),
  getPatent: (projectId: string, patentId: string) =>
    request<PatentDetail>(`/projects/${projectId}/patents/${patentId}`),
  addPatent: (projectId: string, patent: PatentInput) =>
    request<PatentRecord>(`/projects/${projectId}/patents`, json(patent)),
  updatePatent: (projectId: string, patentId: string, changes: Partial<PatentInput>) =>
    request<PatentRecord>(`/projects/${projectId}/patents/${patentId}`, json(changes, "PATCH")),
  deletePatent: (projectId: string, patentId: string) =>
    request<void>(`/projects/${projectId}/patents/${patentId}`, { method: "DELETE" }),
  /** Computed findings for the project's current patents — no model involved. */
  patentFindings: (projectId: string) =>
    request<PatentAwarenessResult>(`/projects/${projectId}/patents/findings`),
  /** Download findings; the file itself carries the full disclaimer. */
  exportPatentFindings: (projectId: string, format: "markdown" | "csv") =>
    download(
      `/projects/${projectId}/patents/findings/export?format=${format}`,
      format === "csv" ? "patent-findings.csv" : "patent-findings.md",
    ),

  // -- Evaluation -------------------------------------------------------
  evaluationStatus: () => request<EvaluationStatus>("/evaluation/status"),
  evaluationGoldenSet: () => request<GoldenSetResponse>("/evaluation/golden-set"),
  runEvaluation: (projectId: string, k = 5, answerQuality = false) =>
    request<EvalReport>(
      `/projects/${projectId}/evaluation/run`,
      json({ k, answer_quality: answerQuality }),
    ),

  // -- Upload with real progress (fetch has no upload-progress event) ---
  uploadDocumentWithProgress: async (
    projectId: string,
    file: File,
    onProgress: (percent: number) => void,
  ) => {
    const auth = await authHeaders();
    return new Promise<{
      document_id: string;
      filename: string;
      num_pages: number;
      num_chunks: number;
      task_id: string | null;
    }>((resolve, reject) => {
      const form = new FormData();
      form.append("file", file);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/projects/${projectId}/documents`);
      for (const [key, value] of Object.entries(auth)) xhr.setRequestHeader(key, value);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };
      xhr.onload = () => {
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* non-JSON body */
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body as never);
        } else {
          if (xhr.status === 401 && AUTH_ENABLED) {
            clearApiToken();
            redirectToSignIn();
          }
          const detail =
            body && typeof body === "object" && "detail" in body
              ? String((body as { detail: unknown }).detail)
              : `Upload failed (${xhr.status})`;
          reject(new ApiError(detail, xhr.status));
        }
      };
      xhr.onerror = () => reject(new ApiError(UNREACHABLE, 0));
      xhr.send(form);
    });
  },
};

/** Human-readable label for an agent name or pipeline stage. */
export function humanise(value: string): string {
  return value
    .split(/[_\s]+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export const STAGES = [
  "queued",
  "orchestrating",
  "extracting",
  "retrieving",
  "embedding",
  "analyzing",
  "building_graph",
  "generating_citations",
  "completed",
] as const;

/**
 * The six canonical pipeline stages, in order, as named in the MAIROS
 * agent design: Router -> Retrieval/Analysis -> Indexing -> Knowledge
 * Graph -> Citation -> Synthesis. Each stage lists every real agent name
 * (see services/agents/router.py's FLOWS) whose events belong to it, so the
 * tracker is derived from real TaskEvents — nothing here is invented.
 */
export const PIPELINE_STAGES = [
  { key: "router", label: "Router", agents: ["orchestrator"] },
  { key: "retrieval", label: "Retrieval / Analysis", agents: ["literature", "retriever", "analysis", "loader"] },
  { key: "indexing", label: "Indexing", agents: ["indexer"] },
  { key: "knowledge_graph", label: "Knowledge Graph", agents: ["knowledge_graph"] },
  // Research workflows added after the mid-review. Flows that do not include
  // one of these agents show this stage as "not in this flow".
  {
    key: "research",
    label: "Research workflow",
    agents: ["comparison", "gaps", "hypothesis", "experiment", "patent_awareness", "novelty"],
  },
  { key: "citation", label: "Citation", agents: ["citation"] },
  { key: "synthesis", label: "Synthesis", agents: ["synthesis"] },
] as const;

export type PipelineStageKey = (typeof PIPELINE_STAGES)[number]["key"];
