import { AlertTriangle, Compass, Network, ScrollText } from "lucide-react";

import { cn } from "@/lib/utils";

type Variant = "offline" | "patent" | "novelty";

const CONFIG: Record<Variant, { icon: typeof Network; title: string; body: string; tone: string }> = {
  offline: {
    icon: Network,
    title: "Running in offline LLM mode",
    body:
      "No live model is configured, so answers are produced by a deterministic offline " +
      "fallback — extractive rather than generated. Retrieval, orchestration, and the " +
      "knowledge graph are unaffected.",
    tone: "border-warning/50 bg-warning/10 text-foreground",
  },
  patent: {
    icon: ScrollText,
    title: "Research-support only",
    body: "Not legal advice or a patentability assessment.",
    tone: "border-warning/50 bg-warning/10 text-foreground",
  },
  novelty: {
    icon: Compass,
    title: "Scope: this project's sources only",
    body:
      "MAIROS can say whether a claim is already covered by the documents in this " +
      "project. It cannot say whether a claim is novel in the field — that would " +
      "require a systematic search of the published literature, which it has not done.",
    // Informational rather than a warning: a tinted border and background,
    // no new colour token.
    tone: "border-primary/50 bg-primary/5 text-foreground",
  },
};

/*
 * Contrast note: the body text is `text-foreground`, not the tone's own
 * foreground token. `text-warning-foreground` is a DARK colour (it is designed
 * to sit on a solid warning badge), so on a 10%-tinted panel it rendered at
 * 16:1 in light mode but 1.12:1 in dark mode — the offline and patent notices
 * were effectively invisible against a dark background. The warning colour now
 * carries the border and the tint only, and every variant's text sits at full
 * contrast in both themes.
 */

interface Props {
  variant: Variant;
  compact?: boolean;
  className?: string;
}

/**
 * Reusable system-state banner:
 *  - "offline": shown wherever a panel's output quality depends on whether
 *    the LLM is live (Chat, workspace header).
 *  - "patent": the compact disclaimer for places that show patent-derived
 *    content outside the patent views — a selected `Patent` node in the
 *    knowledge graph. The patent views themselves use `PatentDisclaimer`,
 *    which can carry the full wording.
 *  - "novelty": the scope limit on the novelty flow. Rendered above every
 *    novelty result so the boundary is stated before any verdict is read,
 *    not buried underneath one.
 */
export function SystemNotice({ variant, compact = false, className }: Props) {
  const { icon: Icon, title, body, tone } = CONFIG[variant];

  if (compact) {
    return (
      <div
        className={cn(
          // `min-w-0` on both the pill and its label is what makes `truncate`
          // actually truncate: a flex item defaults to min-width:auto and will
          // otherwise refuse to shrink below its text, pushing the header wide.
          "flex min-w-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
          tone,
          className,
        )}
      >
        <Icon className="h-3 w-3 shrink-0" />
        <span className="min-w-0 truncate">{title}</span>
      </div>
    );
  }

  return (
    <div className={cn("flex items-start gap-3 rounded-lg border p-3 text-sm", tone, className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 text-xs opacity-90">{body}</p>
      </div>
    </div>
  );
}

export default SystemNotice;
