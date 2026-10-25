"use client";

import { AlertTriangle, CheckCircle2, CircleSlash, Clock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { CoverageSource, LiteratureCoverage, ProjectBrief } from "@/lib/api";

const STATUS: Record<
  CoverageSource["status"],
  { label: string; variant: "success" | "warning" | "destructive"; icon: typeof CheckCircle2 }
> = {
  ok: { label: "searched", variant: "success", icon: CheckCircle2 },
  rate_limited: { label: "rate limited", variant: "warning", icon: Clock },
  failed: { label: "not reached", variant: "destructive", icon: CircleSlash },
};

/**
 * What a literature search looked at, shown beside what it found.
 *
 * Every gap, comparison and coverage verdict built on fetched papers is only
 * as strong as this search, so its limits are stated in the result rather
 * than left for the reader to guess: which sources answered, what was
 * queried, how many papers were kept, and the warnings the backend computed.
 */
export function CoverageReport({ coverage }: { coverage: LiteratureCoverage }) {
  const years = coverage.year_range;
  return (
    <div className="space-y-3 text-xs">
      {coverage.warnings.length > 0 && (
        <ul aria-label="Coverage warnings" className="space-y-1.5">
          {coverage.warnings.map((warning) => (
            <li
              key={warning}
              className="flex gap-2 rounded-md border border-warning/40 bg-warning/10 p-2.5 text-foreground"
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden="true" />
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      )}

      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ["Papers kept", `${coverage.papers_kept} of ${coverage.papers_found}`],
          ["Duplicates merged", String(coverage.duplicates_merged)],
          ["Years", years ? (years[0] === years[1] ? String(years[0]) : `${years[0]}–${years[1]}`) : "—"],
          ["Searched on", coverage.searched_on],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md border p-2">
            <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      <div>
        <h5 className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Sources
        </h5>
        <ul className="space-y-1.5">
          {coverage.sources.map((source) => {
            const status = STATUS[source.status];
            const Icon = status.icon;
            return (
              <li key={source.source} className="flex flex-wrap items-center gap-2">
                <span className="min-w-28 font-medium">{source.name}</span>
                <Badge variant={status.variant} className="text-[10px]">
                  <Icon className="h-3 w-3" aria-hidden="true" /> {status.label}
                </Badge>
                <span className="text-muted-foreground">
                  {source.status === "ok"
                    ? `${source.returned} record(s), ${coverage.papers_by_source[source.name] ?? 0} kept`
                    : source.detail}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <div>
        <h5 className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Queries
        </h5>
        <ul className="flex flex-wrap gap-1.5">
          {coverage.queries.map((query) => (
            <li key={query.text}>
              <Badge variant="outline" className="max-w-full break-words text-[10px] font-normal">
                {query.text}
                <span className="text-muted-foreground">· {query.written_by === "model" ? "model" : "rules"}</span>
              </Badge>
            </li>
          ))}
        </ul>
        {coverage.query_note && <p className="mt-1.5 text-muted-foreground">{coverage.query_note}</p>}
      </div>

      <p className="rounded-md border p-2.5 text-[11px] text-muted-foreground">{coverage.scope_note}</p>
    </div>
  );
}

function BriefList({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd>
        <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </dd>
    </div>
  );
}

/**
 * The project as MAIROS read it, so the user can check the framing before
 * reading anything built on it. Every item is the user's own wording or was
 * checked against it; search keywords are the one exception and are labelled.
 */
export function ProjectBriefView({ brief }: { brief: ProjectBrief }) {
  return (
    <div className="space-y-3 text-xs">
      <p className="text-muted-foreground">
        Read from your description by{" "}
        {brief.extracted_by === "model" ? "the live model, then checked against your text" : "rules over your own sentences"}
        .
        {brief.dropped_ungrounded > 0 &&
          ` ${brief.dropped_ungrounded} item(s) were dropped because your description does not say them.`}
      </p>
      {brief.note && <p className="rounded-md border p-2.5 text-muted-foreground">{brief.note}</p>}

      <dl className="space-y-2.5">
        {brief.title && (
          <div>
            <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Title</dt>
            <dd className="font-medium">{brief.title}</dd>
          </div>
        )}
        {brief.problem && (
          <div>
            <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Problem</dt>
            <dd>{brief.problem}</dd>
          </div>
        )}
        <BriefList label="Methods" items={brief.methods} />
        <BriefList label="Datasets" items={brief.datasets} />
        <BriefList label="Goals" items={brief.goals} />
        <BriefList label="Stated contributions (checked under coverage)" items={brief.contributions} />
        {brief.keywords.length > 0 && (
          <div>
            <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Search keywords
            </dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {brief.keywords.map((keyword) => (
                <Badge key={keyword} variant="secondary" className="text-[10px] font-normal">
                  {keyword}
                </Badge>
              ))}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}
