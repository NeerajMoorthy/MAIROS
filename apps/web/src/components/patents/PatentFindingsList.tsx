import { ExternalLink } from "lucide-react";

import { CitationChip } from "@/components/CitationChip";
import { ScoreBreakdown } from "@/components/patents/ScoreBreakdown";
import { Badge } from "@/components/ui/badge";
import type { PatentAwarenessResult, PatentOverlap } from "@/lib/api";
import { PATENT_NO_OVERLAP_NOTE } from "@/lib/patentCopy";

function locationLabel(overlap: PatentOverlap): string {
  const section = overlap.section;
  if (!section) return "Whole supplied text";
  if (section.kind !== "claim" || section.number == null) return section.label;
  if (section.depends_on.length) {
    return `${section.label} · dependent on claim ${section.depends_on.join(", ")}`;
  }
  return `${section.label} · independent`;
}

function Finding({ overlap, printable }: { overlap: PatentOverlap; printable: boolean }) {
  return (
    <li className="space-y-2 rounded-md border p-3 text-xs break-inside-avoid print:border-black">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="text-[10px] print:border print:border-black print:bg-transparent">
          wording overlap
        </Badge>
        <span className="font-medium">{overlap.concept}</span>
        <span className="text-muted-foreground">
          ↔ {overlap.patent_title}
          {overlap.patent_number ? ` (${overlap.patent_number})` : ""}
        </span>
      </div>

      <p>
        <span className="font-medium">Matched in: </span>
        {locationLabel(overlap)}
        {overlap.also_in && overlap.also_in.length > 0 && (
          <span className="text-muted-foreground"> — also in {overlap.also_in.join(", ")}</span>
        )}
      </p>

      {overlap.section?.excerpt && (
        <blockquote className="border-l-2 border-primary/50 pl-2 italic text-muted-foreground">
          {overlap.section.excerpt}
        </blockquote>
      )}

      {overlap.matched_terms.length > 0 && (
        <p className="text-muted-foreground">Matched terms: {overlap.matched_terms.join(", ")}</p>
      )}

      {overlap.components && overlap.score != null && (
        <ScoreBreakdown score={overlap.score} components={overlap.components} />
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium">Project passage:</span>
        {printable ? (
          <span className="text-[11px] text-muted-foreground">
            {overlap.citation
              ? `${overlap.citation.document_name}${
                  overlap.citation.page != null ? `, p. ${overlap.citation.page}` : ""
                } — “${overlap.citation.quote}”`
              : "no project passage contains this wording verbatim"}
          </span>
        ) : (
          <CitationChip citation={overlap.citation} />
        )}
        {!printable && overlap.patent_url && (
          <a
            href={overlap.patent_url}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-ring inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
          >
            open public record <ExternalLink className="h-3 w-3" aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        )}
      </div>
    </li>
  );
}

/**
 * Computed findings, ranked by similarity score. Shared by the Patents page,
 * its printable view, and the patent workflow's result in Workflows/Tasks, so
 * every surface shows the same thing the same way.
 */
export function PatentFindingsList({
  result,
  printable = false,
}: {
  result: PatentAwarenessResult;
  printable?: boolean;
}) {
  const notes = [...(result.notes ?? [])];
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        {result.summary ? `${result.summary} ` : ""}
        Checked {result.concepts_checked} project concept(s) against {result.patents_checked} supplied
        patent text(s)
        {result.corpus_chunks != null ? ` and ${result.corpus_chunks} indexed project passage(s)` : ""}.
      </p>

      {notes.length > 0 && (
        <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      {result.overlaps.length === 0 ? (
        <p className="rounded-md border p-3 text-xs text-muted-foreground print:border-black">
          {result.patents_checked === 0 ? result.note : result.note ?? PATENT_NO_OVERLAP_NOTE}
        </p>
      ) : (
        <ol className="space-y-2" aria-label="Patent wording overlaps, highest score first">
          {result.overlaps.map((overlap, index) => (
            <Finding
              key={`${overlap.patent_id}-${overlap.concept}-${index}`}
              overlap={overlap}
              printable={printable}
            />
          ))}
        </ol>
      )}

      {result.score_explanation && (
        <p className="text-[11px] text-muted-foreground">{result.score_explanation}</p>
      )}
    </div>
  );
}

export default PatentFindingsList;
