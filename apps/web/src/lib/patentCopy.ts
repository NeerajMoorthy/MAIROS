/**
 * The patent feature's fixed wording, mirrored from
 * `services/patents/sources.py` and `services/patents/scoring.py`.
 *
 * The API sends these with every response, and the UI prefers the server's
 * copy. They are duplicated here for the states where there is no response to
 * read — loading, an error, the backend unreachable — because the disclaimer
 * must show in those too. `tests/test_patents.py` fails if the two copies
 * drift apart.
 */

export const PATENT_DISCLAIMER =
  "Research-support only. Not legal advice or a patentability assessment.";

export const PATENT_FULL_DISCLAIMER =
  PATENT_DISCLAIMER +
  " These findings are computed overlaps in wording between this research " +
  "project's own sources and patent text that a user pasted in; MAIROS did not " +
  "retrieve the patent document. The similarity score measures shared wording " +
  "only. It is not a probability, a risk level, or an opinion on infringement, " +
  "validity, or freedom to operate, and the absence of an overlap is not a " +
  "clearance. Consult a qualified patent professional for any legal question.";

export const PATENT_NO_OVERLAP_NOTE =
  "No project concept was found in the supplied patent text. " +
  "Absence of a literal overlap is not a legal clearance.";

export const PATENT_SCORE_LABEL = "Similarity score (shared wording only)";

/** What each score component means, for tooltips and the explainer. */
export const SCORE_COMPONENT_HELP = {
  term_rarity:
    "How unusual the term is in this project's own indexed passages. A term found in few passages scores near 1; one found in every passage keeps a small floor.",
  phrase_length:
    "Longer matched phrases are stronger evidence of shared wording: one word scores 0.25, four or more words score 1.",
  section_weight:
    "Where the match sits in the patent: independent claim 1.0, dependent claim 0.85, abstract 0.6, whole unsegmented text 0.5, description 0.4.",
} as const;

/**
 * Wording the patent feature must never use: each implies a legal conclusion.
 * Mirrors `LEGAL_CONCLUSION_PATTERNS` in `services/patents/wording.py`.
 */
export const LEGAL_CONCLUSION_PATTERNS = [
  /\binfring\w*/i,
  /\bviolat\w*/i,
  /\bclear\s+to\b/i,
  /\bsafe\s+to\b/i,
  /\bpatentable\b/i,
  /\binvalid\w*/i,
  /\bfreedom[\s-]+to[\s-]+operate\b/i,
  /\b(?:legally|legal)\s+(?:clear|safe|risk)\w*/i,
  /\b(?:no|low|high|moderate)\s+(?:legal\s+)?risk\b/i,
];

/** Legal-conclusion phrases in `text`, ignoring the reviewed disclaimers. */
export function legalConclusionTerms(text: string): string[] {
  let remaining = text;
  for (const allowed of [PATENT_FULL_DISCLAIMER, PATENT_NO_OVERLAP_NOTE, PATENT_DISCLAIMER]) {
    remaining = remaining.split(allowed).join(" ");
  }
  return LEGAL_CONCLUSION_PATTERNS.flatMap((pattern) => {
    const match = remaining.match(pattern);
    return match ? [match[0]] : [];
  });
}
