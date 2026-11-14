"""GigSim adapter: REST client with bounded retries, backoff and Retry-After handling."""
from __future__ import annotations

import os
import time

import httpx

from mcp_servers.marketplace.adapters.base import MarketplaceUnavailable, NotFound, PolicyViolation, RateLimited


class GigSimAdapter:
    name = "gigsim"

    def __init__(self, token: str, base_url: str | None = None, trace_id: str = ""):
        self.base = (base_url or os.getenv("GIGSIM_URL", "http://127.0.0.1:8100")).rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "X-Trace-Id": trace_id}

    def _req(self, method: str, path: str, *, retries: int = 3, idem: str | None = None, **kw) -> dict:
        headers = dict(self.headers)
        if idem:
            headers["Idempotency-Key"] = idem
        last = None
        for attempt in range(retries + 1):
            try:
                r = httpx.request(method, self.base + path, headers=headers, timeout=10, **kw)
            except httpx.HTTPError as e:
                last = e
                time.sleep(min(4, 0.5 * 2 ** attempt))
                continue
            if r.status_code == 429:
                ra = float(r.headers.get("Retry-After", 2))
                if ra > 8 or attempt == retries:
                    raise RateLimited(ra)
                time.sleep(ra)
                continue
            if r.status_code >= 500:
                last = MarketplaceUnavailable(f"GigSim {r.status_code}")
                time.sleep(min(4, 0.5 * 2 ** attempt))
                continue
            if r.status_code == 404:
                raise NotFound(r.json().get("error", "not found"))
            if r.status_code == 422:
                raise PolicyViolation(str(r.json().get("error")))
            if r.status_code >= 400:
                raise PolicyViolation(f"{r.status_code}: {r.json().get('error')}")
            return r.json()
        raise MarketplaceUnavailable(f"GigSim unreachable: {last}")

    def search_jobs(self, query, category, posted_after, limit, include_dev):
        params = {"q": query, "limit": limit, "include_dev": include_dev}
        if category:
            params["category"] = category
        if posted_after:
            params["posted_after"] = posted_after
        return self._req("GET", "/v1/jobs", params=params)

    def get_job(self, job_id):
        return self._req("GET", f"/v1/jobs/{job_id}")

    def get_client(self, client_id):
        return self._req("GET", f"/v1/clients/{client_id}")

    def connects(self):
        return self._req("GET", "/v1/me/connects")

    def market_stats(self, category):
        return self._req("GET", "/v1/market/stats", params={"category": category})

    def policy(self):
        return self._req("GET", "/v1/policy")

    def submit_proposal(self, job_id, cover_letter, bid_amount, screening_answers, idempotency_key, dry_run, variant):
        body = {"job_id": job_id, "cover_letter": cover_letter, "bid_amount": bid_amount, "screening_answers": screening_answers,
                "dry_run": dry_run, "variant": variant}
        # writes: retry only transport errors; the idempotency key makes a retried call safe
        return self._req("POST", "/v1/proposals", json=body, idem=idempotency_key)

    def list_proposals(self):
        return self._req("GET", "/v1/proposals")

    def list_threads(self):
        return self._req("GET", "/v1/threads")

    def get_messages(self, thread_id):
        return self._req("GET", f"/v1/threads/{thread_id}/messages")

    def send_message(self, thread_id, text, idempotency_key, dry_run):
        return self._req("POST", f"/v1/threads/{thread_id}/messages", json={"text": text, "dry_run": dry_run}, idem=idempotency_key)

    def events(self, after):
        return self._req("GET", "/v1/events", params={"after": after})
