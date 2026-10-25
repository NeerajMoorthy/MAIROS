"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  FlaskConical,
  Loader2,
  Play,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ApiError,
  api,
  type EvalCaseResult,
  type EvalReport,
  type EvaluationStatus,
  type GoldenSetResponse,
  type Project,
} from "@/lib/api";

const K = 5;

const METRIC_LABELS: Record<string, string> = {
  faithfulness: "Faithfulness",
  answer_relevancy: "Answer relevancy",
  context_precision: "Context precision",
  context_recall: "Context recall",
};

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-3xl font-semibold tabular-nums">{value}</p>
        <p className="mt-1 text-sm font-medium">{label}</p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

function pct(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(3);
}

function CaseRow({ result }: { result: EvalCaseResult }) {
  const [open, setOpen] = useState(false);
  const m = result.metrics;

  return (
    <li className="rounded-lg border">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="focus-ring flex w-full items-start gap-3 p-3 text-left hover:bg-accent/40"
        aria-expanded={open}
      >
        {result.supported ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
        ) : (
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <code className="text-xs text-muted-foreground">{result.id}</code>
            <Badge variant="outline" className="text-[10px]">
              {result.difficulty}
            </Badge>
            {!result.supported && (
              <Badge variant="secondary" className="text-[10px]">
                not in this corpus
              </Badge>
            )}
          </div>
          <p className="mt-1 text-sm">{result.question}</p>
          {result.supported ? (
            <div className="mt-2 flex flex-wrap gap-3 text-xs tabular-nums text-muted-foreground">
              <span>R@{K} {pct(m[`recall_at_${K}`])}</span>
              <span>P@{K} {pct(m[`precision_at_${K}`])}</span>
              <span>RR {pct(m.reciprocal_rank)}</span>
              <span>nDCG@{K} {pct(m[`ndcg_at_${K}`])}</span>
              <span>{result.relevant_in_corpus} relevant in corpus</span>
            </div>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">{result.note}</p>
          )}
        </div>
        <ChevronDown
          className={`mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="space-y-2 border-t p-3">
          {result.retrieved.length === 0 ? (
            <p className="text-xs text-muted-foreground">Nothing was retrieved for this question.</p>
          ) : (
            result.retrieved.map((item, index) => (
              <div
                key={item.chunk_id || index}
                className={`rounded-md border border-l-[3px] p-2.5 text-xs ${
                  item.relevant ? "border-l-success" : "border-l-muted-foreground/30"
                }`}
              >
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[10px] text-muted-foreground">#{index + 1}</span>
                  <span className="truncate font-medium">{item.document_name || "Untitled"}</span>
                  {item.page != null && (
                    <Badge variant="outline" className="text-[10px]">p. {item.page}</Badge>
                  )}
                  <Badge variant={item.relevant ? "success" : "secondary"} className="text-[10px]">
                    {item.relevant ? "relevant" : "not relevant"}
                  </Badge>
                </div>
                <p className="text-muted-foreground">{item.snippet}</p>
              </div>
            ))
          )}
        </div>
      )}
    </li>
  );
}

/** Evaluation dashboard — retrieval metrics computed live, nothing invented. */
export default function EvaluationPage() {
  const [status, setStatus] = useState<EvaluationStatus | null>(null);
  const [golden, setGolden] = useState<GoldenSetResponse | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [report, setReport] = useState<EvalReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCases, setShowCases] = useState(false);
  const [withAnswerQuality, setWithAnswerQuality] = useState(false);

  useEffect(() => {
    Promise.all([
      api.evaluationStatus(),
      api.evaluationGoldenSet(),
      api.listProjects(),
    ])
      .then(([statusInfo, goldenSet, projectList]) => {
        setStatus(statusInfo);
        setGolden(goldenSet);
        setProjects(projectList);
        if (projectList.length) setProjectId(projectList[0].id);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load evaluation status"),
      )
      .finally(() => setLoading(false));
  }, []);

  const run = useCallback(async () => {
    if (!projectId) return;
    setRunning(true);
    setError(null);
    try {
      setReport(await api.runEvaluation(projectId, K, withAnswerQuality));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Evaluation run failed");
    } finally {
      setRunning(false);
    }
  }, [projectId, withAnswerQuality]);

  const aggregates = report?.aggregates ?? {};

  return (
    <div className="mx-auto w-full max-w-5xl p-6 md:p-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Evaluation</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Retrieval quality measured against a curated golden set — Recall@{K}, MRR,
          Precision@{K}, and nDCG@{K}, computed from this project&apos;s own indexed chunks.
        </p>
      </header>

      {error && (
        <Card className="mb-6 border-destructive/50">
          <CardContent className="flex items-center gap-3 p-4 text-sm">
            <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
            <span>{error}</span>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Run controls */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Run an evaluation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {projects.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No projects yet. Create one and index a document first — metrics are
                  measured against a real corpus, so there is nothing to score until then.
                </p>
              ) : (
                <div className="flex flex-col gap-2 sm:flex-row">
                  <select
                    aria-label="Project to evaluate"
                    value={projectId}
                    onChange={(event) => {
                      setProjectId(event.target.value);
                      setReport(null);
                    }}
                    /*
                      `flex-1` is scoped to the row layout. In the stacked
                      column layout it applied to the main (vertical) axis, so
                      flex-basis:0 beat `h-9` and collapsed the control to 20px
                      tall — below the 24px minimum target size.
                    */
                    className="focus-ring h-9 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm sm:flex-1"
                  >
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>
                        {project.name} ({project.num_documents} docs)
                      </option>
                    ))}
                  </select>
                  <Button onClick={run} disabled={running || !projectId}>
                    {running ? <Loader2 className="animate-spin" /> : <Play />}
                    Run evaluation
                  </Button>
                </div>
              )}

              {status?.answer_metrics_available && (
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={withAnswerQuality}
                    onChange={(event) => setWithAnswerQuality(event.target.checked)}
                    disabled={running}
                    className="h-3.5 w-3.5 rounded border-input"
                  />
                  Also score answer quality with RAGAS — generates an answer per case, so it
                  is slower and costs model calls.
                </label>
              )}
              {status && (
                <p className="text-xs text-muted-foreground">
                  Golden set: {status.golden_set_name || "curated set"} · {status.golden_set_size}{" "}
                  cases · relevance policy: <code>{status.relevance_policy}</code>
                </p>
              )}
            </CardContent>
          </Card>

          {/* Answer-quality availability, stated plainly either way */}
          {status && !status.answer_metrics_available && (
            <Card className="border-warning/40 bg-warning/5">
              <CardContent className="flex items-start gap-3 p-4">
                <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                <div className="text-sm">
                  <p className="font-medium">Answer-quality metrics are unavailable</p>
                  <p className="mt-0.5 text-muted-foreground">
                    {status.answer_metrics_note} No placeholder score is shown for them.
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    RAGAS installed: {String(status.ragas_installed)} · live model:{" "}
                    {String(status.llm_live)}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Results */}
          {report && (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <MetricCard
                  label={`Recall@${K}`}
                  value={pct(aggregates[`recall_at_${K}`])}
                  hint="relevant passages found"
                />
                <MetricCard label="MRR" value={pct(aggregates.mrr)} hint="rank of first hit" />
                <MetricCard
                  label={`Precision@${K}`}
                  value={pct(aggregates[`precision_at_${K}`])}
                  hint={`of the ${K} returned`}
                />
                <MetricCard
                  label={`nDCG@${K}`}
                  value={pct(aggregates[`ndcg_at_${K}`])}
                  hint="ranking quality"
                />
              </div>
              {report.cases_evaluated === 0 && (
                <p className="text-sm text-muted-foreground">
                  No case in the golden set has evidence in this project&apos;s documents, so no metric
                  could be computed. That says nothing about how well retrieval works here.
                </p>
              )}

              {/* Model-judged scores are kept visually separate from the
                  computed ones above — they are a different kind of number. */}
              {report.ragas.scores && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                      Answer quality
                      <Badge variant="warning" className="text-[10px]">
                        model-judged
                      </Badge>
                      {report.ragas.judged_by && (
                        <span className="text-xs font-normal text-muted-foreground">
                          judged by {report.ragas.judged_by}
                        </span>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      {report.ragas.metrics.map((metric) => (
                        <div key={metric} className="rounded-lg border p-3 text-center">
                          <p className="text-2xl font-semibold tabular-nums">
                            {pct(report.ragas.scores?.[metric])}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {METRIC_LABELS[metric] ?? metric}
                          </p>
                        </div>
                      ))}
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">{report.ragas.note}</p>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">
                    Per-case results
                    <Badge variant="secondary" className="ml-2">
                      {report.cases_evaluated} scored
                    </Badge>
                    {report.cases_unsupported > 0 && (
                      <Badge variant="outline" className="ml-1.5">
                        {report.cases_unsupported} not in corpus
                      </Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-xs text-muted-foreground">
                    Scored against {report.corpus_chunks} indexed chunks. A case whose
                    evidence does not exist in this project is excluded from the averages
                    rather than counted as a zero the retriever never had a chance to earn.
                  </p>
                  <ul className="space-y-2">
                    {report.cases.map((result) => (
                      <CaseRow key={result.id} result={result} />
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </>
          )}

          {/* Golden set listing */}
          {golden && (
            <Card>
              <CardHeader className="pb-3">
                <button
                  type="button"
                  onClick={() => setShowCases((prev) => !prev)}
                  className="focus-ring flex w-full items-center justify-between text-left"
                  aria-expanded={showCases}
                >
                  <CardTitle className="text-base">
                    Curated golden set
                    <Badge variant="secondary" className="ml-2">{golden.size} cases</Badge>
                  </CardTitle>
                  <ChevronDown
                    className={`h-4 w-4 text-muted-foreground transition-transform ${showCases ? "rotate-180" : ""}`}
                  />
                </button>
              </CardHeader>
              {showCases && (
                <CardContent className="space-y-2">
                  {typeof golden.metadata.notes === "string" && (
                    <p className="text-xs text-muted-foreground">{golden.metadata.notes}</p>
                  )}
                  <ul className="space-y-2">
                    {golden.cases.map((testCase) => (
                      <li key={testCase.id} className="rounded-md border p-2.5 text-xs">
                        <div className="flex flex-wrap items-center gap-2">
                          <code className="text-[10px] text-muted-foreground">{testCase.id}</code>
                          <Badge variant="outline" className="text-[10px]">{testCase.difficulty}</Badge>
                          {testCase.tags.map((tag) => (
                            <Badge key={tag} variant="secondary" className="text-[10px]">{tag}</Badge>
                          ))}
                        </div>
                        <p className="mt-1 font-medium">{testCase.question}</p>
                        <p className="mt-1 text-muted-foreground">{testCase.expected_answer}</p>
                        <p className="mt-1 text-muted-foreground">
                          Relevant when a passage contains:{" "}
                          {testCase.required_entities.map((term) => (
                            <code key={term} className="mr-1 rounded bg-muted px-1 py-0.5">{term}</code>
                          ))}
                        </p>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
