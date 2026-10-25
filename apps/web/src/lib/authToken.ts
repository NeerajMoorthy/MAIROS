/**
 * Bearer tokens for the FastAPI backend.
 *
 * Better Auth keeps the session in an HTTP-only cookie on this site. The
 * backend is a different service and never sees that cookie; instead the JWT
 * plugin exchanges the session for a short-lived signed token
 * (`GET /api/auth/token`), which the backend verifies against the published
 * key set. The token is cached here until shortly before it expires, so the
 * exchange happens once per ~15 minutes rather than once per request.
 */

import { AUTH_ENABLED } from "@/lib/config";

const REFRESH_MARGIN_MS = 60_000;

let cached: { token: string; expiresAt: number } | null = null;
let inflight: Promise<string | null> | null = null;

function expiryOf(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" ? payload.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

async function fetchToken(): Promise<string | null> {
  try {
    const response = await fetch("/api/auth/token", { credentials: "include" });
    if (!response.ok) return null;
    const body = (await response.json()) as { token?: string };
    if (!body.token) return null;
    cached = { token: body.token, expiresAt: expiryOf(body.token) };
    return body.token;
  } catch {
    return null;
  } finally {
    inflight = null;
  }
}

/** The current API token, or `null` when signed out or auth is off. */
export async function getApiToken(): Promise<string | null> {
  if (!AUTH_ENABLED) return null;
  if (cached && cached.expiresAt - REFRESH_MARGIN_MS > Date.now()) return cached.token;
  // Concurrent callers share one exchange instead of racing several.
  inflight ??= fetchToken();
  return inflight;
}

/** Headers to add to a backend request. Empty in local mode. */
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await getApiToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Forget the cached token (sign-out, or a 401 from the backend). */
export function clearApiToken(): void {
  cached = null;
}

/** Send the browser to sign in, returning here afterwards. */
export function redirectToSignIn(): void {
  if (typeof window === "undefined" || window.location.pathname.startsWith("/sign-in")) return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.assign(`/sign-in?next=${next}`);
}
