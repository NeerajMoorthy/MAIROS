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

/**
 * /api/* is proxied to the backend with the visitor's own headers. When the
 * backend sits behind a free ngrok domain, a browser User-Agent gets ngrok's
 * warning page instead of JSON unless this header is present. Any other
 * backend ignores it.
 */
function forwardToBackend(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set("ngrok-skip-browser-warning", "1");
  return NextResponse.next({ request: { headers } });
}

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith("/api/")) return forwardToBackend(request);
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
  // Pages (for the sign-in redirect), and /api/* only to add the header above:
  // the backend answers 401 itself. Not the sign-in page or static assets.
  matcher: [
    "/api/:path*",
    "/((?!api|sign-in|_next/static|_next/image|favicon.ico|icon.svg|robots.txt).*)",
  ],
};
