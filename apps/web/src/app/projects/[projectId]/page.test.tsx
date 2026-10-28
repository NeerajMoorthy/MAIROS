import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ProjectWorkspace from "@/app/projects/[projectId]/page";
import { ApiError, api } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "missing-project" }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

vi.mock("@/components/AgentActivity", () => ({ AgentActivity: () => null }));
vi.mock("@/components/ChatPanel", () => ({ ChatPanel: () => null }));
vi.mock("@/components/GraphViewer", () => ({ GraphViewer: () => null }));
vi.mock("@/components/ProjectOverview", () => ({ ProjectOverview: () => null }));
vi.mock("@/components/SearchUpload", () => ({ SearchUpload: () => null }));
vi.mock("@/components/WorkflowPanel", () => ({ WorkflowPanel: () => null }));

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe("Project workspace route", () => {
  it("shows a project loading failure and lets the user retry", async () => {
    const user = userEvent.setup();
    mocked.getProject
      .mockRejectedValueOnce(new ApiError("Project not found", 404))
      .mockResolvedValueOnce({
        id: "missing-project",
        name: "Recovered project",
        description: "",
        created_at: "2026-10-12T00:00:00Z",
        document_ids: [],
        paper_ids: [],
        num_documents: 0,
        num_papers: 0,
        documents: [],
      });
    mocked.projectStats.mockResolvedValue({
      documents: 0,
      papers: 0,
      chunks: 0,
      graph: { nodes: 0, edges: 0 },
      tasks: 0,
      task_counts: { queued: 0, running: 0, completed: 0, failed: 0 },
    });

    render(<ProjectWorkspace />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Project not found");

    await user.click(screen.getByRole("button", { name: /Retry/i }));
    await waitFor(() => expect(mocked.getProject).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Recovered project" })).toBeInTheDocument();
  });
});

describe("Workspace header counts", () => {
  it("re-reads the task counts while the page is open", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mocked.getProject.mockReset().mockResolvedValue({
        id: "missing-project",
        name: "Busy project",
        description: "",
        created_at: "2026-10-12T00:00:00Z",
        document_ids: [],
        paper_ids: [],
        num_documents: 0,
        num_papers: 0,
        documents: [],
      });
      mocked.projectStats.mockReset().mockResolvedValue({
        documents: 0,
        papers: 0,
        chunks: 0,
        graph: { nodes: 0, edges: 0 },
        tasks: 0,
        task_counts: { queued: 0, running: 0, completed: 0, failed: 0 },
      });

      render(<ProjectWorkspace />);
      expect(await screen.findByRole("heading", { name: "Busy project" })).toBeInTheDocument();
      const loads = mocked.projectStats.mock.calls.length;

      // Runs started elsewhere after the page opened must reach the header.
      await vi.advanceTimersByTimeAsync(4000);
      expect(mocked.projectStats.mock.calls.length).toBeGreaterThan(loads);
    } finally {
      vi.useRealTimers();
    }
  });
});
