import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowPanel } from "@/components/WorkflowPanel";
import { ApiError, api } from "@/lib/api";
import { aFailedTask, aTask, aTaskResult, aComparison } from "@/test/fixtures";

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
});

describe("WorkflowPanel", () => {
  it("offers no example inputs outside the example project", async () => {
    render(<WorkflowPanel projectId="p1" />);

    await screen.findByText("Compare papers");
    expect(screen.queryByRole("button", { name: /use the example input/i })).not.toBeInTheDocument();
  });

  it("fills a card with its example input in the example project", async () => {
    mocked.createTask.mockResolvedValue(aTask({ id: "t-ex", status: "queued" }));
    mocked.getTask.mockResolvedValue(aTask({ id: "t-ex", status: "queued" }));
    render(
      <WorkflowPanel
        projectId="p1"
        examples={{ experiment: "Budget: one 500 m test track, two weeks, no cloud computing." }}
      />,
    );

    await userEvent.click(
      await screen.findByRole("button", { name: /use the example input for design experiments/i }),
    );

    const input = screen.getByRole("textbox", { name: /design experiments/i });
    expect(input).toHaveValue("Budget: one 500 m test track, two weeks, no cloud computing.");
    // Only the cards with an example get the button.
    expect(screen.getAllByRole("button", { name: /use the example input/i })).toHaveLength(1);
  });

  it("offers every research workflow", async () => {
    render(<WorkflowPanel projectId="p1" />);

    expect(await screen.findByText("Compare papers")).toBeInTheDocument();
    expect(screen.getByText("Detect research gaps")).toBeInTheDocument();
    expect(screen.getByText("Generate hypotheses")).toBeInTheDocument();
    expect(screen.getByText("Design experiments")).toBeInTheDocument();
    expect(screen.getByText("Patent awareness")).toBeInTheDocument();
    expect(screen.getByText("Check what is new here")).toBeInTheDocument();
    expect(screen.getByText("Literature review")).toBeInTheDocument();
  });

  it("describes the novelty workflow by its limit, not by a promise", async () => {
    render(<WorkflowPanel projectId="p1" />);

    expect(
      await screen.findByText(/it will not claim anything is novel in the field/i),
    ).toBeInTheDocument();
  });

  it("starts the matching flow and shows the result", async () => {
    const user = userEvent.setup();
    mocked.createTask.mockResolvedValue(aTask({ id: "t-cmp", status: "queued" }));
    mocked.getTask.mockResolvedValue(
      aTask({ id: "t-cmp", result: aTaskResult({ comparison: aComparison() }) }),
    );

    const onStarted = vi.fn();
    render(<WorkflowPanel projectId="p1" onTaskStarted={onStarted} />);

    await user.click(screen.getAllByRole("button", { name: /^Run$/ })[0]);

    await waitFor(() => expect(mocked.createTask).toHaveBeenCalled());
    // Third argument is the forced flow — the UI must not rely on routing here.
    expect(mocked.createTask.mock.calls[0][2]).toBe("compare");
    expect(onStarted).toHaveBeenCalledWith("t-cmp");

    expect(await screen.findByText("Focus of the work")).toBeInTheDocument();
    expect(screen.getByText(/Retrieval grounds the answer in the source text/i)).toBeInTheDocument();
  });

  it("renders a failed run's error rather than a blank panel", async () => {
    const user = userEvent.setup();
    mocked.createTask.mockResolvedValue(aTask({ id: "t-failed", status: "queued" }));
    mocked.getTask.mockResolvedValue(aFailedTask());

    render(<WorkflowPanel projectId="p1" />);
    await user.click(screen.getAllByRole("button", { name: /^Run$/ })[0]);

    expect(
      await screen.findByText(/the vector store is unreachable/i),
    ).toBeInTheDocument();
    // And the run panel is genuinely populated, not an empty shell.
    expect(screen.getByText(/Run progress/i)).toBeInTheDocument();
  });

  it("surfaces an API failure when the run cannot even start", async () => {
    const user = userEvent.setup();
    mocked.createTask.mockRejectedValue(new ApiError("Project not found", 404));

    render(<WorkflowPanel projectId="p1" />);
    await user.click(screen.getAllByRole("button", { name: /^Run$/ })[0]);

    expect(await screen.findByText("Project not found")).toBeInTheDocument();
  });

  it("keeps a started run visible when its first status poll fails", async () => {
    const user = userEvent.setup();
    mocked.createTask.mockResolvedValue(aTask({ id: "t-poll", status: "queued" }));
    mocked.getTask.mockRejectedValue(new Error("temporary network error"));

    render(<WorkflowPanel projectId="p1" />);
    await user.click(screen.getAllByRole("button", { name: /^Run$/ })[0]);

    expect(await screen.findByText(/Run progress/i)).toBeInTheDocument();
    expect(await screen.findByText(/Could not check workflow progress\. Retrying/i)).toBeInTheDocument();
  });

  it("reviews a pasted project description as the project flow", async () => {
    const user = userEvent.setup();
    mocked.createTask.mockResolvedValue(aTask({ id: "t-proj", status: "queued" }));
    mocked.getTask.mockResolvedValue(aTask({ id: "t-proj" }));
    render(<WorkflowPanel projectId="p1" />);

    const box = await screen.findByRole("textbox", { name: "Review my project" });
    const button = screen.getByRole("button", { name: /Review project/ });

    // Too short to be a description: the button waits and says why.
    await user.type(box, "A robot for railway cracks.");
    expect(button).toBeDisabled();
    expect(screen.getByText(/\/ 200 characters minimum/)).toBeInTheDocument();

    const description = "We are building a low-cost robot that detects cracks in railway tracks. ".repeat(4);
    await user.clear(box);
    await user.click(box);
    await user.paste(description);
    expect(button).toBeEnabled();
    await user.click(button);

    await waitFor(() => expect(mocked.createTask).toHaveBeenCalled());
    expect(mocked.createTask.mock.calls[0][1]).toBe(description.trim());
    expect(mocked.createTask.mock.calls[0][2]).toBe("project");
  });

  it("keeps the patent disclaimer visible before anything is run", async () => {
    render(<WorkflowPanel projectId="p1" />);
    expect(
      (await screen.findAllByText(/Research-support only/i)).length,
    ).toBeGreaterThan(0);
  });
});
