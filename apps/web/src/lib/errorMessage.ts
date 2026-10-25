import { ApiError } from "@/lib/api";

/**
 * Turn a thrown value into something a researcher can act on.
 *
 * The backend already sends a useful `detail` for a rate limit or a dependency
 * outage, so the job here is not to replace that text but to add the two things
 * only the client knows what to do with: how long to wait, and the correlation
 * id to quote if the failure is worth reporting.
 *
 * `fallback` is used only when the thrown value is not an ApiError at all —
 * a programming error rather than a response — because inventing a friendly
 * sentence for an unknown failure would hide it.
 */
export function describeError(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;

  const parts = [error.message];

  if (error.retryAfterSeconds) {
    parts.push(`Try again in about ${error.retryAfterSeconds}s.`);
  }
  if (error.requestId) {
    parts.push(`(request ${error.requestId})`);
  }

  return parts.join(" ");
}

/** Whether the UI should offer a retry rather than ask the user to change something. */
export function isRetryable(error: unknown): boolean {
  return error instanceof ApiError && error.isTransient;
}
