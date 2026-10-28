import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PatentsPage from "@/app/projects/[projectId]/patents/page";
import PrintablePatentFindings from "@/app/projects/[projectId]/patents/print/page";
import { ApiError, api } from "@/lib/api";
import { PATENT_DISCLAIMER, PATENT_FULL_DISCLAIMER, legalConclusionTerms } from "@/lib/patentCopy";
import { expectNoViolations } from "@/test/a11y";
import { aProjectDetail, aTask } from "@/test/fixtures";
import { aPatent, aPatentDetail, noFindings, someFindings } from "@/test/patentFixtures";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1" }),
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

function withPatents() {
  mocked.getProject.mockResolvedValue(aProjectDetail());
  mocked.listPatents.mockResolvedValue({ disclaimer: PATENT_DISCLAIMER, patents: [aPatent()] });
  mocked.getPatent.mockResolvedValue(aPatentDetail());
  mocked.patentFindings.mockResolvedValue(someFindings());
}

beforeEach(() => {
  mocked.patentSources.mockResolvedValue({
    disclaimer: PATENT_DISCLAIMER,
    full_disclaimer: PATENT_FULL_DISCLAIMER,
    fetches_documents: false,
    sources: [{ domain: "patents.google.com", name: "Google Patents" }],
    notes: [],
  });
});

describe("Patents page — the disclaimer in every state", () => {
  it("is shown while loading", () => {
    mocked.getProject.mockReturnValue(new Promise(() => {}));
    mocked.listPatents.mockReturnValue(new Promise(() => {}));
    mocked.patentFindings.mockReturnValue(new Promise(() => {}));
    render(<PatentsPage />);

    expect(screen.getByTestId("patent-disclaimer")).toHaveTextContent(PATENT_FULL_DISCLAIMER);
    expect(screen.getByRole("status", { name: /Loading patents/i })).toBeInTheDocument();
  });

  it("is shown on an error, with a retry", async () => {
    mocked.getProject.mockRejectedValue(new ApiError("The vector store is unreachable.", 503));
    mocked.listPatents.mockRejectedValue(new ApiError("The vector store is unreachable.", 503));
    mocked.patentFindings.mockRejectedValue(new ApiError("The vector store is unreachable.", 503));
    render(<PatentsPage />);

    expect(await screen.findByText(/Unable to load patents/i)).toBeInTheDocument();
    expect(screen.getByTestId("patent-disclaimer")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Retry/i }).length).toBeGreaterThan(0);
  });

  it("is shown when the project has no patents, and no-match is never a clearance", async () => {
    mocked.getProject.mockResolvedValue(aProjectDetail());
    mocked.listPatents.mockResolvedValue({ disclaimer: PATENT_DISCLAIMER, patents: [] });
    mocked.patentFindings.mockResolvedValue(noFindings());
    render(<PatentsPage />);

    expect(await screen.findByText(/No patents yet/i)).toBeInTheDocument();
    expect(screen.getByTestId("patent-disclaimer")).toBeInTheDocument();
    expect(await screen.findByText(/not a legal clearance/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run patent workflow/i })).toBeDisabled();
  });

  it("is shown with results, which explain their scores", async () => {
    withPatents();
    render(<PatentsPage />);

    const findings = await screen.findByRole("list", { name: /Patent wording overlaps/i });
    expect(screen.getByTestId("patent-disclaimer")).toBeInTheDocument();
    expect(within(findings).getAllByText(/Similarity score \(shared wording only\)/).length).toBe(2);
    expect(within(findings).getAllByRole("meter", { name: "Term rarity" })[0]).toHaveAttribute("aria-valuenow", "0.85");
    expect(within(findings).getByText(/Claim 1 · independent/)).toBeInTheDocument();
    expect(within(findings).getByText(/Claim 2 · dependent on claim 1/)).toBeInTheDocument();
  });
});

