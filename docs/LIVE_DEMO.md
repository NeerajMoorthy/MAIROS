# The live demo: Vercel and this PC

> **Moving off the PC (28 October 2026):** the owner chose to run the API on a
> free Oracle Cloud VM so the site stays up without this PC. Once that is set up
> (`docs/ORACLE_VM.md`), this page describes the old setup; do not run
> `publish_demo.py` or Start MAIROS after the switch.

MAIROS is on the internet at **https://mairos.vercel.app**. The website runs
on Vercel; the API runs on the project owner's PC and is reached through a free
**ngrok** domain, `https://maximize-aground-booted.ngrok-free.dev` (since
26 October 2026; before that, a Cloudflare quick tunnel). It is up only while
that PC is on, awake, online and running it.

**27 October 2026:** Microsoft Defender quarantined `ngrok.exe` as
`Trojan:Win32/Kepavll!rfn`, a reputation-based detection that commonly hits
ngrok. Until the owner reviews it in Windows Security → Protection history,
the demo runs on a Cloudflare quick tunnel again (`publish_demo.py
--cloudflare`). Going back to ngrok is `publish_demo.py --ngrok-domain
maximize-aground-booted.ngrok-free.dev`.

**28 October 2026:** the PC's network still blocks Cloudflare's tunnel port
(TCP 7844 to both regions), so the demo moves to a **localhost.run** tunnel:
`publish_demo.py --localhost-run`, once; the choice is remembered, so Start
MAIROS (`start_demo.bat`) keeps using it. localhost.run needs no account and no
install (it uses the SSH client built into Windows, over port 22). Its address
(`https://<id>.lhr.life`) changes on every start and the free service may move
it while running; the script then sees the old address stop answering, opens a
new tunnel and redeploys (1-2 minutes).

Why ngrok: its address never changes, so a restart needs no redeploy, and it
runs over ordinary HTTPS. On 26 October the network this PC was on blocked the
ports Cloudflare's tunnel needs (outbound UDP and TCP 7844), and ngrok worked
there. ngrok's free plan shows a warning page to browsers; the website's
middleware adds the `ngrok-skip-browser-warning` header to every `/api` call
it forwards, so visitors never see it.

This is the single-user demo. The multi-user deployment (Cloudflare, Fly.io,
Supabase, Better Auth, Google Analytics) is described in
[DEPLOYMENT.md](DEPLOYMENT.md) and is built and tested but not deployed.

```
 browser ──► Vercel: Next.js site (mairos.vercel.app)
               │  /api/*  proxied to MAIROS_API_URL (next.config.js, fallback rewrite),
               │          with ngrok's skip-warning header (src/middleware.ts)
               ▼
             ngrok  https://maximize-aground-booted.ngrok-free.dev
               ▼
             this PC: uvicorn on 127.0.0.1:8010
               │  DATA_DIR = ..\mairos-deploy-data  (never apps/api/data)
               └─► Groq (the key in mairos/.env); arXiv, OpenAlex, Semantic Scholar
```

## Start it, or start it again

From `mairos/`:

```powershell
.venv\Scripts\python scripts\publish_demo.py
```

The script starts what is not already running:

1. **The API** on port 8010, with its own data folder, so projects on the
   local app (`apps/api/data`) are never published.
2. **The tunnel** to it: ngrok on the saved domain (set once with
   `--ngrok-domain`, after `ngrok config add-authtoken …`). The site reads the
   backend address when it is built, so the script redeploys it only when that
   address changes — with ngrok, only the first time. `--cloudflare` switches
   back to a Cloudflare quick tunnel, whose address changes on every start;
   `--localhost-run` to a localhost.run tunnel over SSH, likewise.

Both keep running in the background after the script ends, even if the
terminal is closed. Run the script after a reboot, or whenever the site's
sidebar says the backend is offline; if everything is still up, it changes
nothing and finishes in a few seconds.

