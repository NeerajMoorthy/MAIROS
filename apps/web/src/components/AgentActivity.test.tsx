import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentActivity } from "@/components/AgentActivity";
import { api } from "@/lib/api";
import {
  aFailedTask,
  aNoveltyReport,
  aTask,
  aTaskResult,
  anEvent,
  someGaps,
} from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  vi.useRealTimers();
});

describe("AgentActivity", () => {
  it("tells the user how to start a run when there are none", async () => {
    mocked.listTasks.mockResolvedValue([]);
    render(<AgentActivity projectId="p1" />);

    expect(await screen.findByText(/No agent runs yet/i)).toBeInTheDocument();
  });

  it("shows the ordered algorithm trace for the selected run", async () => {
    mocked.listTasks.mockResolvedValue([aTask()]);
    render(<AgentActivity projectId="p1" />);

    expect(await screen.findByText(/Algorithm trace/i)).toBeInTheDocument();
    // Stages the "answer" flow really runs.
    expect(screen.getByText("Retrieval / Analysis")).toBeInTheDocument();
    expect(screen.getByText("Synthesis")).toBeInTheDocument();
    // Stages outside this flow are labelled, not left looking stuck.
    expect(screen.getAllByText(/Not in this flow/i).length).toBeGreaterThan(0);
  });

  it("renders a failed run's error rather than a blank detail pane", async () => {
    mocked.listTasks.mockResolvedValue([aFailedTask()]);
    render(<AgentActivity projectId="p1" />);

    expect(await screen.findByText(/Workflow failed/i)).toBeInTheDocument();
    expect(screen.getByText(/the vector store is unreachable/i)).toBeInTheDocument();
  });

  it("keeps a long provider error inside the pipeline detail panel", async () => {
    mocked.listTasks.mockResolvedValue([
      aTask({
        status: "failed",
        current_stage: "failed",
        result: null,
        error: "RateLimitError: a provider error with a long identifier that must wrap inside the panel",
        events: [
          {
            task_id: "t1",
            timestamp: "2026-09-01T10:10:00Z",
            agent_name: "synthesis",
            stage: "synthesizing",
            status: "failed",
            message: "RateLimitError: a provider error with a long identifier that must wrap inside the panel",
          },
        ],
      }),
    ]);
    render(<AgentActivity projectId="p1" />);

    expect((await screen.findAllByText(/long identifier/i)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/must wrap inside the panel/i).length).toBeGreaterThan(0);
  });

  it("shows grounding passages with their retrieval score", async () => {
    mocked.listTasks.mockResolvedValue([aTask()]);
    render(<AgentActivity projectId="p1" />);

    expect(await screen.findByText(/Grounding passages/i)).toBeInTheDocument();
    expect(screen.getByText(/score 0.82/)).toBeInTheDocument();
    expect(screen.getByText("p. 3")).toBeInTheDocument();
  });

  it("renders structured workflow output when a run produced it", async () => {
    mocked.listTasks.mockResolvedValue([
      aTask({ result: aTaskResult({ gaps: someGaps() }) }),
    ]);
    render(<AgentActivity projectId="p1" />);

    expect(await screen.findByText("Research gaps")).toBeInTheDocument();
    expect(screen.getByText("Memory cost limits long sequences.")).toBeInTheDocument();
  });

  it("renders a novelty result (it used to be dropped from this panel)", async () => {
    mocked.listTasks.mockResolvedValue([
      aTask({ flow: "novelty", result: aTaskResult({ novelty: aNoveltyReport() }) }),
    ]);
    render(<AgentActivity projectId="p1" />);

    expect(await screen.findByText("Coverage in this project")).toBeInTheDocument();
    expect(screen.getByText(/Scope: this project's sources only/i)).toBeInTheDocument();
  });

  it("lists the same prompt run twice as two distinguishable runs, each with its own events", async () => {
    const user = userEvent.setup();
    const first = aTask({
      id: "aaaaaa-first",
      created_at: "2026-09-01T10:00:00Z",
      events: [anEvent({ task_id: "aaaaaa-first", message: "first run event" })],
    });
    const second = aTask({
      id: "bbbbbb-second",
      created_at: "2026-09-01T10:05:00Z",
      events: [anEvent({ task_id: "bbbbbb-second", message: "second run event" })],
    });
    mocked.listTasks.mockResolvedValue([second, first]);
    render(<AgentActivity projectId="p1" />);

    const rows = await screen.findAllByRole("button", { name: /How does retrieval reduce hallucination\?/ });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("#bbbbbb");
    expect(rows[1]).toHaveTextContent("#aaaaaa");

    // The newest run is selected, and only its events show (each event
    // appears in both the stage tracker and the log — that is one run).
    expect(screen.getAllByText("second run event").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("first run event")).toHaveLength(0);

    await user.click(rows[1]);
    expect((await screen.findAllByText("first run event")).length).toBeGreaterThan(0);
    expect(screen.queryAllByText("second run event")).toHaveLength(0);
  });

  it("reports a backend hiccup instead of showing the empty state", async () => {
    mocked.listTasks.mockRejectedValue(new Error("network down"));
    render(<AgentActivity projectId="p1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not load agent runs/i);
    expect(screen.queryByText(/No agent runs yet/i)).not.toBeInTheDocument();
  });

  it("clears a selected run when switching to a project with no runs", async () => {
    mocked.listTasks.mockImplementation((projectId: string) =>
      Promise.resolve(
        projectId === "p1" ? [aTask({ id: "old-project-run", project_id: "p1" })] : [],
      ),
    );
    const { rerender } = render(<AgentActivity projectId="p1" />);

    expect(await screen.findAllByText("How does retrieval reduce hallucination?")).toHaveLength(2);
    rerender(<AgentActivity projectId="p2" />);

    expect(await screen.findByText(/No agent runs yet/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText("How does retrieval reduce hallucination?")).not.toBeInTheDocument(),
    );
  });
});
