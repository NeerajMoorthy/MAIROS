import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CoverageReport, ProjectBriefView } from "@/components/LiteratureCoverage";
import { WorkflowSections } from "@/components/TaskResultView";
import { expectNoViolations } from "@/test/a11y";
import { aCoverage, aProjectBrief, aTaskResult } from "@/test/fixtures";

/**
 * The coverage report is the stated limit of every result built on fetched
 * papers. These check that the limits reach the screen — a source that did
 * not answer, a set too small to conclude from — rather than only the counts.
 */
describe("CoverageReport", () => {
  it("states every warning the backend computed", () => {
    render(<CoverageReport coverage={aCoverage()} />);
    const warnings = screen.getByRole("list", { name: "Coverage warnings" });
    expect(within(warnings).getAllByRole("listitem")).toHaveLength(2);
    expect(within(warnings).getByText(/Semantic Scholar did not answer/)).toBeInTheDocument();
    expect(within(warnings).getByText(/too few for a gap/)).toBeInTheDocument();
  });

  it("shows each source's outcome in words, not colour alone", () => {
    render(<CoverageReport coverage={aCoverage()} />);
    expect(screen.getAllByText("searched")).toHaveLength(2);
    expect(screen.getByText("rate limited")).toBeInTheDocument();
    expect(screen.getByText(/SEMANTIC_SCHOLAR_API_KEY/)).toBeInTheDocument();
    expect(screen.getByText("4 record(s), 3 kept")).toBeInTheDocument();
  });

  it("says who wrote each query", () => {
    render(<CoverageReport coverage={aCoverage()} />);
    expect(screen.getByText("open-domain QA with a retriever")).toBeInTheDocument();
    expect(screen.getByText("· model")).toBeInTheDocument();
    expect(screen.getByText("· rules")).toBeInTheDocument();
  });

  it("always shows the scope note, even when nothing went wrong", () => {
    render(<CoverageReport coverage={aCoverage({ warnings: [] })} />);
    expect(screen.queryByRole("list", { name: "Coverage warnings" })).not.toBeInTheDocument();
    expect(screen.getByText(/not a systematic review/)).toBeInTheDocument();
    expect(screen.getByText("2017–2020")).toBeInTheDocument();
  });

  it("has no WCAG AA violations", async () => {
    const { container } = render(<CoverageReport coverage={aCoverage()} />);
    await expectNoViolations(container);
  });
});

describe("ProjectBriefView", () => {
  it("shows the project as read, and how it was read", () => {
    render(<ProjectBriefView brief={aProjectBrief()} />);
    expect(screen.getByText(/the live model, then checked against your text/)).toBeInTheDocument();
    expect(screen.getByText(/2 item\(s\) were dropped because your description does not say them/)).toBeInTheDocument();
    expect(screen.getByText("dense passage retrieval", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText(/Stated contributions \(checked under coverage\)/)).toBeInTheDocument();
  });

  it("omits empty sections instead of rendering blank headings", () => {
    render(<ProjectBriefView brief={aProjectBrief({ datasets: [], methods: [] })} />);
    expect(screen.queryByText("Datasets")).not.toBeInTheDocument();
    expect(screen.queryByText("Methods")).not.toBeInTheDocument();
  });

  it("has no WCAG AA violations", async () => {
    const { container } = render(<ProjectBriefView brief={aProjectBrief()} />);
    await expectNoViolations(container);
  });
});

describe("WorkflowSections", () => {
  it("puts the brief and the search scope ahead of the findings", () => {
    render(
      <WorkflowSections
        result={aTaskResult({ project_brief: aProjectBrief(), literature_coverage: aCoverage() })}
      />,
    );
    const headings = screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent);
    expect(headings.slice(0, 2)).toEqual(["Your project, as read", "What was searched"]);
  });
});
