import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import { describeError, isRetryable } from "@/lib/errorMessage";

/**
 * The backend distinguishes "you asked for something impossible" (4xx) from
 * "come back shortly" (0 / 429 / 503). These assert the UI keeps that
 * distinction, because telling someone to retry a 404 wastes their time and
 * telling them a 503 is their fault wastes more of it.
 */
describe("describeError", () => {
  it("keeps the server's own explanation", () => {
    const error = new ApiError("The vector store is not reachable.", 503);
    expect(describeError(error, "fallback")).toContain("The vector store is not reachable.");
  });

  it("adds the wait the server asked for", () => {
    const error = new ApiError("Too many requests: the limit is 20 per 60s.", 429, 17);
    expect(describeError(error, "fallback")).toBe(
      "Too many requests: the limit is 20 per 60s. Try again in about 17s.",
    );
  });

  it("includes the correlation id so a failure can be reported precisely", () => {
    const error = new ApiError("Something went wrong.", 500, null, "a1b2c3");
    expect(describeError(error, "fallback")).toContain("(request a1b2c3)");
  });

  it("falls back only when the failure is not an API response at all", () => {
    expect(describeError(new TypeError("undefined is not a function"), "Upload failed")).toBe(
      "Upload failed",
    );
    expect(describeError("nope", "Upload failed")).toBe("Upload failed");
  });

  it("does not invent a retry hint the server did not give", () => {
    const error = new ApiError("Project not found", 404);
    expect(describeError(error, "fallback")).toBe("Project not found");
  });
});

describe("isRetryable", () => {
  it.each([
    [0, "backend unreachable"],
    [429, "rate limited"],
    [503, "dependency outage"],
  ])("treats %i (%s) as worth retrying", (status) => {
    expect(isRetryable(new ApiError("x", status))).toBe(true);
  });

  it.each([
    [400, "bad request"],
    [404, "not found"],
    [413, "body too large"],
    [500, "server bug"],
  ])("does not offer a retry for %i (%s)", (status) => {
    expect(isRetryable(new ApiError("x", status))).toBe(false);
  });

  it("is false for anything that is not an API error", () => {
    expect(isRetryable(new Error("boom"))).toBe(false);
  });
});

describe("ApiError carries what the server sent", () => {
  it("defaults the optional fields rather than leaving them undefined", () => {
    const error = new ApiError("plain", 400);
    expect(error.retryAfterSeconds).toBeNull();
    expect(error.requestId).toBeNull();
  });

  it("is a real Error, so it survives instanceof across a throw", () => {
    try {
      throw new ApiError("thrown", 503, 30, "req1");
    } catch (caught) {
      expect(caught).toBeInstanceOf(ApiError);
      expect((caught as ApiError).status).toBe(503);
      expect((caught as ApiError).isTransient).toBe(true);
    }
  });
});