describe("Patents page — list and detail", () => {
  it("shows segmented claims and metadata for the selected patent", async () => {
    withPatents();
    render(<PatentsPage />);

    expect(await screen.findByRole("region", { name: "Patent metadata" })).toHaveTextContent("G06F 16/3347");
    const segmented = screen.getByRole("region", { name: "Segmented text" });
    expect(within(segmented).getByText("independent")).toBeInTheDocument();
    expect(within(segmented).getByText(/depends on claim 1/)).toBeInTheDocument();
  });

  it("adds a patent with its metadata", async () => {
    const user = userEvent.setup();
    withPatents();
    mocked.addPatent.mockResolvedValue(aPatent({ id: "pat-2", title: "New one", warnings: [] }));
    render(<PatentsPage />);

    await user.click(await screen.findByRole("button", { name: /^Add patent$/ }));
    const form = screen.getByRole("form", { name: "Add a patent" });
    await user.type(within(form).getByLabelText(/Title/), "New one");
    await user.type(within(form).getByLabelText("CPC codes"), "G06F 16/33, G06N 3/08");
    await user.type(within(form).getByLabelText("Inventors"), "Ada Lovelace, Alan Turing");
    await user.click(within(form).getByRole("button", { name: /Add patent/ }));

    await waitFor(() => expect(mocked.addPatent).toHaveBeenCalled());
    const [, input] = mocked.addPatent.mock.calls[0];
    expect(input.title).toBe("New one");
    expect(input.cpc_codes).toEqual(["G06F 16/33", "G06N 3/08"]);
    expect(input.inventors).toEqual(["Ada Lovelace", "Alan Turing"]);
  });

  it("asks for confirmation before removing a patent", async () => {
    const user = userEvent.setup();
    withPatents();
    mocked.deletePatent.mockResolvedValue(undefined);
    render(<PatentsPage />);

    await user.click(await screen.findByRole("button", { name: /Remove/ }));
    expect(screen.getByRole("dialog", { name: /Remove this patent/i })).toBeInTheDocument();
    expect(mocked.deletePatent).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Remove patent/ }));
    await waitFor(() => expect(mocked.deletePatent).toHaveBeenCalledWith("p1", "pat-1"));
  });

  it("exports Markdown and CSV through accessible controls", async () => {
    const user = userEvent.setup();
    withPatents();
    mocked.exportPatentFindings.mockResolvedValue("p1-patent-findings.csv");
    render(<PatentsPage />);

    await user.click(await screen.findByRole("button", { name: /Export CSV/ }));
    expect(mocked.exportPatentFindings).toHaveBeenCalledWith("p1", "csv");
    expect(await screen.findByRole("status")).toHaveTextContent(/carries the full disclaimer/);

    await user.click(screen.getByRole("button", { name: /Export Markdown/ }));
    expect(mocked.exportPatentFindings).toHaveBeenCalledWith("p1", "markdown");
    expect(screen.getByRole("link", { name: /Printable view/ })).toHaveAttribute("href", "/projects/p1/patents/print");
  });

  it("launches the patent workflow for this project", async () => {
    const user = userEvent.setup();
    withPatents();
    mocked.createTask.mockResolvedValue(aTask({ flow: "patent" }));
    render(<PatentsPage />);

    await user.click(await screen.findByRole("button", { name: /Run patent workflow/ }));
    await waitFor(() => expect(mocked.createTask).toHaveBeenCalled());
    expect(mocked.createTask.mock.calls[0][2]).toBe("patent");
    expect(push).toHaveBeenCalledWith("/tasks");
  });

  it("has no WCAG 2.1 AA violations axe can detect, populated", async () => {
    withPatents();
    const { container } = render(<PatentsPage />);
    await screen.findByRole("list", { name: /Patent wording overlaps/i });
    await screen.findByRole("region", { name: "Patent metadata" });
    await expectNoViolations(container);
  });

  it("has no WCAG violations in the add form", async () => {
    const user = userEvent.setup();
    withPatents();
    const { container } = render(<PatentsPage />);
    await user.click(await screen.findByRole("button", { name: /^Add patent$/ }));
    await expectNoViolations(container);
  });
});

describe("Printable view", () => {
  it("prints the full disclaimer at the top and the end, with citations written out", async () => {
    withPatents();
    render(<PrintablePatentFindings />);

    await screen.findByRole("region", { name: "Findings" });
    expect(screen.getByTestId("patent-disclaimer")).toHaveTextContent(PATENT_FULL_DISCLAIMER);
    expect(screen.getByRole("contentinfo")).toHaveTextContent(PATENT_FULL_DISCLAIMER);
    // On paper a citation chip cannot be clicked, so the passage is printed.
    expect(screen.getAllByText(/retrieval\.pdf, p\. 4 — “We build an embedding index/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Print/ })).toBeEnabled();
  });

  it("keeps the disclaimer when the findings cannot be loaded", async () => {
    mocked.getProject.mockRejectedValue(new ApiError("Project not found", 404));
    mocked.listPatents.mockRejectedValue(new ApiError("Project not found", 404));
    mocked.patentFindings.mockRejectedValue(new ApiError("Project not found", 404));
    render(<PrintablePatentFindings />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Project not found");
    expect(screen.getByTestId("patent-disclaimer")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent(PATENT_DISCLAIMER);
  });
});

describe("Wording audit — no legal conclusions in rendered patent output", () => {
  it("flags conclusions but permits the reviewed disclaimers", () => {
    expect(legalConclusionTerms("This may infringe claim 1")).toEqual(["infringe"]);
    expect(legalConclusionTerms("You are safe to proceed")).toEqual(["safe to"]);
    expect(legalConclusionTerms(PATENT_FULL_DISCLAIMER)).toEqual([]);
    // A negation is not a blanket pass: only the reviewed sentences are exempt.
    expect(legalConclusionTerms("This does not infringe")).toEqual(["infringe"]);
  });

  it.each([
    ["results", () => withPatents()],
    [
      "no match",
      () => {
        mocked.getProject.mockResolvedValue(aProjectDetail());
        mocked.listPatents.mockResolvedValue({ disclaimer: PATENT_DISCLAIMER, patents: [aPatent()] });
        mocked.getPatent.mockResolvedValue(aPatentDetail());
        mocked.patentFindings.mockResolvedValue(noFindings());
      },
    ],
  ])("the Patents page with %s", async (_label, arrange) => {
    arrange();
    const { container } = render(<PatentsPage />);
    await screen.findByRole("region", { name: "Patent metadata" });
    await waitFor(() => expect(mocked.patentFindings).toHaveBeenCalled());
    expect(legalConclusionTerms(container.textContent ?? "")).toEqual([]);
  });

  it("the printable view", async () => {
    withPatents();
    const { container } = render(<PrintablePatentFindings />);
    await screen.findByRole("region", { name: "Findings" });
    expect(legalConclusionTerms(container.textContent ?? "")).toEqual([]);
  });
});
