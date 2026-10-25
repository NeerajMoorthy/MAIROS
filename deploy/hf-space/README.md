---
title: MAIROS API
emoji: 🔬
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Backend API for the MAIROS research assistant
---

# MAIROS API

The FastAPI backend of MAIROS, a multi-agent research assistant. The MAIROS
website (on Vercel) forwards every `/api` request here; this Space has no user
interface of its own.

- Health check: `/api/health`
- Interactive API docs: `/docs`

## Settings this Space needs

| Name | Kind | Value |
|---|---|---|
| `GROQ_API_KEY` | **Secret** | Your Groq API key. Without it, the API runs on the offline fallback model. |

The models (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`) are set in the
Dockerfile and can be overridden with Space variables `DEFAULT_LLM` and
`FAST_LLM`.

## Limits on the free tier

- Data is not kept: projects, uploads and graphs are lost when the Space
  restarts or wakes from sleep.
- The Space sleeps after a period without visits; the first request after that
  waits while it starts again.
