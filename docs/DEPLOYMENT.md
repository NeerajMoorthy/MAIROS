# Deploying MAIROS

MAIROS still runs entirely on one machine with no accounts and no services —
that is the default and nothing below changes it. This guide is for putting it
on the internet for several users, with this stack:

| Concern | Service | Where it lives in the repo |
|---|---|---|
| Frontend hosting | **Cloudflare Workers** (Next.js via OpenNext) | `apps/web/wrangler.jsonc`, `apps/web/open-next.config.ts` |
| API server | **Fly.io** (FastAPI in a container, volume for data) | `fly.toml`, `apps/api/Dockerfile` |
| Database | **Supabase** Postgres (users, sessions, projects, tasks…) | `infra/supabase/migrations/0001_mairos.sql`, `apps/api/app/db.py` |
| Authentication | **Better Auth** (in Next.js) + JWT verification in FastAPI | `apps/web/src/lib/auth.ts`, `apps/api/app/auth.py` |
| Analytics | **Google Analytics 4** (page views only) | `apps/web/src/components/Analytics.tsx` |

Every one of these is switched on by configuration. Leave a variable empty and
that piece stays in its local-first form.

```
 browser ──► Cloudflare Worker (Next.js)
               │  /api/auth/*  → Better Auth ──► Supabase (user, session, jwks)
               │  /api/*       → proxied ──────► Fly.io FastAPI ──► Supabase (mairos.* tables)
               │                                   │  verifies the bearer JWT against
               │                                   │  https://<site>/api/auth/jwks
               │                                   └─► /data volume: Chroma index, graphs, uploads
               └─ GA4 page views (optional)
```

What lives where, and why:

- **Users, sessions and signing keys → Supabase**, written by Better Auth.
- **Projects, documents, papers, patents, tasks → Supabase**, schema `mairos`,
  written by the API through the same store surface SQLite used.
- **The vector index, knowledge graphs and uploaded PDFs → the Fly.io volume.**
  ChromaDB is embedded and the graphs are JSON files; moving the vectors to
  Supabase `pgvector` is possible but is a retrieval change, not a deployment
  one, and is not part of this build.

---

## 1. Supabase

1. Create a project. From **Project Settings → Database**, copy the
   **transaction pooler** connection string (port **6543**). This is
   `DATABASE_URL` for both the API and the frontend.
2. In the SQL editor, run `infra/supabase/migrations/0001_mairos.sql`. It creates
   the `mairos` schema and the Better Auth tables, and enables row-level
   security on every table with **no policies**.

   Why that matters: Supabase exposes the `public` schema through its Data API
   to anyone holding the project's *anon* key. A table there without RLS is
   readable by the world. RLS-with-no-policies refuses every Data API role;
   the app connects as the table owner and is unaffected. MAIROS never uses the
   Data API, so nothing needs a policy.
3. Optional but recommended: from `apps/web`, run Better Auth's own migrator,
   which tracks its schema version (the SQL file's Better Auth section matches
   1.x and is idempotent, so running both is safe):

   ```bash
   DATABASE_URL=... BETTER_AUTH_SECRET=... npm run auth:migrate
   ```

## 2. Fly.io (the API)

From the repository root (`mairos/`):

```bash
fly launch --no-deploy --copy-config        # creates the app from fly.toml
fly volumes create mairos_data --size 3     # Chroma, graphs, uploads
fly secrets set \
  GROQ_API_KEY=gsk_... \
  DATABASE_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres' \
  AUTH_JWKS_URL=https://mairos.example.com/api/auth/jwks \
  AUTH_ISSUER=https://mairos.example.com \
  AUTH_AUDIENCE=https://mairos.example.com
fly deploy
```

- The image installs CPU-only PyTorch and bakes in the embedding model, so a
  cold start does not depend on `huggingface.co`.
- **One machine, one worker, always on.** Agent runs execute in-process and the
  rate limiter is per process; a machine stopped mid-run would lose the run.
  `fly.toml` sets `auto_stop_machines = "off"` and `min_machines_running = 1`.
