import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { NoveltyView } from "@/components/ResearchResults";
import { aNoveltyReport } from "@/test/fixtures";

/**
 * These assertions mirror the backend's: the component may report corpus
 * coverage and must never render a claim of novelty in the field. Most of what
 * follows checks that something is *absent*, because the failure mode worth
 * guarding against is the UI quietly overclaiming.
 */
describe("NoveltyView", () => {
  it("states the scope limit before any verdict", () => {
    render(<NoveltyView result={aNoveltyReport()} />);

    const notice = screen.getByText(/Scope: this project's sources only/);
    const firstVerdict = screen.getByText("Already covered by this project's sources");

    // Node.DOCUMENT_POSITION_FOLLOWING === 4: the verdict comes after the notice.
    expect(notice.compareDocumentPosition(firstVerdict) & 4).toBeTruthy();
  });

  it("never renders a claim that something is novel", () => {
    const { container } = render(<NoveltyView result={aNoveltyReport()} />);
    const text = container.textContent ?? "";

    for (const overclaim of [
      /this (claim|idea|approach) is novel/i,
      /\bunprecedented\b/i,
      /\boriginal contribution\b/i,
      /no prior work (exists|was found in the literature)/i,
      /\bnot been done before\b/i,
    ]) {
      expect(text).not.toMatch(overclaim);
    }

    // "novel in the field" may appear, but only inside a denial — every
    // occurrence must be preceded by "cannot say whether" or "was not assessed".
    const occurrences =
      text.match(/.{0,40}novel(?:ty)? in the field.{0,40}/gi) ?? [];
    expect(occurrences.length).toBeGreaterThan(0);
    for (const occurrence of occurrences) {
      expect(occurrence).toMatch(/cannot say whether|was not assessed|can be made from/i);
    }
  });

  it("labels a claim absent from the corpus without calling it original", () => {
    render(<NoveltyView result={aNoveltyReport()} />);

    expect(screen.getByText("Not found in this project's sources")).toBeInTheDocument();
    expect(
      screen.getByText(/No passage in the searched sources mentions this/),
    ).toBeInTheDocument();
    expect(screen.getByText(/not a finding of originality/)).toBeInTheDocument();
  });

  it("shows why field novelty was not assessed on every assessment", () => {
    const result = aNoveltyReport();
    render(<NoveltyView result={result} />);

    const reasons = screen.getAllByText(/Novelty in the field was not assessed/);
    expect(reasons).toHaveLength(result.assessments.length);
  });

  it("reveals the supporting passage behind a covered claim", async () => {
    const user = userEvent.setup();
    render(<NoveltyView result={aNoveltyReport()} />);

    const quote = "The transformer relies on self attention to process sequences in parallel.";
    expect(screen.queryByText(quote)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /attention\.pdf/ }));
    expect(screen.getByText(quote)).toBeInTheDocument();
  });

  it("reports the scope and how many unsupported notes were dropped", () => {
    render(<NoveltyView result={aNoveltyReport()} />);

    expect(
      screen.getByText(/Checked against 2 document\(s\) retrieved from this project/),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 unsupported note\(s\) dropped/)).toBeInTheDocument();
  });

  it("says so plainly when there is nothing to assess", () => {
    render(
      <NoveltyView
        result={aNoveltyReport({
          assessments: [],
          scope: "no documents from this project",
          note: "Nothing to assess — no claim was supplied.",
          uncited_notes_dropped: 0,
        })}
      />,
    );

    expect(screen.getByText(/Nothing to assess/)).toBeInTheDocument();
    expect(screen.queryByText(/unsupported note/)).not.toBeInTheDocument();
  });
});
