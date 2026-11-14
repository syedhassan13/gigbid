# Runbook

## Start
* Local, no Docker: `python scripts/dev.py --demo` (GigSim on :8100, API on :8000, web on :5173).
* Full stack: `cp .env.example .env` (fill in the keys), then `docker compose -f infra/docker-compose.yml up --build`.
  The web app is served on :8080 and the API on :8000.
* Single container (Hugging Face Space): the root `Dockerfile` (see DEPLOY below).

## Schedules and why
| Job | GigSim | Live Upwork | Justification |
|---|---|---|---|
| Scout saved searches | every `scout.interval_minutes` (180) | every `marketplace.live_poll_minutes` (240), reads only | Freelance jobs stay open for days; a 3–4 h cadence catches them while staying far from anything that looks like scraping. Each run issues one search per saved search (≈6 calls). |
| Pipeline sync (`get_events`) | every 10 min (Arq cron) / 60 s (embedded) | every 240 min | Cheap incremental read keyed by event sequence number. |
| GigSim auto-tick | 30–60 s | – | Simulator time only. |

Rate limits: the Marketplace MCP server's token bucket (60/min/user) stays below GigSim's 120/min. The
GigSim adapter honours `Retry-After`, backs off on 5xx, and never retries a write without its idempotency key.

## Idempotency (worker restarts)
* Thread ids are deterministic: `bid:<user>:<job>`, `conv:<user>:<thread>:<n_messages>`. `analyse_job` returns
  the cached result for a finished thread, so a restart never re-analyses a job.
* Submits and messages carry keys derived from the thread and draft. The marketplace server and GigSim both
  deduplicate them.
* `tick_all → retry_queued` resumes threads left `approved` (submit queued during an outage) or `dead_letter`.

## Degraded mode (viva: "kill the marketplace server")
`/api/health` probes the Marketplace MCP server and GigSim, and the UI shows a red banner
(`DegradedBanner` in `apps/web/src/components/Layout.tsx`). Graph nodes catch `ServerUnavailable`
(`agent/mcp_client.py`) and move the job to `dead_letter` or keep a submit queued. Nothing is sent, and work
resumes on the next tick once the server is back.

## Crash-and-resume demo
1. Open a job awaiting approval in the Proposal Studio.
2. Kill the API (`Ctrl+C` / `docker compose kill api`) and restart it.
3. Refresh the page. The approval is still there because it is read from the checkpointer.
4. Approve. `GET /v1/proposals` on GigSim shows exactly one proposal. `tests/integration/test_bid_graph_gigsim.py`
   automates this, including a forced re-run of the submit node.

## Replay any job from any node
Run viewer → Checkpoints, or `POST /api/runs/{thread_id}/replay/{checkpoint_id}`.

## Live mode (Upwork)
Set `marketplace.adapter: upwork_live` or connect Upwork in Settings, which runs OAuth 2.1 with PKCE and
dynamic client registration and stores tokens encrypted with `TOKEN_ENC_KEY`. Writes become drafts that the
user confirms on Upwork. There is no browser automation, no cookies and no scraping.

## Deploy (Hugging Face Docker Space)
1. Create a Space (SDK: Docker), add secrets `GROQ_API_KEY`, `JWT_SECRET`, `TOKEN_ENC_KEY`, `REVIEWER_EMAIL`,
   `REVIEWER_PASSWORD`, and optionally `LANGSMITH_API_KEY`.
2. `git remote add space https://huggingface.co/spaces/<user>/gigbid && git push space main`.
3. Port 7860 is set in the Space README header (`app_port: 7860`).

## Secrets
Secrets come from the environment only. `.env` is git-ignored, CI fails if a key-like string or `.env` is
committed, OAuth tokens are encrypted at rest, and PII is masked in logs, traces and the audit log.