- `GET /health` reports `"metadata_store": "postgres"` and `"auth": "enabled"`
  when the secrets took effect.

## 3. Cloudflare (the frontend)

From `apps/web`:

```bash
npx wrangler secret put BETTER_AUTH_SECRET     # openssl rand -base64 32
npx wrangler secret put DATABASE_URL           # same Supabase pooler URL
# optional social sign-in
npx wrangler secret put GITHUB_CLIENT_ID
npx wrangler secret put GITHUB_CLIENT_SECRET

# Build-time variables: Next.js inlines these, so they must be present when
# the build runs (shell or CI), not only as Worker variables.
export MAIROS_API_URL=https://mairos-api.fly.dev
export NEXT_PUBLIC_AUTH_ENABLED=true
export NEXT_PUBLIC_GA_MEASUREMENT_ID=G-XXXXXXXXXX     # optional
export NEXT_PUBLIC_AUTH_SOCIAL=github                 # optional, comma-separated

npm run cf:deploy
```

Set `BETTER_AUTH_URL` in `wrangler.jsonc` (`vars`) to the public site URL. It
must equal `AUTH_ISSUER` / `AUTH_AUDIENCE` on the API, because the API checks
both claims.

**Version pin.** `@opennextjs/cloudflare` is pinned to `~1.15.1`: it is the last
release that supports Next.js 14 (1.16 and later require Next 15+, which would
mean a React 19 migration). Next is at 14.2.35, the version that release
requires.

## 4. Google Analytics

Set `NEXT_PUBLIC_GA_MEASUREMENT_ID` at build time. MAIROS then loads gtag with
IP anonymisation on and Google signals / ad personalisation off, and sends page
views only — no custom events, so no question, document or project name ever
reaches Google. Page paths contain project ids, never names. If you need a
consent banner for your jurisdiction, put it in front of `<Analytics />` in
`src/app/layout.tsx`.

---

## How authentication works

1. A user signs in on `/sign-in` (email + password, or GitHub/Google if
   configured). Better Auth sets an HTTP-only session cookie on the site.
2. Before calling the API, the browser exchanges that session for a 15-minute
   JWT at `/api/auth/token` (cached in memory, refreshed a minute before
   expiry) and sends it as `Authorization: Bearer …`.
3. FastAPI verifies the signature against the published key set
   (`/api/auth/jwks`, cached; refetched on an unknown key id, rate-limited),
   plus `exp`, `iss` and `aud`. Symmetric algorithms are refused outright.
4. One dependency (`authorize`) guards every API route and checks project
   ownership from the path — `project_id` directly, `task_id` through its
   project. Someone else's project answers **404**, so ids cannot be probed.
   Project and task lists are filtered to the caller's own.

The edge middleware that redirects signed-out visitors is a convenience; the
security boundary is the API.

**Projects created before auth was turned on** have no owner and are visible to
nobody (deliberately not to everybody). Assign them explicitly:

```bash
python scripts/assign_project_owner.py --list
python scripts/assign_project_owner.py --owner <better-auth-user-id> --all-unowned
```

## What was verified, and what was not

| Piece | Verified how |
|---|---|
| Postgres store | `tests/test_database_contract.py` passed against a real PostgreSQL 16 server (embedded), 22/22, with the same contract as SQLite |
| Supabase migration SQL | Applied twice to PostgreSQL 16 (idempotent); every table has RLS on |
| JWT verification and isolation | `tests/test_auth.py`: real Ed25519 tokens; expired, wrong issuer/audience, foreign key, HS256 confusion all refused; cross-user access is 404 on every project-scoped route |
| Cloudflare build | `npm run cf:build` produces `.open-next/worker.js` |
| Production Next build | `npm run build` clean, no edge-runtime warnings |
| **Not verified** | An actual deploy to Cloudflare, Fly.io or a hosted Supabase project, and a live Better Auth sign-in round trip — these need your accounts. |
