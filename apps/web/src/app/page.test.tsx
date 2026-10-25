import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ProjectsPage from "@/app/page";
import { ApiError, api } from "@/lib/api";
import { aProject } from "@/test/fixtures";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
  useParams: () => ({}),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe("Projects page", () => {
  it("shows a loading placeholder before the list arrives", () => {
    mocked.listProjects.mockReturnValue(new Promise(() => {}));
    render(<ProjectsPage />);

    expect(screen.getAllByRole("status", { name: /loading/i }).length).toBeGreaterThan(0);
    expect(screen.queryByText(/No projects yet/i)).not.toBeInTheDocument();
  });

  it("invites the first project when none exist", async () => {
    mocked.listProjects.mockResolvedValue([]);
    render(<ProjectsPage />);

    expect(await screen.findByText(/No projects yet/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Create your first project/i }),
    ).toBeInTheDocument();
  });

  it("lists projects with their document and paper counts", async () => {
    mocked.listProjects.mockResolvedValue([
      aProject({ id: "p1", name: "Retrieval survey", num_documents: 3, num_papers: 7 }),
    ]);
    render(<ProjectsPage />);

    expect(await screen.findByText("Retrieval survey")).toBeInTheDocument();
    expect(screen.getByText(/3 docs/)).toBeInTheDocument();
    expect(screen.getByText(/7 papers/)).toBeInTheDocument();
  });

  it("surfaces a backend failure instead of an empty page", async () => {
    mocked.listProjects.mockRejectedValue(
      new ApiError("Cannot reach the MAIROS backend. Is it running on port 8000?", 0),
    );
    render(<ProjectsPage />);

    expect(await screen.findByText(/Cannot reach the MAIROS backend/i)).toBeInTheDocument();
  });

  it("creates a project and opens its workspace", async () => {
    const user = userEvent.setup();
    mocked.listProjects.mockResolvedValue([]);
    mocked.createProject.mockResolvedValue(aProject({ id: "new-id" }));

    render(<ProjectsPage />);
    await user.click(await screen.findByRole("button", { name: /Create your first project/i }));

    await user.type(screen.getByPlaceholderText(/Retrieval-Augmented Generation survey/i), "New work");
    await user.click(screen.getByRole("button", { name: /^Create project$/i }));

    await waitFor(() => expect(mocked.createProject).toHaveBeenCalledWith("New work", ""));
    expect(push).toHaveBeenCalledWith("/projects/new-id");
  });

  it("confirms and removes a project from the list", async () => {
    const user = userEvent.setup();
    mocked.listProjects.mockResolvedValue([aProject({ id: "p1", name: "Disposable project" })]);
    mocked.deleteProject.mockResolvedValue(undefined);
    render(<ProjectsPage />);

    await user.click(await screen.findByRole("button", { name: "Delete Disposable project" }));
    expect(screen.getByText(/permanently removes/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete project" }));

    await waitFor(() => expect(mocked.deleteProject).toHaveBeenCalledWith("p1"));
    expect(screen.queryByText("Disposable project")).not.toBeInTheDocument();
  });
});
