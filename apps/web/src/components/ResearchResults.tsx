"use client";

import { CitationChip } from "@/components/CitationChip";
import { PatentDisclaimer } from "@/components/patents/PatentDisclaimer";
import { PatentFindingsList } from "@/components/patents/PatentFindingsList";
import { Badge } from "@/components/ui/badge";
import { SystemNotice } from "@/components/SystemNotice";
import type {
  ComparisonResult,
  ExperimentResult,
  GapResult,
  HypothesisResult,
  NoveltyAssessment,
  NoveltyResult,
  PatentAwarenessResult,
} from "@/lib/api";

// Re-exported: callers and tests import it from here.
export { CitationChip };

/** Evidence-backed research gaps, kept visually separate from graph signals. */
export function GapsList({ result }: { result: GapResult }) {
  return (
    <div className="space-y-4">
      {result.note && (
        <p className="rounded-md border p-3 text-sm text-muted-foreground">{result.note}</p>
      )}

      {result.gaps.length > 0 && (
        <div>
          <h5 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Gaps stated in the sources
          </h5>
          <ul className="space-y-2">
            {result.gaps.map((gap) => (
              <li
                key={gap.id}
                className="rounded-md border border-l-[3px] border-l-primary/60 p-2.5 text-xs"
              >
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <code className="text-[10px] text-muted-foreground">{gap.id}</code>
                  <Badge variant="outline" className="text-[10px]">
                    {gap.kind.replace(/_/g, " ")}
                  </Badge>
                  <span className="truncate text-[10px] text-muted-foreground">
                    {gap.source_document}
                  </span>
                </div>
                <p className="font-medium">{gap.gap}</p>
                <p className="mt-1 italic text-muted-foreground">“{gap.evidence_quote}”</p>
                <div className="mt-1.5">
                  <CitationChip citation={gap.citation} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.graph_signals.length > 0 && (
        <div>
          <h5 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Structural signals from the knowledge graph
          </h5>
          <ul className="space-y-2">
            {result.graph_signals.map((signal) => (
              <li key={signal.signal} className="rounded-md border p-2.5 text-xs">
                <p className="font-medium">{signal.signal.replace(/_/g, " ")}</p>
                <p className="mt-0.5 text-muted-foreground">{signal.detail}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {signal.entities.map((entity) => (
                    <Badge key={entity} variant="secondary" className="text-[10px]">
                      {entity}
                    </Badge>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Hypotheses, each showing the gap and passage it descends from. */
export function HypothesisList({ result }: { result: HypothesisResult }) {
  if (!result.hypotheses.length) {
    return (
      <p className="rounded-md border p-3 text-sm text-muted-foreground">
        {result.note ?? "No hypothesis was generated."}
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {result.hypotheses.map((hypothesis) => (
        <li
          key={hypothesis.id}
          className="rounded-md border border-l-[3px] border-l-primary/60 p-2.5 text-xs"
        >
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <code className="text-[10px] text-muted-foreground">{hypothesis.id}</code>
            <Badge variant="outline" className="text-[10px]">
              from {hypothesis.grounded_in_gap}
            </Badge>
          </div>
          <p className="font-medium">{hypothesis.statement}</p>
          {hypothesis.rationale && (
            <p className="mt-1 text-muted-foreground">{hypothesis.rationale}</p>
          )}
          <p className="mt-1">
            <span className="font-medium">Testable prediction: </span>
            <span className="text-muted-foreground">{hypothesis.testable_prediction}</span>
          </p>
          <p className="mt-1 italic text-muted-foreground">Gap: {hypothesis.gap_text}</p>
          <div className="mt-1.5">
            <CitationChip citation={hypothesis.citation} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function DesignField({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <span className="font-medium">{label}: </span>
      <span className="text-muted-foreground">{items.join("; ")}</span>
    </div>
  );
}

/** Experiment protocols, one per hypothesis. */
export function ExperimentList({ result }: { result: ExperimentResult }) {
  if (!result.experiments.length) {
    return (
      <p className="rounded-md border p-3 text-sm text-muted-foreground">
        {result.note ?? "No experiment design was produced."}
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {result.experiments.map((design) => (
        <li key={design.id} className="space-y-1.5 rounded-md border p-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <code className="text-[10px] text-muted-foreground">{design.id}</code>
            <Badge variant="outline" className="text-[10px]">
              tests {design.hypothesis_id}
            </Badge>
          </div>
          <p className="font-medium">{design.objective}</p>
          <p className="italic text-muted-foreground">{design.hypothesis}</p>
          <DesignField label="Datasets" items={design.datasets} />
          <DesignField label="Baselines" items={design.baselines} />
          <DesignField label="Metrics" items={design.metrics} />
          <DesignField label="Controls" items={design.controls} />
          {design.procedure.length > 0 && (
            <div>
              <span className="font-medium">Procedure:</span>
              <ol className="ml-4 list-decimal space-y-0.5 text-muted-foreground">
                {design.procedure.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
            </div>
          )}
          <DesignField label="Threats to validity" items={design.threats_to_validity} />
        </li>
      ))}
    </ul>
  );
}

/** Patent overlaps — always shown under the standing legal disclaimer. */
export function PatentAwarenessView({ result }: { result: PatentAwarenessResult }) {
  return (
    <div className="space-y-3">
      <PatentDisclaimer text={result.disclaimer} />
      <PatentFindingsList result={result} />
    </div>
  );
}

/**
 * Novelty — corpus coverage, under a scope banner that is never optional.
 *
 * Every verdict is phrased against this project's sources, and the scope
 * notice renders before the list rather than after it, so the boundary is read
 * first. Nothing here can display a claim of novelty in the field: the only
 * field-level string the component renders is `field_novelty_reason`, which
 * states why that was not assessed.
 */
const ORIGIN_LABELS: Record<NoveltyAssessment["origin"], string> = {
  hypothesis: "a generated hypothesis",
  question: "your request",
  project: "your project's stated contributions",
};

export function NoveltyView({ result }: { result: NoveltyResult }) {
  const TONE: Record<NoveltyAssessment["verdict"], "success" | "warning" | "outline"> = {
    covered_in_corpus: "success",
    partially_covered: "warning",
    not_found_in_corpus: "outline",
  };

  return (
    <div className="space-y-3">
      <SystemNotice variant="novelty" />

      <p className="text-xs text-muted-foreground">
        Checked against {result.scope}.
        {result.uncited_notes_dropped
          ? ` ${result.uncited_notes_dropped} unsupported note(s) dropped.`
          : ""}
      </p>

      {result.note && (
        <p className="rounded-md border p-3 text-xs text-muted-foreground">{result.note}</p>
      )}

      <ul className="space-y-2">
        {result.assessments.map((assessment, index) => (
          <li key={`${assessment.verdict}-${index}`} className="rounded-md border p-2.5 text-xs">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <Badge variant={TONE[assessment.verdict]} className="text-[10px]">
                {assessment.verdict_label}
              </Badge>
              <span className="text-[10px] text-muted-foreground">
                wording overlap {Math.round(assessment.corpus_overlap * 100)}% · from{" "}
                {ORIGIN_LABELS[assessment.origin] ?? "your request"}
              </span>
            </div>

            <p className="font-medium text-foreground">{assessment.claim}</p>

            {assessment.nearest_prior_work.length > 0 ? (
              <div className="mt-1.5 space-y-1.5">
                {assessment.nearest_prior_work.map((prior, priorIndex) => (
                  <div key={`${prior.citation.chunk_id}-${priorIndex}`}>
                    <p className="text-muted-foreground">{prior.note}</p>
                    <CitationChip citation={prior.citation} />
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-1.5 text-muted-foreground">
                No passage in the searched sources mentions this.
              </p>
            )}

            <p className="mt-2 border-t pt-1.5 text-[10px] text-muted-foreground">
              {assessment.field_novelty_reason}
            </p>
          </li>
        ))}
      </ul>

      {result.limits && (
        <p className="rounded-md border p-3 text-[11px] text-muted-foreground">{result.limits}</p>
      )}
    </div>
  );
}

/** Tab (Workflows): the cited comparison table produced by the compare flow. */
export function ComparisonTable({ comparison }: { comparison: ComparisonResult }) {
  if (!comparison.rows.length) {
    return (
      <p className="rounded-md border p-3 text-sm text-muted-foreground">
        {comparison.note ?? "No comparable dimensions were found across these sources."}
      </p>
    );
  }

  const sources = comparison.sources;

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b bg-muted/40">
              <th className="p-2.5 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Dimension
              </th>
              {sources.map((source) => (
                <th key={source.key} className="p-2.5 text-left text-xs font-medium">
                  {source.document_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {comparison.rows.map((row) => (
              <tr key={row.dimension} className="border-b last:border-b-0 align-top">
                <td className="w-40 p-2.5 text-xs font-medium">{row.dimension}</td>
                {sources.map((source) => {
                  const cell = row.cells.find((c) => c.source_key === source.key);
                  return (
                    <td key={source.key} className="p-2.5 text-xs">
                      {cell ? (
                        <div className="space-y-1.5">
                          <p>{cell.value}</p>
                          <CitationChip citation={cell.citation} />
                        </div>
                      ) : (
                        <span className="text-muted-foreground">— not stated</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {comparison.uncited_cells_dropped ? (
        <p className="text-xs text-muted-foreground">
          {comparison.uncited_cells_dropped} cell(s) were dropped because no retrieved passage
          supported them — a cited table never shows an unsupported claim.
        </p>
      ) : null}

      {comparison.agreements.length > 0 && (
        <div>
          <h5 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Agreements
          </h5>
          <ul className="space-y-1.5">
            {comparison.agreements.map((item, index) => (
              <li key={index} className="rounded-md border p-2.5 text-xs">
                <p>{item.claim}</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {item.sources.map((name) => (
                    <Badge key={name} variant="secondary" className="text-[10px]">
                      {name}
                    </Badge>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {comparison.contradictions.length > 0 && (
        <div>
          <h5 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Contradictions
          </h5>
          <ul className="space-y-1.5">
            {comparison.contradictions.map((item, index) => (
              <li key={index} className="rounded-md border p-2.5 text-xs">
                <p className="font-medium">{item.claim}</p>
                <ul className="mt-1.5 space-y-1.5">
                  {item.positions.map((position, positionIndex) => (
                    <li key={positionIndex}>
                      <span className="font-medium">{position.document_name || "Source"}:</span>{" "}
                      {position.position}
                      <div className="mt-1">
                        <CitationChip citation={position.citation} />
                      </div>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}

      {comparison.gaps.length > 0 && (
        <div>
          <h5 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Noted gaps
          </h5>
          <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">
            {comparison.gaps.map((gap, index) => (
              <li key={index}>{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
