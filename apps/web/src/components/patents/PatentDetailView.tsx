"use client";

import { useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { PatentDetail, PatentSection } from "@/lib/api";

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === "" || (Array.isArray(value) && value.length === 0)) return null;
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2 py-1 text-xs">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{value}</dd>
    </div>
  );
}

function SectionItem({ section }: { section: PatentSection }) {
  const [open, setOpen] = useState(false);
  const long = section.text.length > 280;
  const isClaim = section.kind === "claim" && section.number != null;

  return (
    <li className="rounded-md border p-2.5 text-xs">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="font-medium">{section.label}</span>
        {isClaim && (
          <Badge variant={section.independent ? "default" : "secondary"} className="text-[10px]">
            {section.independent ? "independent" : "dependent"}
          </Badge>
        )}
        {section.depends_on.length > 0 && (
          <span className="text-[11px] text-muted-foreground">
            depends on claim {section.depends_on.join(", ")}
          </span>
        )}
        {section.unresolved_references.length > 0 && (
          <span className="text-[11px] text-muted-foreground">
            refers to claim {section.unresolved_references.join(", ")}, which could not be resolved
          </span>
        )}
      </div>
      <p className={open || !long ? "whitespace-pre-wrap" : "line-clamp-3"}>{section.text}</p>
      {long && (
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          aria-expanded={open}
          className="focus-ring mt-1 inline-flex items-center gap-0.5 text-[11px] font-medium text-primary hover:underline"
        >
          <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
          {open ? "Show less" : `Show all of ${section.label.toLowerCase()}`}
        </button>
      )}
    </li>
  );
}

/** One patent: its hand-entered metadata and what segmentation found. */
export function PatentDetailView({ detail }: { detail: PatentDetail }) {
  const { patent, segmentation } = detail;
  const claims = segmentation.sections.filter((s) => s.kind === "claim");
  const others = segmentation.sections.filter((s) => s.kind !== "claim");

  return (
    <div className="space-y-5">
      <section aria-label="Patent metadata">
        <h3 className="mb-1 text-sm font-medium">Metadata</h3>
        <dl className="divide-y divide-border/60">
          <MetaRow label="Publication no." value={patent.number} />
          <MetaRow label="Application no." value={patent.application_number} />
          <MetaRow label="Family" value={patent.family_id} />
          <MetaRow label="Assignee" value={patent.assignee} />
          <MetaRow label="Inventors" value={patent.inventors.join(", ")} />
          <MetaRow label="CPC" value={patent.cpc_codes.join(", ")} />
          <MetaRow label="IPC" value={patent.ipc_codes.join(", ")} />
          <MetaRow label="Priority date" value={patent.priority_date} />
          <MetaRow label="Filing date" value={patent.filing_date} />
          <MetaRow label="Publication date" value={patent.publication_date} />
          <MetaRow label="Source" value={patent.source} />
          <MetaRow
            label="Public record"
            value={
              patent.url ? (
                // Plain inline, not inline-flex: a registry URL has no spaces,
                // and an inline-flex box cannot wrap it — at 375px it pushed
                // the whole page 112px wider than the screen.
                <a
                  href={patent.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="focus-ring break-all text-primary hover:underline"
                >
                  {patent.url}{" "}
                  <ExternalLink className="inline h-3 w-3 align-[-2px]" aria-hidden="true" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              ) : null
            }
          />
        </dl>
      </section>

      <section aria-label="Segmented text" className="space-y-2">
        <h3 className="text-sm font-medium">
          Segmented text
          {segmentation.claim_count > 0 && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {segmentation.claim_count} claim(s) · independent {segmentation.independent_claims.join(", ") || "none"}
            </span>
          )}
        </h3>
        {segmentation.notes.map((note) => (
          <p key={note} className="rounded-md border border-warning/40 bg-warning/5 p-2 text-xs">
            {note}
          </p>
        ))}
        {segmentation.sections.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No text was pasted for this patent, so there is nothing to compare yet.
          </p>
        ) : (
          <>
            {others.length > 0 && (
              <ul className="space-y-2">
                {others.map((section) => (
                  <SectionItem key={section.id} section={section} />
                ))}
              </ul>
            )}
            {claims.length > 0 && (
              <>
                <h4 className="pt-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Claims</h4>
                <ul className="space-y-2">
                  {claims.map((section) => (
                    <SectionItem key={section.id} section={section} />
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}

export default PatentDetailView;
