import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PipelineTrace } from "@/components/PipelineTrace";
import { aTask, anEvent, aTaskResult } from "@/test/fixtures";

describe("PipelineTrace", () => {
  it("renders nothing without a task", () => {
    const { container } = render(<PipelineTrace task={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("marks a stage completed only when its agent reported completion", () => {
    render(<PipelineTrace task={aTask()} />);

    expect(screen.getByText("Router")).toBeInTheDocument();
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
    expect(screen.getByText(/5 chunks retrieved/)).toBeInTheDocument();
  });

  it("labels stages outside the chosen flow instead of leaving them pending", () => {
    render(<PipelineTrace task={aTask()} />);
    // The answer flow has no indexing or knowledge-graph step.
    expect(screen.getAllByText(/Not in this flow/i).length).toBeGreaterThan(0);
  });

  it("shows a stage as pending when its agent has not run yet", () => {
    const running = aTask({
      status: "running",
      result: null,
      events: [anEvent({ agent_name: "orchestrator", status: "running" })],
    });
    render(<PipelineTrace task={running} />);

    // With no routing decision yet, later stages read as pending, not skipped.
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
  });

  it("marks the failing stage as failed", () => {
    const failed = aTask({
      status: "failed",
      result: aTaskResult(),
      events: [
        anEvent({ agent_name: "orchestrator", status: "completed" }),
        anEvent({ agent_name: "retriever", status: "failed", message: "vector store unreachable" }),
      ],
    });
    render(<PipelineTrace task={failed} />);

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/vector store unreachable/)).toBeInTheDocument();
  });

  it("renders a compact stepper without per-stage detail", () => {
    render(<PipelineTrace task={aTask()} compact />);

    expect(screen.getByText("Router")).toBeInTheDocument();
    expect(screen.queryByText(/5 chunks retrieved/)).not.toBeInTheDocument();
  });
});
