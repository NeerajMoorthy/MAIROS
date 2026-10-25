/** @type {import('next').NextConfig} */
const { PHASE_DEVELOPMENT_SERVER } = require("next/constants");

// Where /api/* is proxied. Local default: the uvicorn dev server. In
// production: the Fly.io app, e.g. https://mairos-api.fly.dev, or for the
// Vercel demo the tunnel set by scripts/publish_demo.py. Read when the config
// is evaluated, which on Vercel and Cloudflare is build time — set it in the
// build environment, not only as a Worker variable.
const API_URL = (
  process.env.MAIROS_API_URL ||
  process.env.NEXT_PUBLIC_API_URL || // older name, still honoured
  "http://127.0.0.1:8000"
).replace(/\/+$/, "");

module.exports = (phase) => ({
  reactStrictMode: true,
  poweredByHeader: false,
  // Keep `next dev` separate from `next build`: sharing .next can leave the
  // dev server loading production chunks (or vice versa) after a build runs.
  distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
  // Proxy /api to the FastAPI backend so the browser makes same-origin
  // requests (no CORS preflight, no base URL baked into the bundle).
  //
  // A *fallback* rewrite, not the default kind: fallback rewrites run after
  // every app route, including dynamic ones, so Better Auth's
  // /api/auth/[...all] route answers its own paths and only what no Next.js
  // route handles reaches the backend. An ordinary rewrite would win over the
  // dynamic auth route and forward sign-in requests to FastAPI.
  async rewrites() {
    return {
      fallback: [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }],
    };
  },
});
