import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectOverview } from "@/components/ProjectOverview";
import type { ProjectStats } from "@/lib/api";

function stats(task_counts: ProjectStats["task_counts"]): ProjectStats {
  return {
    documents: 1,
    papers: 0,
    chunks: 4,
    graph: { nodes: 0, edges: 0 },
    tasks: Object.values(task_counts).reduce((a, b) => a + b, 0),
    task_counts,
  };
}

function runningTile() {
  return screen.getByText("Tasks running").parentElement!;
}

describe("ProjectOverview", () => {
  it("counts runs waiting to start as in progress", () => {
    render(<ProjectOverview stats={stats({ queued: 2, running: 1, completed: 3, failed: 0 })} />);

    expect(runningTile()).toHaveTextContent("3");
    expect(runningTile()).toHaveTextContent("2 waiting to start");
  });

  it("shows zero only when nothing is queued or running", () => {
    render(<ProjectOverview stats={stats({ queued: 0, running: 0, completed: 3, failed: 1 })} />);

    expect(runningTile()).toHaveTextContent(/^0Tasks running$/);
  });
});
