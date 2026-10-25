"use client";

import { useState } from "react";
import { ChevronDown, Quote } from "lucide-react";

import type { EvidenceCitation } from "@/lib/api";

/** A citation chip that expands to the exact supporting passage. */
export function CitationChip({ citation }: { citation: EvidenceCitation | null }) {
  const [open, setOpen] = useState(false);

  if (!citation) {
    return (
      <span className="text-[10px] italic text-muted-foreground">no supporting passage</span>
    );
  }

  return (
    <span className="inline-block">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="focus-ring inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-accent/50"
        title="Show the passage this came from"
        aria-expanded={open}
        aria-label={`${open ? "Hide" : "Show"} the passage from ${
          citation.document_name || "the source"
        }`}
      >
        <Quote className="h-2.5 w-2.5" />
        <span className="max-w-[10rem] truncate">{citation.document_name || "source"}</span>
        {citation.page != null && <span>p. {citation.page}</span>}
        <ChevronDown className={`h-2.5 w-2.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <span className="mt-1 block rounded-md border border-l-[3px] border-l-primary/60 bg-muted/40 p-2 text-[11px] text-muted-foreground">
          {citation.quote}
        </span>
      )}
    </span>
  );
}

export default CitationChip;
