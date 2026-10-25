/**
 * Build-time feature switches. Every integration is opt-in, so an empty
 * environment is the local-first app exactly as before: no login, no
 * analytics, API proxied to 127.0.0.1:8000.
 *
 * `NEXT_PUBLIC_*` values are inlined into the client bundle at build time.
 */

/** Better Auth sign-in, and bearer tokens on every API call. */
export const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";

/** Google Analytics 4 measurement id, e.g. `G-XXXXXXXXXX`. Empty = no analytics. */
export const GA_MEASUREMENT_ID = (process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID ?? "").trim();

/** Social sign-in buttons to show; the server must have matching credentials. */
export const SOCIAL_PROVIDERS = (process.env.NEXT_PUBLIC_AUTH_SOCIAL ?? "")
  .split(",")
  .map((name) => name.trim().toLowerCase())
  .filter((name): name is "github" | "google" => name === "github" || name === "google");
