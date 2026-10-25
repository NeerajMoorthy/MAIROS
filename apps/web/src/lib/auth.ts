/**
 * Better Auth — server side. Runs inside Next.js (on Cloudflare Workers in
 * production, Node in development); never imported by client components.
 *
 * Users, sessions and the JWT signing keys live in Supabase Postgres
 * (`DATABASE_URL`). The JWT plugin is what connects this to the FastAPI
 * backend: it issues short-lived tokens (`/api/auth/token`) signed with a key
 * it publishes at `/api/auth/jwks`, and the backend verifies those tokens
 * without ever touching this database.
 *
 * Required server env when `NEXT_PUBLIC_AUTH_ENABLED=true`:
 *   BETTER_AUTH_SECRET  — 32+ random bytes (`openssl rand -base64 32`)
 *   BETTER_AUTH_URL     — the public site URL, e.g. https://mairos.example.com
 *   DATABASE_URL        — Supabase Postgres connection string (pooler, :6543)
 * Optional: GITHUB_CLIENT_ID/SECRET, GOOGLE_CLIENT_ID/SECRET.
 */

import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { jwt } from "better-auth/plugins";
import { Pool } from "pg";

function socialProviders() {
  const providers: Record<string, { clientId: string; clientSecret: string }> = {};
  if (process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET) {
    providers.github = {
      clientId: process.env.GITHUB_CLIENT_ID,
      clientSecret: process.env.GITHUB_CLIENT_SECRET,
    };
  }
  if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
    providers.google = {
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    };
  }
  return providers;
}

export function createAuth() {
  const baseURL = process.env.BETTER_AUTH_URL;
  return betterAuth({
    baseURL,
    secret: process.env.BETTER_AUTH_SECRET,
    // One connection per instance. On Workers an instance lives for one
    // request (see getAuth), and Supabase's pooler multiplexes behind it.
    database: new Pool({ connectionString: process.env.DATABASE_URL, max: 1 }),
    emailAndPassword: { enabled: true, minPasswordLength: 10 },
    socialProviders: socialProviders(),
    plugins: [
      jwt({
        // The backend checks both against AUTH_ISSUER / AUTH_AUDIENCE.
        jwt: { issuer: baseURL, audience: baseURL, expirationTime: "15m" },
      }),
      nextCookies(),
    ],
  });
}

type Auth = ReturnType<typeof createAuth>;

const onWorkers =
  typeof navigator !== "undefined" && navigator.userAgent === "Cloudflare-Workers";

let shared: Auth | null = null;

/**
 * The auth instance for this request.
 *
 * Cloudflare Workers forbid reusing an I/O object (a database socket) across
 * requests, so there a fresh instance is built per request. In Node one
 * instance — and one pool — is shared for the life of the process.
 */
export function getAuth(): Auth {
  if (onWorkers) return createAuth();
  shared ??= createAuth();
  return shared;
}
