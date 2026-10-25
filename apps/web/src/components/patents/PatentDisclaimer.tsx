import { ScrollText } from "lucide-react";

import { PATENT_DISCLAIMER, PATENT_FULL_DISCLAIMER } from "@/lib/patentCopy";
import { cn } from "@/lib/utils";

/**
 * The standing patent disclaimer. Rendered in every patent state — empty,
 * loading, error, results, print — so it is never conditional on a response
 * having arrived. `full` shows the complete wording that exports carry.
 */
export function PatentDisclaimer({
  full = false,
  text,
  className,
}: {
  full?: boolean;
  /** The server's wording, when a response provided it. */
  text?: string;
  className?: string;
}) {
  const body = text || (full ? PATENT_FULL_DISCLAIMER : PATENT_DISCLAIMER);
  return (
    <aside
      aria-label="Patent disclaimer"
      data-testid="patent-disclaimer"
      className={cn(
        "flex items-start gap-3 rounded-lg border border-warning/50 bg-warning/10 p-3 text-sm text-foreground",
        "print:border-black print:bg-transparent print:text-black",
        className,
      )}
    >
      <ScrollText className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div>
        {/* The full wording begins with the short one, so it gets its own heading. */}
        <p className="font-medium">{full ? "What these findings are — and are not" : "Research-support only"}</p>
        <p className="mt-0.5 text-xs leading-relaxed opacity-90 print:opacity-100">{body}</p>
      </div>
    </aside>
  );
}

export default PatentDisclaimer;
