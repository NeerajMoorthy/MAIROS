import { useRef, useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProjectExportDialog } from "@/components/ProjectExportDialog";
import { ApiError, api } from "@/lib/api";
import { expectNoViolations } from "@/test/a11y";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

function renderDialog() {
  return render(<ProjectExportDialog projectId="p1" open onOpenChange={() => {}} />);
}

describe("ProjectExportDialog", () => {
  it("downloads a ZIP without originals by default", async () => {
    const user = userEvent.setup();
    mocked.exportProject.mockResolvedValue("retrieval-survey-export-20261022.zip");
    renderDialog();

    expect(screen.getByLabelText(/Include the original PDFs/)).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));

    await waitFor(() => expect(mocked.exportProject).toHaveBeenCalledWith("p1", "zip", false));
    expect(await screen.findByRole("status")).toHaveTextContent("retrieval-survey-export-20261022.zip");
  });

  it("includes originals only when asked, and only in a ZIP", async () => {
    const user = userEvent.setup();
    mocked.exportProject.mockResolvedValue("x.zip");
    renderDialog();

    await user.click(screen.getByLabelText(/Include the original PDFs/));
    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));
    await waitFor(() => expect(mocked.exportProject).toHaveBeenCalledWith("p1", "zip", true));

    await user.click(screen.getByRole("radio", { name: /Single JSON file/ }));
    expect(screen.getByLabelText(/Include the original PDFs/)).toBeDisabled();
    expect(screen.getByLabelText(/Include the original PDFs/)).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: /Download JSON/ }));
    await waitFor(() => expect(mocked.exportProject).toHaveBeenLastCalledWith("p1", "json", false));
  });

  it("explains a failure", async () => {
    const user = userEvent.setup();
    mocked.exportProject.mockRejectedValue(new ApiError("Too many requests: try again in 30s.", 429));
    renderDialog();

    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Too many requests/);
  });

  it("returns keyboard focus to the control that opened it", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [open, setOpen] = useState(false);
      const ref = useRef<HTMLButtonElement>(null);
      return (
        <>
          <button ref={ref} onClick={() => setOpen(true)}>
            Export data
          </button>
          <ProjectExportDialog projectId="p1" open={open} onOpenChange={setOpen} returnFocusTo={ref} />
        </>
      );
    }
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Export data" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Export data" })).toHaveFocus();
  });

  it("lists what the archive contains, and has no WCAG violations", async () => {
    renderDialog();
    for (const file of ["chunks.jsonl / .csv", "graph.json", "tasks.jsonl", "evaluation.json"]) {
      expect(screen.getByText(file)).toBeInTheDocument();
    }
    await expectNoViolations(document.body);
  });
});
