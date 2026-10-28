# Handoff: continuing MAIROS from another account

Written 28 October 2026, at the end of a long working session, so that work can
continue from a different Claude account (or a different machine) without the
original chat. **A new session should read this file first**, then the README.

---

## 1. Where everything lives

| What | Where | Access needed |
|---|---|---|
| Code | GitHub, private: `NeerajMoorthy/MAIROS`, branch `main` | Add the new account's GitHub user as a collaborator, or sign in as NeerajMoorthy |
| Website | Vercel project `mairos` (account `moorthyneeraj2008-5702`), https://mairos.vercel.app | `npx vercel login` in `apps/web` with that Vercel account |
| Backend (demo) | Runs on the owner's PC and is reached through a tunnel; see section 4 | The PC, plus the tunnel's account if ngrok |
| Groq API key | `mairos/.env` (`GROQ_API_KEY=…`) — **never committed** | Copy `.env.example` to `.env` and paste the key on the new machine |
| Demo data | `mairos-deploy-data/` beside the repository (not in git) | Only on the owner's PC |
| Sample project | `output/sample-project/` (in git); regenerate with `scripts/generate_sample_project.py` | — |

No secret is stored in the repository. Tokens pasted into the old chat (a
Hugging Face token, early on) should be revoked if that has not been done.

## 2. Getting a new machine or session running

```bash
git clone https://github.com/NeerajMoorthy/MAIROS.git mairos
cd mairos
python -m venv .venv && .venv\Scripts\pip install -r apps\api\requirements.txt
copy .env.example .env          # then set GROQ_API_KEY
cd apps\web && npm ci
```

Run locally: README, *Run it*. Run every test before changing anything:

```bash
.venv\Scripts\python -m pytest -q          # expect 695 passed, 9 skipped
cd apps\web && npm test                     # expect 151 passed
```

## 3. State of the project

- **Progress:** 93.75% — 30 of 32 required items (`docs/ROADMAP.md`). Open:
  (1) live-model validation and RAGAS figures, which need 15–20 real papers and
  spend Groq quota; (2) a full manual pass with
  `docs/SAMPLE_PROJECT_WALKTHROUGH.md`.
- **Architecture:** an orchestrator with a router and 15 registered agents, each
  used by at least one flow (a test enforces this). Chat & Q&A runs through the
  `answer` flow like every workflow. Evaluation is computed, not an agent, by
  design. See README, *Agents*.
- **Recent work (27–28 Oct), in the commit that lands with this file:**
  - Chat answers through the orchestrator; `/chat` streams each agent step.
  - The unused Planner agent was removed.
  - Agent Activity shows each run as a tree: the Orchestrator at the root and
    one table per assigned agent (`components/OrchestrationTree.tsx`).
  - The sidebar's "Backend offline" box was removed.
  - Knowledge graph: uploaded papers are nodes linked to their concepts; a
    deterministic concept extractor (`services/knowledge_graph/concepts.py`)
    is used offline and whenever the model call fails; the graph viewer's
    layout forces now actually apply.
  - Patent awareness, which matches patents against those concepts, now finds
    claim-level overlaps on the sample project ("convolutional neural network"
    in claim 2).
- **Deferred plan:** `docs/MIGRATION_WORKERS.md` (Cloudflare Workers +
  Supabase), on hold until there is a budget for it.

## 4. The live demo — and the decision waiting

https://mairos.vercel.app forwards `/api` to `MAIROS_API_URL`, a tunnel to the
API on the owner's PC (`scripts/publish_demo.py`; `docs/LIVE_DEMO.md`).

**On 28 October the site has no backend**, and a choice is pending:

| Option | Status |
|---|---|
| ngrok, fixed domain `maximize-aground-booted.ngrok-free.dev` | Worked on 26 Oct. On 27 Oct Microsoft Defender quarantined `ngrok.exe` as `Trojan:Win32/Kepavll!rfn` (a reputation detection common for ngrok). Restoring it is the owner's decision. Then: `publish_demo.py --ngrok-domain maximize-aground-booted.ngrok-free.dev` |
| Cloudflare quick tunnel | Blocked on the network the PC used on 28 Oct (UDP and TCP 7844 both refused). Works on other networks: `publish_demo.py --cloudflare` |
| localhost.run (SSH, port 22) | Reachable on that network and needs no install, but not yet approved by the owner; it would have to be added to `publish_demo.py` |

After the tunnel is up: `publish_demo.py --restart-api` (loads the 27–28 Oct
backend code) and `publish_demo.py --redeploy` (puts the new tree, sidebar and
graph viewer on Vercel). Then check the site, Agent Activity, the Knowledge
Graph tab and the Patents page with the sample project.

## 5. How the owner wants work done

These came up repeatedly; a new session should follow them.

- **Ask before any live run** that spends Groq quota. Verify offline first
  (the offline model and recorded fixtures), then ask.
- **Ask before taking decisions on your own**: propose, say what you would do,
  and let the owner choose.
- **Commit and push only when asked.** Commits are authored as
  *Moorthy Neeraj* (repo-local git config).
- **Never handle secrets.** The owner types tokens and keys into terminals
  themselves; never paste them into chat or files.
- **Fix with a regression test** that fails on the old code, and say so.
- Keep the project's boundaries: findings are computed, never generated; no
  legal conclusions in patent output; field novelty is always "not assessed";
  every claim keeps its citation.
- **Free tools only** for now (5-day demo window from 26 Oct; the plan may
  change with the owner's budget).

## 6. Things not to lose

- `scripts/start_demo.bat` — a double-click starter for the demo, added by the
  owner; not yet committed.
- The professor will check **patent awareness and the knowledge graph** in
  particular; both were verified on the sample project offline on 28 Oct, but
  not yet on the live site with the live model.
