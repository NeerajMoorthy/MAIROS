"use client";

import { useState } from "react";
import { ChevronDown, Quote } from "lucide-react";

import {
  ComparisonTable,
  ExperimentList,
  GapsList,
  HypothesisList,
  NoveltyView,
  PatentAwarenessView,
} from "@/components/ResearchResults";
import { CoverageReport, ProjectBriefView } from "@/components/LiteratureCoverage";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { Citation, TaskResult } from "@/lib/api";

/**
 * The research-workflow sections of a task result, in pipeline order.
 *
 * One list, used by both the Workflows tab and Agent Activity. They used to
 * keep separate copies, which had drifted: Agent Activity never rendered the
 * novelty result, so a novelty run looked empty there.
 */
const SECTIONS: {
  key: keyof Pick<
    TaskResult,
    | "project_brief"
    | "literature_coverage"
    | "comparison"
    | "gaps"
    | "hypotheses"
    | "experiments"
    | "novelty"
    | "patent_awareness"
  >;
  title: string;
  render: (result: TaskResult) => React.ReactNode;
}[] = [
  { key: "project_brief", title: "Your project, as read", render: (r) => <ProjectBriefView brief={r.project_brief!} /> },
  {
    key: "literature_coverage",
    title: "What was searched",
    render: (r) => <CoverageReport coverage={r.literature_coverage!} />,
  },
  { key: "comparison", title: "Comparison table", render: (r) => <ComparisonTable comparison={r.comparison!} /> },
  { key: "gaps", title: "Research gaps", render: (r) => <GapsList result={r.gaps!} /> },
  { key: "hypotheses", title: "Hypotheses", render: (r) => <HypothesisList result={r.hypotheses!} /> },
  { key: "experiments", title: "Experiment designs", render: (r) => <ExperimentList result={r.experiments!} /> },
  { key: "novelty", title: "Coverage in this project", render: (r) => <NoveltyView result={r.novelty!} /> },
  {
    key: "patent_awareness",
    title: "Patent awareness",
    render: (r) => <PatentAwarenessView result={r.patent_awareness!} />,
  },
];

/** Every research-workflow section the result carries, each under a heading. */
export function WorkflowSections({ result }: { result: TaskResult }) {
  const present = SECTIONS.filter((section) => result[section.key]);
  if (!present.length) return null;
  return (
    <>
      {present.map((section) => (
        <section key={section.key} aria-label={section.title} className="space-y-2">
          <Separator />
          <h4 className="pt-2 text-sm font-medium">{section.title}</h4>
          {section.render(result)}
        </section>
      ))}
    </>
  );
}

function GroundingPassage({ citation, index }: { citation: Citation; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="flex gap-2.5 rounded-md border border-l-[3px] border-l-primary/60 p-2.5 text-xs">
      <span className="mt-0.5 shrink-0 font-mono text-[10px] font-semibold text-primary">
        [{index + 1}]
      </span>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="truncate font-medium">{citation.document_name || "Source"}</span>
          {citation.page != null && (
            <Badge variant="outline" className="text-[10px]">
              p. {citation.page}
            </Badge>
          )}
          {citation.score != null && (
            <Badge variant="secondary" className="text-[10px]">
              score {citation.score.toFixed(2)}
            </Badge>
          )}
        </div>
        <p className={open ? "text-muted-foreground" : "line-clamp-3 text-muted-foreground"}>
          {citation.text}
        </p>
        {citation.text.length > 160 && (
          <button
            type="button"
            onClick={() => setOpen((prev) => !prev)}
            aria-expanded={open}
            className="focus-ring mt-1 inline-flex items-center gap-0.5 text-[10px] font-medium text-primary hover:underline"
          >
            <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
            {open ? "Show less" : "Show full passage"}
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * The final answer, its APA references and the passages that grounded it.
 *
 * Each passage owns its expanded state. The previous version kept one set of
 * expanded indexes for the whole panel, so opening passage 2 of one run left
 * passage 2 of the next selected run open as well.
 */
export function TaskAnswer({ result }: { result: TaskResult }) {
  return (
    <div className="space-y-4">
      <section aria-label="Final answer" className="space-y-1.5">
        <h4 className="text-sm font-medium">Final answer</h4>
        <div className="whitespace-pre-wrap rounded-lg border bg-muted/40 p-4 text-sm">
          {result.answer || "The run finished without an answer."}
        </div>
      </section>

      {result.references.length > 0 && (
        <section aria-label="References" className="space-y-2">
          <h4 className="flex items-center gap-1.5 text-sm font-medium">
            <Quote className="h-3.5 w-3.5" aria-hidden="true" /> References (APA)
          </h4>
          <ul className="space-y-2">
            {result.references.map((reference, index) => (
              <li key={index} className="rounded-md border p-2.5 text-xs leading-relaxed">
                {reference}
              </li>
            ))}
          </ul>
        </section>
      )}

      {result.citations.length > 0 && (
        <section aria-label="Grounding passages" className="space-y-2">
          <h4 className="text-sm font-medium">Grounding passages ({result.citations.length})</h4>
          <ul className="space-y-2">
            {result.citations.map((citation, index) => (
              <GroundingPassage key={`${citation.chunk_id}-${index}`} citation={citation} index={index} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
