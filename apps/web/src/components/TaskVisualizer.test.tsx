import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TaskVisualizer } from "@/components/TaskVisualizer";
import { api } from "@/lib/api";
import { aTask } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe("TaskVisualizer", () => {
  it("lights the newest run's flow on the map, with the runs and its trace under it", async () => {
    mocked.listTasks.mockResolvedValue([aTask({ id: "abcdef-1", flow: "answer" })]);
    render(<TaskVisualizer />);

    expect(await screen.findByRole("heading", { name: /Answer: \d+ agents, in order/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Answer" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Lit agents: run/)).toHaveTextContent("#abcdef");
    // The run list and the selected run's trace sit inside the map's panel.
    const panel = screen.getByRole("region", { name: "How the work is divided" });
    expect(panel).toContainElement(screen.getByRole("heading", { name: "Runs" }));
    expect(panel).toContainElement(await screen.findByRole("figure", { name: /orchestration tree/i }));
  });

  it("switches the map when another run is picked", async () => {
    const user = userEvent.setup();
    mocked.listTasks.mockResolvedValue([
      aTask({ id: "newest-run", flow: "answer", request: "What is RAG?" }),
      aTask({ id: "older-run", flow: "patent", request: "Check the patents" }),
    ]);
    render(<TaskVisualizer />);

    await screen.findByRole("heading", { name: /Answer: \d+ agents, in order/ });
    await user.click(screen.getByRole("button", { name: /Check the patents/ }));
    expect(await screen.findByRole("heading", { name: /Patent: 5 agents, in order/ })).toBeInTheDocument();
    expect(screen.getByText(/Lit agents: run/)).toHaveTextContent("Check the patents");
  });

  it("still lets the user browse any flow, dropping the run caption", async () => {
    const user = userEvent.setup();
    mocked.listTasks.mockResolvedValue([aTask({ flow: "answer" })]);
    render(<TaskVisualizer />);

    await screen.findByText(/Lit agents: run/);
    await user.click(screen.getByRole("button", { name: "Experiment" }));
    expect(screen.getByRole("button", { name: "Experiment" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText(/Lit agents: run/)).not.toBeInTheDocument();
  });
});
