import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AGENTS, FLOWS } from "@/lib/agents";

import { AgentNetwork3D } from "./AgentNetwork3D";

describe("AgentNetwork3D", () => {
  it("starts on the search flow and lists its agents in order, Router first", () => {
    render(<AgentNetwork3D />);
    expect(screen.getByRole("button", { name: "Search" })).toHaveAttribute("aria-pressed", "true");
    const list = screen.getByRole("heading", { name: /Search: 6 agents, in order/ }).nextElementSibling as HTMLElement;
    const names = within(list)
      .getAllByRole("listitem")
      .map((item) => item.querySelector("span.font-medium")?.textContent);
    expect(names).toEqual(["Router", "Literature", "Indexer", "Knowledge Graph", "Citation", "Synthesis"]);
  });

  it("switches the team when another flow is picked", async () => {
    render(<AgentNetwork3D />);
    await userEvent.click(screen.getByRole("button", { name: "Patent" }));
    expect(screen.getByRole("button", { name: "Patent" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: /Patent: 5 agents, in order/ })).toBeInTheDocument();
    expect(screen.getAllByText("Patent Awareness").length).toBeGreaterThan(0);
  });

  it("shows every agent under 'All agents'", async () => {
    render(<AgentNetwork3D />);
    await userEvent.click(screen.getByRole("button", { name: "All agents" }));
    expect(screen.getByRole("heading", { name: `All ${AGENTS.length} agents` })).toBeInTheDocument();
  });

  it("offers every flow and hides the decorative scene from screen readers", () => {
    render(<AgentNetwork3D />);
    for (const flow of FLOWS) {
      expect(screen.getByRole("button", { name: flow.label })).toBeInTheDocument();
    }
    expect(screen.getByTestId("agent-map-stage")).toHaveAttribute("aria-hidden", "true");
  });
});
