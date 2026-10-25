import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EvaluationPage from "@/app/evaluation/page";
import { ApiError, api } from "@/lib/api";
import { aGoldenSet, aProject, anEvalReport, anEvaluationStatus } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  mocked.evaluationStatus.mockResolvedValue(anEvaluationStatus());
  mocked.evaluationGoldenSet.mockResolvedValue(aGoldenSet());
  mocked.listProjects.mockResolvedValue([aProject()]);
});

describe("Evaluation page", () => {
  it("shows a loading state before the status arrives", () => {
    mocked.evaluationStatus.mockReturnValue(new Promise(() => {}));
    render(<EvaluationPage />);

    expect(screen.getAllByRole("status", { name: /loading/i }).length).toBeGreaterThan(0);
  });

  it("says plainly that answer-quality metrics are unavailable, and why", async () => {
    render(<EvaluationPage />);

    expect(
      await screen.findByText(/Answer-quality metrics are unavailable/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/No placeholder score is shown/i)).toBeInTheDocument();
    // Both conditions are reported, so the reader knows which one to fix.
    expect(screen.getByText(/RAGAS installed: false · live model: false/i)).toBeInTheDocument();
  });

  it("offers answer-quality scoring only when it can actually be produced", async () => {
    mocked.evaluationStatus.mockResolvedValue(
      anEvaluationStatus({
        answer_metrics_available: true,
        answer_metrics_reason: "ready",
        ragas_installed: true,
        llm_live: true,
      }),
    );
    render(<EvaluationPage />);

    expect(await screen.findByRole("checkbox")).toBeInTheDocument();
    expect(
      screen.queryByText(/Answer-quality metrics are unavailable/i),
    ).not.toBeInTheDocument();
  });

  it("hides the answer-quality option when it cannot be produced", async () => {
    render(<EvaluationPage />);
    await screen.findByRole("button", { name: /Run evaluation/i });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("labels model-judged scores as such, separately from computed metrics", async () => {
    const user = userEvent.setup();
    mocked.evaluationStatus.mockResolvedValue(
      anEvaluationStatus({ answer_metrics_available: true, ragas_installed: true, llm_live: true }),
    );
    mocked.runEvaluation.mockResolvedValue(
      anEvalReport({
        ragas: {
          available: true,
          metrics: ["faithfulness", "answer_relevancy", "context_precision", "context_recall"],
          scores: { faithfulness: 0.91, answer_relevancy: 0.88, context_precision: 0.7, context_recall: 0.65 },
          per_case: [],
          judged_by: "llama-3.3-70b-versatile",
          reason: "ok",
          note: "One model's assessment of another model's answers.",
          kind: "model_judged",
        },
      }),
    );

    render(<EvaluationPage />);
    await user.click(await screen.findByRole("button", { name: /Run evaluation/i }));

    expect(await screen.findByText("Answer quality")).toBeInTheDocument();
    expect(screen.getByText("model-judged")).toBeInTheDocument();
    expect(screen.getByText(/judged by llama-3.3-70b-versatile/i)).toBeInTheDocument();
    expect(screen.getByText("0.910")).toBeInTheDocument();
  });

  it("explains that a project must be indexed before anything can be scored", async () => {
    mocked.listProjects.mockResolvedValue([]);
    render(<EvaluationPage />);

    expect(await screen.findByText(/No projects yet/i)).toBeInTheDocument();
  });

  it("runs an evaluation and reports the four retrieval metrics", async () => {
    const user = userEvent.setup();
    mocked.runEvaluation.mockResolvedValue(anEvalReport());

    render(<EvaluationPage />);
    await user.click(await screen.findByRole("button", { name: /Run evaluation/i }));

    // Answer-quality scoring is opt-in and off by default.
    await waitFor(() => expect(mocked.runEvaluation).toHaveBeenCalledWith("p1", 5, false));

    expect(await screen.findByText("Recall@5")).toBeInTheDocument();
    expect(screen.getByText("0.800")).toBeInTheDocument();
    expect(screen.getByText("MRR")).toBeInTheDocument();
    expect(screen.getByText("0.750")).toBeInTheDocument();
  });

  it("marks a case whose evidence is absent instead of scoring it zero", async () => {
    const user = userEvent.setup();
    mocked.runEvaluation.mockResolvedValue(anEvalReport());

    render(<EvaluationPage />);
    await user.click(await screen.findByRole("button", { name: /Run evaluation/i }));

    expect(await screen.findByText(/1 not in corpus/i)).toBeInTheDocument();
    expect(screen.getByText(/not in this corpus/i)).toBeInTheDocument();
    expect(screen.getByText(/Excluded from the aggregates/i)).toBeInTheDocument();
  });

  it("shows a dash, not 0.000, when no case could be scored", async () => {
    // Regression (walkthrough K3): a corpus none of the cases applies to showed
    // 0.000 for every metric, which reads as a measured failure.
    const user = userEvent.setup();
    const unsupported = anEvalReport().cases.filter((c) => !c.supported);
    mocked.runEvaluation.mockResolvedValue(
      anEvalReport({
        aggregates: { recall_at_5: null, precision_at_5: null, mrr: null, ndcg_at_5: null, cases_evaluated: 0 },
        cases: unsupported,
        cases_total: unsupported.length,
        cases_evaluated: 0,
        cases_unsupported: unsupported.length,
      }),
    );

    render(<EvaluationPage />);
    await user.click(await screen.findByRole("button", { name: /Run evaluation/i }));

    expect(await screen.findByText("Recall@5")).toBeInTheDocument();
    expect(screen.queryByText("0.000")).not.toBeInTheDocument();
    for (const label of ["Recall@5", "MRR", "Precision@5", "nDCG@5"]) {
      expect(screen.getByText(label).parentElement).toHaveTextContent("—");
    }
    expect(screen.getByText(/no metric\s+could be computed/i)).toBeInTheDocument();
  });

  it("reveals which passages a case retrieved and which counted", async () => {
    const user = userEvent.setup();
    mocked.runEvaluation.mockResolvedValue(anEvalReport());

    render(<EvaluationPage />);
    await user.click(await screen.findByRole("button", { name: /Run evaluation/i }));

    await user.click(await screen.findByText(/How does retrieval-augmented generation/i));
    expect(await screen.findByText("relevant")).toBeInTheDocument();
    expect(screen.getByText(/Retrieval grounds answers and reduces hallucination/i)).toBeInTheDocument();
  });

  it("surfaces a failed run", async () => {
    const user = userEvent.setup();
    mocked.runEvaluation.mockRejectedValue(new ApiError("Project not found", 404));

    render(<EvaluationPage />);
    await user.click(await screen.findByRole("button", { name: /Run evaluation/i }));

    expect(await screen.findByText("Project not found")).toBeInTheDocument();
  });
});
