import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentActivity } from "@/components/AgentActivity";
import { ChatPanel } from "@/components/ChatPanel";
import {
  ComparisonTable,
  ExperimentList,
  GapsList,
  HypothesisList,
  NoveltyView,
  PatentAwarenessView,
} from "@/components/ResearchResults";
import { SearchUpload } from "@/components/SearchUpload";
import { SystemNotice } from "@/components/SystemNotice";
import { WorkflowPanel } from "@/components/WorkflowPanel";
import { api } from "@/lib/api";
import { expectNoViolations } from "@/test/a11y";
import {
  aComparison,
  aNoveltyReport,
  aProjectDetail,
  aTask,
  anEvent,
  someExperiments,
  someGaps,
  someHypotheses,
} from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  mocked.listPatents.mockResolvedValue({ disclaimer: "Research-support only.", patents: [] });
  mocked.patentSources.mockResolvedValue({
    disclaimer: "Research-support only.",
    fetches_documents: false,
    sources: [{ domain: "patents.google.com", name: "Google Patents" }],
    notes: [],
  });
  mocked.listTasks.mockResolvedValue([aTask()]);
  mocked.getTask.mockResolvedValue(aTask());
  mocked.getProject.mockResolvedValue(aProjectDetail());
  mocked.searchPapers.mockResolvedValue({ papers: [] });
  mocked.listPapers.mockResolvedValue([]);
  mocked.health.mockResolvedValue({
    status: "ok",
    version: "0.2.0",
    llm: { provider: "offline-fallback", model: "mairos-offline", live: false },
    projects: 1,
  });
  mocked.chat.mockResolvedValue({ answer: "", citations: [] });
});

/**
 * Populated-state accessibility checks.
 *
 * The browser-level audit that accompanied this work covers the empty states of
 * each route; these cover the states that only appear once a run has produced
 * output, which is most of the surface a reviewer actually looks at. Everything
 * here is a real WCAG 2.1 AA rule from axe-core, not a stylistic preference.
 */
describe("accessibility of populated result views", () => {
  it.each([
    ["comparison table", () => <ComparisonTable comparison={aComparison()} />],
    ["gaps list", () => <GapsList result={someGaps()} />],
    ["hypothesis list", () => <HypothesisList result={someHypotheses()} />],
    ["experiment list", () => <ExperimentList result={someExperiments()} />],
    ["novelty report", () => <NoveltyView result={aNoveltyReport()} />],
    [
      "patent awareness",
      () => (
        <PatentAwarenessView
          result={{
            disclaimer: "Research-support only.",
            patents_checked: 1,
            concepts_checked: 3,
            overlaps: [],
            summary: "No overlap found.",
          }}
        />
      ),
    ],
    ["offline notice", () => <SystemNotice variant="offline" />],
    ["novelty notice", () => <SystemNotice variant="novelty" />],
    ["compact notice", () => <SystemNotice variant="offline" compact />],
  ])("%s has no WCAG AA violations", async (_name, renderNode) => {
    const { container } = render(renderNode());
    await expectNoViolations(container);
  });

  it("the workflow panel is accessible once its flows are listed", async () => {
    const { container } = render(<WorkflowPanel projectId="p1" />);
    await screen.findByText("Compare papers");
    await expectNoViolations(container);
  });

  it("the agent activity panel is accessible with a selected run", async () => {
    mocked.listTasks.mockResolvedValue([
      aTask({ events: [anEvent(), anEvent({ agent_name: "synthesis" })] }),
    ]);
    const { container } = render(<AgentActivity projectId="p1" />);
    await waitFor(() => expect(mocked.listTasks).toHaveBeenCalled());
    await expectNoViolations(container);
  });

  it("search and upload is accessible", async () => {
    const { container } = render(
      <SearchUpload
        projectId="p1"
        documents={aProjectDetail().documents}
        onTaskStarted={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    await screen.findByLabelText(/Topic to search the literature for/);
    await expectNoViolations(container);
  });

  it("the chat panel is accessible", async () => {
    const { container } = render(<ChatPanel projectId="p1" />);
    await screen.findByLabelText(/Ask a question about your documents/);
    await expectNoViolations(container);
  });
});

/**
 * Keyboard operability. Every disclosure in the app is a real <button> with
 * aria-expanded, so it is reachable by Tab and toggled by Enter or Space —
 * these assert that rather than trusting the markup to stay that way.
 */
describe("keyboard operation", () => {
  it("a citation chip opens with the keyboard and reports its state", async () => {
    const user = userEvent.setup();
    render(<NoveltyView result={aNoveltyReport()} />);

    const chip = screen.getByRole("button", { name: /Show the passage from attention\.pdf/ });
    expect(chip).toHaveAttribute("aria-expanded", "false");

    chip.focus();
    expect(chip).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(chip).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByText(/The transformer relies on self attention/),
    ).toBeInTheDocument();
  });

  it("every disclosure in a result view declares aria-expanded", () => {
    render(<ComparisonTable comparison={aComparison()} />);

    const chips = screen.getAllByRole("button", { name: /Show the passage/ });
    expect(chips.length).toBeGreaterThan(0);
    for (const chip of chips) {
      expect(chip).toHaveAttribute("aria-expanded");
    }
  });

  it("the selected run is marked with aria-current, not colour alone", async () => {
    const user = userEvent.setup();
    mocked.listTasks.mockResolvedValue([
      aTask({ id: "t1", request: "First run" }),
      aTask({ id: "t2", request: "Second run" }),
    ]);
    render(<AgentActivity projectId="p1" />);

    const second = await screen.findByText("Second run");
    await user.click(second);

    await waitFor(() =>
      expect(second.closest("button")).toHaveAttribute("aria-current", "true"),
    );
  });
});
