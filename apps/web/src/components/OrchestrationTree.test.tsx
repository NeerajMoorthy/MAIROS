import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OrchestrationTree, flowAgents } from "@/components/OrchestrationTree";
import { aTask, anEvent } from "@/test/fixtures";

const running = () =>
  aTask({
    status: "running",
    current_stage: "retrieving",
    result: null,
    events: [
      anEvent({ message: "Task accepted" }),
      anEvent({ message: "Pipeline: retriever → gaps → hypothesis → synthesis" }),
      anEvent({ agent_name: "retriever", stage: "retrieving", message: "5 chunks retrieved" }),
      anEvent({ agent_name: "gaps", stage: "analyzing", message: "Scanning 5 passages" }),
    ],
  });

describe("OrchestrationTree", () => {
  it("takes the agents from the orchestrator's pipeline announcement while a run is live", () => {
    expect(flowAgents(running())).toEqual(["retriever", "gaps", "hypothesis", "synthesis"]);
  });

  it("puts every agent's own work under its heading, with its status", () => {
    render(<OrchestrationTree task={running()} />);

    const tables = screen.getAllByRole("table");
    expect(tables).toHaveLength(4);
    const [retriever, gaps, hypothesis] = tables;
    expect(retriever).toHaveTextContent("Done");
    expect(within(retriever).getByText("5 chunks retrieved")).toBeInTheDocument();
    expect(gaps).toHaveTextContent("Running");
    expect(within(gaps).queryByText("5 chunks retrieved")).toBeNull();
    expect(hypothesis).toHaveTextContent("Not started yet");
  });

  it("keeps the orchestrator's own steps at the root, not in a branch", () => {
    render(<OrchestrationTree task={running()} />);

    const tree = screen.getByRole("figure", { name: /orchestration tree/i });
    expect(tree).toHaveTextContent("Task accepted");
    for (const table of screen.getAllByRole("table")) {
      expect(table).not.toHaveTextContent("Task accepted");
    }
    expect(tree).toHaveTextContent("assigns 4 agents");
  });

  it("marks agents a finished or failed run never reached", () => {
    const failed = { ...running(), status: "failed" as const, current_stage: "failed" as const };
    render(<OrchestrationTree task={failed} />);

    const [, , hypothesis] = screen.getAllByRole("table");
    expect(hypothesis).toHaveTextContent("Not reached");
  });
});
