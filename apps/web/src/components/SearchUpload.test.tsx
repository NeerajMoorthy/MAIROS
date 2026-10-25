import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SearchUpload } from "@/components/SearchUpload";
import { ApiError, api } from "@/lib/api";
import { aProjectDetail, aTask } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const props = {
  projectId: "p1",
  documents: aProjectDetail().documents,
  onTaskStarted: vi.fn(),
  onChanged: vi.fn(),
};

beforeEach(() => {
  mocked.listPapers.mockResolvedValue([]);
});

describe("SearchUpload", () => {
  it("prompts an empty project to start somewhere", async () => {
    render(<SearchUpload {...props} documents={[]} />);

    expect(await screen.findByText(/This project is empty/i)).toBeInTheDocument();
    expect(screen.getByText(/No documents yet/i)).toBeInTheDocument();
    expect(screen.getByText(/Run a topic search above/i)).toBeInTheDocument();
  });

  it("hides the getting-started prompt once documents exist", async () => {
    render(<SearchUpload {...props} />);

    await waitFor(() => expect(mocked.listPapers).toHaveBeenCalled());
    expect(screen.queryByText(/This project is empty/i)).not.toBeInTheDocument();
    expect(screen.getByText("attention.pdf")).toBeInTheDocument();
    expect(screen.getByText(/9 pages · 42 chunks/)).toBeInTheDocument();
  });

  it("confirms a started search and tracks its pipeline", async () => {
    const user = userEvent.setup();
    mocked.createTask.mockResolvedValue(aTask({ id: "t-search" }));
    mocked.getTask.mockResolvedValue(aTask({ id: "t-search" }));

    render(<SearchUpload {...props} />);
    await user.type(screen.getByPlaceholderText(/retrieval augmented generation/i), "rag");
    await user.click(screen.getByRole("button", { name: /Search/i }));

    expect(await screen.findByText(/Search started for "rag"/i)).toBeInTheDocument();
    expect(await screen.findByText(/Pipeline progress/i)).toBeInTheDocument();
  });

  it("reports a failed search without losing the form", async () => {
    const user = userEvent.setup();
    mocked.createTask.mockRejectedValue(new ApiError("Project not found", 404));

    render(<SearchUpload {...props} />);
    await user.type(screen.getByPlaceholderText(/retrieval augmented generation/i), "rag");
    await user.click(screen.getByRole("button", { name: /Search/i }));

    expect(await screen.findByText("Project not found")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/retrieval augmented generation/i)).toBeInTheDocument();
  });

  it("reports the indexed result after a successful upload", async () => {
    const user = userEvent.setup();
    mocked.uploadDocumentWithProgress.mockResolvedValue({
      document_id: "d2",
      filename: "paper.pdf",
      num_pages: 12,
      num_chunks: 64,
      task_id: "t-upload",
    });
    mocked.getTask.mockResolvedValue(aTask({ id: "t-upload" }));

    const { container } = render(<SearchUpload {...props} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));

    expect(
      await screen.findByText(/Uploaded "paper.pdf" — 12 pages, 64 chunks indexed/i),
    ).toBeInTheDocument();
  });

  it("explains a rejected upload", async () => {
    const user = userEvent.setup();
    mocked.uploadDocumentWithProgress.mockRejectedValue(
      new ApiError("No text could be extracted from this PDF.", 422),
    );

    const { container } = render(<SearchUpload {...props} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["scan"], "scan.pdf", { type: "application/pdf" }));

    expect(await screen.findByText(/No text could be extracted/i)).toBeInTheDocument();
  });
});
