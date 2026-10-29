import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "@/app/settings/page";
import { ApiError, api, type ExampleWorkspaceInfo } from "@/lib/api";
import { aProject } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const EXAMPLE: ExampleWorkspaceInfo = {
  name: "RailGuard Lite (example)",
  description: "Example workspace",
  files: [
    { name: "paper-a-camera-cnn.pdf", description: "Sample paper" },
    { name: "scanned-page.pdf", description: "Must be refused" },
  ],
  guide: [
    { feature: "Topic search", where: "search", flow: null, input: "railway crack detection", expect: "Papers" },
    { feature: "Compare papers", where: "workflows", flow: "compare", input: "Compare them", expect: "A table" },
  ],
};

beforeEach(() => {
  localStorage.clear();
  mocked.exampleWorkspace.mockResolvedValue(EXAMPLE);
  mocked.listProjects.mockResolvedValue([aProject({ id: "p1" }), aProject({ id: "p2" })]);
});

describe("Settings page", () => {
  it("loads the example data and links each guide step into it", async () => {
    mocked.loadExampleWorkspace.mockResolvedValue({
      project_id: "ex1",
      name: EXAMPLE.name,
      documents: [
        { document_id: "d1", filename: "a.pdf", num_pages: 2, num_chunks: 4, task_id: "t1" },
        { document_id: "d2", filename: "b.pdf", num_pages: 2, num_chunks: 4, task_id: "t2" },
      ],
      patent_id: "pat1",
      replaced: 0,
    });
    render(<SettingsPage />);

    await userEvent.click(await screen.findByRole("button", { name: /load example data/i }));

    expect(await screen.findByText(/2 papers \(8 passages\) and a patent/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open the example project/i })).toHaveAttribute("href", "/projects/ex1");
    const links = screen.getAllByRole("link", { name: /^open$/i });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/projects/ex1",
      "/projects/ex1?tab=workflows",
    ]);
    expect(localStorage.getItem("mairos:last-project-id")).toBe("ex1");
  });

  it("finds an example project that is already loaded", async () => {
    mocked.listProjects.mockResolvedValue([aProject({ id: "old-ex", name: EXAMPLE.name })]);
    render(<SettingsPage />);

    expect(await screen.findByRole("link", { name: /open the example project/i })).toHaveAttribute(
      "href",
      "/projects/old-ex",
    );
  });

  it("asks before clearing, and Cancel deletes nothing", async () => {
    render(<SettingsPage />);
    await screen.findByText("Try every feature");

    await userEvent.click(screen.getByRole("button", { name: /clear workspace/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/deletes all 2 projects/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mocked.clearWorkspace).not.toHaveBeenCalled();
  });

  it("clears the workspace once confirmed", async () => {
    localStorage.setItem("mairos:last-project-id", "p1");
    mocked.clearWorkspace.mockResolvedValue({ deleted: 2 });
    render(<SettingsPage />);
    await screen.findByText("Try every feature");

    await userEvent.click(screen.getByRole("button", { name: /clear workspace/i }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /delete everything/i }));

    expect(await screen.findByText(/deleted 2 projects/i)).toBeInTheDocument();
    expect(mocked.clearWorkspace).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem("mairos:last-project-id")).toBeNull();
  });

  it("shows why loading failed", async () => {
    mocked.loadExampleWorkspace.mockRejectedValue(new ApiError("The example papers could not be indexed: disk full", 500));
    render(<SettingsPage />);

    await userEvent.click(await screen.findByRole("button", { name: /load example data/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/disk full/i);
  });

  it("downloads a sample file", async () => {
    mocked.downloadSampleFile.mockResolvedValue("scanned-page.pdf");
    render(<SettingsPage />);

    await userEvent.click(await screen.findByRole("button", { name: /download scanned-page.pdf/i }));

    expect(mocked.downloadSampleFile).toHaveBeenCalledWith("scanned-page.pdf");
  });
});
