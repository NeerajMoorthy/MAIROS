import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GraphViewer } from "@/components/GraphViewer";
import { api } from "@/lib/api";

// The force-graph canvas needs a real browser; the legend, empty state and
// node details are what this panel actually has to get right.
vi.mock("next/dynamic", () => ({
  default: () => function ForceGraphStub() {
    return <div data-testid="force-graph" />;
  },
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const graph = {
  nodes: [
    { id: "Self Attention", name: "Self Attention", group: "Method", description: "", mentions: 3, val: 4 },
    { id: "Ashish Vaswani", name: "Ashish Vaswani", group: "Person", description: "", mentions: 1, val: 2 },
  ],
  links: [{ source: "Self Attention", target: "Ashish Vaswani", label: "RELATED_TO", confidence: 1 }],
  stats: { nodes: 2, edges: 1 },
};

describe("GraphViewer", () => {
  it("explains how to populate an empty graph", async () => {
    mocked.getGraph.mockResolvedValue({ nodes: [], links: [], stats: { nodes: 0, edges: 0 } });
    render(<GraphViewer projectId="p1" />);

    expect(await screen.findByText(/The knowledge graph is empty/i)).toBeInTheDocument();
    expect(screen.getByText(/Upload a PDF or run a topic search/i)).toBeInTheDocument();
  });

  it("shows the node and edge counts once loaded", async () => {
    mocked.getGraph.mockResolvedValue(graph);
    render(<GraphViewer projectId="p1" />);

    expect(await screen.findByText(/2 nodes · 1 edges/)).toBeInTheDocument();
    expect(screen.getByTestId("force-graph")).toBeInTheDocument();
  });

  it("always shows the full legend, including types with no nodes yet", async () => {
    mocked.getGraph.mockResolvedValue(graph);
    render(<GraphViewer projectId="p1" />);

    // Present types carry their count…
    expect(await screen.findByText("Method (1)")).toBeInTheDocument();
    // …the backend's "Person" reads as "Author" in the UI…
    expect(screen.getByText("Author (1)")).toBeInTheDocument();
    // …and reserved types are listed at zero rather than hidden.
    expect(screen.getByText("Patent (0)")).toBeInTheDocument();
    expect(screen.getByText("Dataset (0)")).toBeInTheDocument();
  });

  it("shows a retryable error instead of claiming a failed request is empty", async () => {
    mocked.getGraph.mockRejectedValue(new Error("boom"));
    render(<GraphViewer projectId="p1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the knowledge graph");
    expect(screen.queryByText(/The knowledge graph is empty/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
  });
});
