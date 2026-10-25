import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  CitationChip,
  ComparisonTable,
  ExperimentList,
  GapsList,
  HypothesisList,
} from "@/components/ResearchResults";
import {
  aComparison,
  someExperiments,
  someGaps,
  someHypotheses,
} from "@/test/fixtures";

describe("CitationChip", () => {
  it("reveals the passage it points at when opened", async () => {
    const user = userEvent.setup();
    const citation = {
      chunk_id: "c1",
      document_id: "d1",
      document_name: "attention.pdf",
      page: 4,
      quote: "memory grows quadratically with sequence length",
    };

    render(<CitationChip citation={citation} />);

    // Collapsed: the source is named but the passage is not shown.
    expect(screen.getByText("attention.pdf")).toBeInTheDocument();
    expect(screen.getByText("p. 4")).toBeInTheDocument();
    expect(
      screen.queryByText(/memory grows quadratically/i),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button"));

    // Expanded: the exact supporting text is now visible.
    expect(screen.getByText(/memory grows quadratically with sequence length/i)).toBeInTheDocument();
  });

  it("says so when a claim has no supporting passage", () => {
    render(<CitationChip citation={null} />);
    expect(screen.getByText(/no supporting passage/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("ComparisonTable", () => {
  it("renders a cell per source with its citation, and reports dropped cells", () => {
    render(<ComparisonTable comparison={aComparison()} />);

    expect(screen.getByText("Focus of the work")).toBeInTheDocument();
    expect(screen.getByText(/Parallel sequence processing/i)).toBeInTheDocument();
    // The second source said nothing about this dimension.
    expect(screen.getByText(/not stated/i)).toBeInTheDocument();
    // Transparency about what was thrown away.
    expect(screen.getByText(/2 cell\(s\) were dropped/i)).toBeInTheDocument();
  });

  it("explains itself instead of rendering an empty table", () => {
    render(
      <ComparisonTable
        comparison={aComparison({
          rows: [],
          note: "A comparison needs at least two distinct documents.",
        })}
      />,
    );

    expect(screen.getByText(/needs at least two distinct documents/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("GapsList", () => {
  it("separates quoted gaps from structural graph signals", () => {
    render(<GapsList result={someGaps()} />);

    expect(screen.getByText(/Gaps stated in the sources/i)).toBeInTheDocument();
    expect(screen.getByText("Memory cost limits long sequences.")).toBeInTheDocument();
    expect(screen.getByText(/memory grows quadratically/i)).toBeInTheDocument();

    expect(screen.getByText(/Structural signals from the knowledge graph/i)).toBeInTheDocument();
    expect(screen.getByText("Curriculum Pretraining")).toBeInTheDocument();
  });

  it("shows the explanation when nothing could be evidenced", () => {
    render(
      <GapsList
        result={someGaps({
          gaps: [],
          graph_signals: [],
          note: "No gap in these passages could be tied to a quotable sentence.",
        })}
      />,
    );
    expect(screen.getByText(/could be tied to a quotable sentence/i)).toBeInTheDocument();
  });
});

describe("HypothesisList", () => {
  it("shows the gap each hypothesis descends from", () => {
    render(<HypothesisList result={someHypotheses()} />);

    expect(screen.getByText(/Sparse attention keeps accuracy/i)).toBeInTheDocument();
    expect(screen.getByText("from GAP1")).toBeInTheDocument();
    expect(screen.getByText(/Testable prediction:/i)).toBeInTheDocument();
  });

  it("falls back to its note when nothing was generated", () => {
    render(<HypothesisList result={{ hypotheses: [], note: "No evidenced gap was available." }} />);
    expect(screen.getByText(/No evidenced gap was available/i)).toBeInTheDocument();
  });
});

describe("ExperimentList", () => {
  it("renders the protocol fields that make a design runnable", () => {
    render(<ExperimentList result={someExperiments()} />);

    expect(screen.getByText(/tests HYP1/i)).toBeInTheDocument();
    expect(screen.getByText(/Perplexity/)).toBeInTheDocument();
    expect(screen.getByText(/Reproduce the baseline/)).toBeInTheDocument();
    expect(screen.getByText(/Baseline may not reproduce/)).toBeInTheDocument();
  });

  it("falls back to its note when no design survived validation", () => {
    render(
      <ExperimentList
        result={{ experiments: [], note: "No design came back with a deciding metric." }}
      />,
    );
    expect(screen.getByText(/deciding metric/i)).toBeInTheDocument();
  });
});