| To | Run |
|---|---|
| Stop the demo | `.venv\Scripts\python scripts\publish_demo.py --stop` — the site stays up and shows the backend as offline |
| Load code changes into the API | `.venv\Scripts\python scripts\publish_demo.py --restart-api` — the tunnel and its address are kept, so the site needs no redeploy |
| Redeploy with the current tunnel | `.venv\Scripts\python scripts\publish_demo.py --redeploy` — needed after a change to the website itself (`apps/web`) |
| Read the logs | `mairos-deploy-data\logs\api.log` and `tunnel.log` |

The script needs the Vercel CLI to be logged in to the account that owns the
project. If it reports a failed `vercel` command, run `npx vercel login` in
`apps/web` and run the script again.

## Before you share the link

- **There is no sign-in.** Everyone with the link works in one shared
  workspace: they can open, change and delete every project in it, and every
  question they ask spends your Groq quota. Share the link only with people you
  trust, and keep private documents out of the demo. Turning on Better Auth
  ([DEPLOYMENT.md](DEPLOYMENT.md)) is what gives each user their own projects.
- **It is up only while this PC is.** Shutting down, sleeping or rebooting
  takes the API offline until the script is run again. To keep it up without
  the PC, see the deferred plan in [MIGRATION_WORKERS.md](MIGRATION_WORKERS.md)
  or the Fly.io route in [DEPLOYMENT.md](DEPLOYMENT.md).
- **ngrok's free plan has usage limits** (bandwidth and requests per month).
  A small demo stays well inside them; heavy use could reach them.
- **Visitors share rate limits.** Without sign-in the API counts requests per
  caller address, and behind Vercel that address is one of Vercel's servers,
  not the visitor's. The budget per address is 240 reads and 20 writes a
  minute, so several people working at once can see HTTP 429.
- **Uploads travel through the proxy.** PDFs of 4, 6 and 12 MB all reached the
  API through Vercel (12 MB in 27 s from this PC). The API's own cap is 40 MB.

The per-deployment addresses Vercel creates (`mairos-<id>-….vercel.app`) are
behind Vercel Authentication, which is on by default; only
`mairos.vercel.app` is public.

## How it was set up

Done once, on 25 October 2026:

1. **cloudflared** 2026.10.3 from
   [the cloudflared releases](https://github.com/cloudflare/cloudflared/releases),
   saved as `tools\cloudflared\cloudflared.exe` beside `mairos\` (the script
   also finds it on `PATH`, or takes `--cloudflared <path>`).
2. **The Vercel project**, from `apps/web`: `npx vercel login`, then
   `npx vercel project add mairos` and `npx vercel link --yes --project mairos`.
   - `apps/web/vercel.json` names the framework. A project created from the
     CLI starts without the Next.js preset, and the first build failed looking
     for a `public` output folder.
   - `apps/web/.vercelignore` keeps `node_modules`, build output and env files
     out of the upload. Vercel installs and builds on its own servers.
3. **The first run** of `publish_demo.py` set `MAIROS_API_URL` and deployed.

## What was checked

On 25 October 2026, through `https://mairos.vercel.app`:

| Check | Result |
|---|---|
| `/api/health` through the site | `"live": true` — Groq, `openai/gpt-oss-120b` |
| Create a project in the site | Created; the workspace opened |
| Upload a 10-page PDF | 201 after 20 s, most of it the embedding model loading for the first time; 10 chunks indexed and the analysis task completed |
| Larger uploads | 4, 6 and 12 MB request bodies reached the API |
| A chat question | Answered with cited passages (file, page, score) |
| The *Design experiments* workflow | Started as a task and polled through the proxy; gaps, hypotheses and designs rendered |
| Delete the project | 204; no project left |
| Browser console and network | No errors; every `/api` request returned 2xx |
| `publish_demo.py` | Started the API and a tunnel and redeployed; a second run reused both; `--stop` ended the API (launcher and server) and the tunnel; a new run brought the site back on a new tunnel |

The upload, chat and workflow checks ran with the API on the offline model, so
they spent no Groq quota; the live model was switched back on afterwards. **A
question answered by the live model through the site has not been run yet.**

## Other route tried: Hugging Face Spaces

`deploy/hf-space/` and `scripts/build_hf_space.py` package the API as a Docker
Space. Creating the Space was refused with HTTP 402: Docker Spaces need a paid
(PRO) account. The bundle is kept in case that changes.
