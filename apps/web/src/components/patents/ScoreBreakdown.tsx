import type { ScoreComponents } from "@/lib/api";
import { PATENT_SCORE_LABEL, SCORE_COMPONENT_HELP } from "@/lib/patentCopy";

function Bar({ label, value, help }: { label: string; value: number; help: string }) {
  const percent = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="grid grid-cols-[7.5rem_1fr_2.75rem] items-center gap-2" title={help}>
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="contents">
        <span
          className="h-1.5 overflow-hidden rounded-full bg-muted print:border print:border-black"
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={1}
          aria-valuenow={value}
        >
          <span className="block h-full rounded-full bg-primary/80" style={{ width: `${percent}%` }} />
        </span>
        <span className="text-right font-mono text-[11px] tabular-nums">{value.toFixed(2)}</span>
      </dd>
    </div>
  );
}

/**
 * Why a finding scored what it did. The total is the product of the three
 * bars, so a reader can see which factor moved it — and the label says, every
 * time, that this measures shared wording and nothing else.
 */
export function ScoreBreakdown({
  score,
  components,
}: {
  score: number;
  components: ScoreComponents;
}) {
  return (
    <div className="space-y-1.5 rounded-md border bg-muted/30 p-2.5">
      <p className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
        <span className="font-medium">{PATENT_SCORE_LABEL}</span>
        <span className="font-mono tabular-nums">{score.toFixed(3)}</span>
      </p>
      <dl className="space-y-1">
        <Bar label="Term rarity" value={components.term_rarity} help={SCORE_COMPONENT_HELP.term_rarity} />
        <Bar label="Phrase length" value={components.phrase_length} help={SCORE_COMPONENT_HELP.phrase_length} />
        <Bar label="Section weight" value={components.section_weight} help={SCORE_COMPONENT_HELP.section_weight} />
      </dl>
      <p className="text-[10px] text-muted-foreground">
        = rarity × length × weight. Found in {components.chunks_containing_term} of{" "}
        {components.corpus_chunks} project passage(s); appears {components.occurrences_in_section}{" "}
        time(s) in this section (repetition is not scored).
      </p>
    </div>
  );
}

export default ScoreBreakdown;
