import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "@/components/ChatPanel";
import { ApiError, api } from "@/lib/api";
import { aSource } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const { makeApiProxy } = await import("@/test/apiMock");
  return { ...actual, api: makeApiProxy() };
});

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

const liveHealth = {
  status: "ok",
  version: "0.2.0",
  llm: { provider: "groq", model: "llama-3.3-70b-versatile", live: true },
  projects: 1,
};

beforeEach(() => {
  mocked.health.mockResolvedValue(liveHealth);
});

async function ask(question: string) {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText(/Ask a question grounded/i), question);
  await user.click(screen.getByRole("button", { name: "" }).closest("button")!);
}

describe("ChatPanel", () => {
  it("explains what it does before the first question", async () => {
    render(<ChatPanel projectId="p1" />);
    expect(await screen.findByText(/Ask a question about this project/i)).toBeInTheDocument();
  });

  it("shows the answer with each source's page, score and graph badge", async () => {
    const user = userEvent.setup();
    mocked.query.mockResolvedValue({
      question: "q",
      answer: "Retrieval grounds the answer [rag.pdf, p. 2].",
      results: [aSource({ document_name: "rag.pdf", page: 2, score: 0.77, graph_hit: true })],
      graph_context: [],
    });

    render(<ChatPanel projectId="p1" />);
    await user.type(screen.getByPlaceholderText(/Ask a question grounded/i), "why?");
    await user.keyboard("{Enter}");

    expect(await screen.findByText(/Retrieval grounds the answer/i)).toBeInTheDocument();
    expect(screen.getByText("rag.pdf")).toBeInTheDocument();
    expect(screen.getByText("p. 2")).toBeInTheDocument();
    expect(screen.getByText(/score 0.77/)).toBeInTheDocument();
    expect(screen.getByText("graph")).toBeInTheDocument();
  });

  it("expands a source to its full passage on request", async () => {
    const user = userEvent.setup();
    const longText = `${"Retrieval grounds answers. ".repeat(12)}`;
    mocked.query.mockResolvedValue({
      question: "q",
      answer: "Answer",
      results: [aSource({ text: longText })],
      graph_context: [],
    });

    render(<ChatPanel projectId="p1" />);
    await user.type(screen.getByPlaceholderText(/Ask a question grounded/i), "why?");
    await user.keyboard("{Enter}");

    const toggle = await screen.findByRole("button", { name: /Show full passage/i });
    await user.click(toggle);
    expect(screen.getByRole("button", { name: /Show less/i })).toBeInTheDocument();
  });

  it("renders a failed question as an error message, not silence", async () => {
    const user = userEvent.setup();
    mocked.query.mockRejectedValue(new ApiError("Project not found", 404));

    render(<ChatPanel projectId="p1" />);
    await user.type(screen.getByPlaceholderText(/Ask a question grounded/i), "why?");
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Project not found")).toBeInTheDocument();
  });

  it("warns when answers are coming from the offline fallback model", async () => {
    mocked.health.mockResolvedValue({
      ...liveHealth,
      llm: { provider: "offline-fallback", model: "mairos-offline", live: false },
    });

    render(<ChatPanel projectId="p1" />);
    await waitFor(() =>
      expect(screen.getByText(/Running in offline LLM mode/i)).toBeInTheDocument(),
    );
  });

  it("stays quiet about the model when it is live", async () => {
    render(<ChatPanel projectId="p1" />);
    await waitFor(() => expect(mocked.health).toHaveBeenCalled());
    expect(screen.queryByText(/Running in offline LLM mode/i)).not.toBeInTheDocument();
  });
});
