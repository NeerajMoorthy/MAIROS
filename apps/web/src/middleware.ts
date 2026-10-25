/**
 * Sends signed-out visitors to /sign-in when authentication is enabled.
 *
 * This is an optimistic check — it only looks for Better Auth's session
 * cookie, because middleware runs at the edge without database access. It is a
 * convenience, not the security boundary: every API call is verified by the
 * backend (apps/api/app/auth.py), so a forged cookie gets a page shell and
 * nothing in it.
 *
 * The cookie names are read directly rather than through
 * `better-auth/cookies`, which pulls the whole JWT library into the edge
 * bundle to answer a question that needs two string comparisons.
 */

import { NextResponse, type NextRequest } from "next/server";

// Better Auth prefixes the cookie with `__Secure-` when served over HTTPS.
const SESSION_COOKIES = ["better-auth.session_token", "__Secure-better-auth.session_token"];

export function middleware(request: NextRequest) {
  if (process.env.NEXT_PUBLIC_AUTH_ENABLED !== "true") return NextResponse.next();

  if (!SESSION_COOKIES.some((name) => request.cookies.get(name)?.value)) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Pages only: not the API (the backend answers 401 itself), not the sign-in
  // page, and not static assets.
  matcher: ["/((?!api|sign-in|_next/static|_next/image|favicon.ico|icon.svg|robots.txt).*)"],
};
