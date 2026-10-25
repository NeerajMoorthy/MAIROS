import type { PatentAwarenessResult, PatentDetail, PatentOverlap, PatentRecord } from "@/lib/api";
import {
  PATENT_DISCLAIMER,
  PATENT_FULL_DISCLAIMER,
  PATENT_NO_OVERLAP_NOTE,
  PATENT_SCORE_LABEL,
} from "@/lib/patentCopy";

export const aPatent = (overrides: Partial<PatentRecord> = {}): PatentRecord => ({
  id: "pat-1",
  project_id: "p1",
  title: "Dense retrieval apparatus",
  number: "US1234567B2",
  url: "https://patents.google.com/patent/US1234567B2/en",
  text: "Claims\n1. A retrieval system comprising an embedding index.\n2. The system of claim 1, wherein ranking is dense.",
  source: "Google Patents",
  added_at: "2026-10-01T10:00:00Z",
  application_number: "US 16/123,456",
  family_id: "FAM-1",
  cpc_codes: ["G06F 16/3347"],
  ipc_codes: ["G06F 16/33"],
  assignee: "Example Labs",
  inventors: ["Ada Lovelace"],
  priority_date: "2019-03-01",
  filing_date: "2020-03-01",
  publication_date: "2021-09-14",
  segmented: true,
  claim_count: 2,
  warnings: [],
  disclaimer: PATENT_DISCLAIMER,
  ...overrides,
});

export const aPatentDetail = (overrides: Partial<PatentDetail> = {}): PatentDetail => ({
  disclaimer: PATENT_DISCLAIMER,
  patent: aPatent(),
  segmentation: {
    segmented: true,
    notes: [],
    claim_count: 2,
    independent_claims: [1],
    dependent_claims: [2],
    sections: [
      {
        id: "claim-1",
        kind: "claim",
        label: "Claim 1",
        text: "A retrieval system comprising an embedding index.",
        start: 7,
        end: 60,
        number: 1,
        independent: true,
        depends_on: [],
        unresolved_references: [],
      },
      {
        id: "claim-2",
        kind: "claim",
        label: "Claim 2",
        text: "The system of claim 1, wherein ranking is dense.",
        start: 61,
        end: 112,
        number: 2,
        independent: false,
        depends_on: [1],
        unresolved_references: [],
      },
    ],
  },
  ...overrides,
});

export const anOverlap = (overrides: Partial<PatentOverlap> = {}): PatentOverlap => ({
  patent_id: "pat-1",
  patent_title: "Dense retrieval apparatus",
  patent_number: "US1234567B2",
  patent_url: "https://patents.google.com/patent/US1234567B2/en",
  patent_family_id: "FAM-1",
  concept: "embedding index",
  overlap: "This wording appears both in the project's sources and in the supplied patent text.",
  matched_terms: ["embedding index"],
  citation: {
    chunk_id: "c9",
    document_id: "d1",
    document_name: "retrieval.pdf",
    page: 4,
    quote: "We build an embedding index over every passage.",
  },
  score: 0.425,
  score_label: PATENT_SCORE_LABEL,
  components: {
    term_rarity: 0.85,
    phrase_length: 0.5,
    section_weight: 1,
    corpus_chunks: 40,
    chunks_containing_term: 2,
    phrase_words: 2,
    occurrences_in_section: 1,
  },
  section: {
    id: "claim-1",
    kind: "claim",
    label: "Claim 1",
    number: 1,
    independent: true,
    depends_on: [],
    excerpt: "A retrieval system comprising an embedding index.",
  },
  also_in: [],
  ...overrides,
});

export const someFindings = (overrides: Partial<PatentAwarenessResult> = {}): PatentAwarenessResult => ({
  disclaimer: PATENT_DISCLAIMER,
  full_disclaimer: PATENT_FULL_DISCLAIMER,
  patents_checked: 1,
  concepts_checked: 12,
  corpus_chunks: 40,
  overlaps: [
    anOverlap(),
    anOverlap({
      concept: "dense",
      score: 0.17,
      components: { ...anOverlap().components!, phrase_length: 0.25, section_weight: 0.85, term_rarity: 0.8 },
      section: { ...anOverlap().section!, id: "claim-2", label: "Claim 2", number: 2, independent: false, depends_on: [1] },
    }),
  ],
  notes: [],
  score_label: PATENT_SCORE_LABEL,
  score_explanation: "similarity = term rarity × phrase length × section weight, each between 0 and 1.",
  patents: [],
  ...overrides,
});

export const noFindings = (): PatentAwarenessResult =>
  someFindings({ overlaps: [], note: PATENT_NO_OVERLAP_NOTE });
