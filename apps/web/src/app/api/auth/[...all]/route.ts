/**
 * Better Auth's endpoints (/api/auth/*): sign-in, sign-up, session, the JWT
 * exchange, and the JWKS the backend verifies against.
 *
 * Every other /api/* path is proxied to FastAPI by the fallback rewrite in
 * next.config.js — fallback rewrites run after app routes, which is what lets
 * this route and the proxy share the /api prefix.
 */

import { getAuth } from "@/lib/auth";

export const dynamic = "force-dynamic";

const disabled = () =>
  Response.json({ detail: "Authentication is not enabled on this deployment." }, { status: 404 });

async function handle(request: Request): Promise<Response> {
  if (process.env.NEXT_PUBLIC_AUTH_ENABLED !== "true") return disabled();
  return getAuth().handler(request);
}

export const GET = handle;
export const POST = handle;
