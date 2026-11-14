"""Adapter contract for the marketplace port. GigSim and live Upwork both implement it,
so the Marketplace MCP server (and therefore the agent graph) cannot tell which is in use."""
from __future__ import annotations

from typing import Protocol


class MarketplaceError(Exception):
    code = "error"


class MarketplaceUnavailable(MarketplaceError):
    code = "unavailable"


class RateLimited(MarketplaceError):
    code = "rate_limited"

    def __init__(self, retry_after: float):
        super().__init__(f"rate limited, retry after {retry_after:.0f}s")
        self.retry_after = retry_after


class NotFound(MarketplaceError):
    code = "not_found"


class PolicyViolation(MarketplaceError):
    code = "policy_violation"


class Adapter(Protocol):
    name: str

    def search_jobs(self, query: str, category: str | None, posted_after: str | None, limit: int, include_dev: bool) -> dict: ...
    def get_job(self, job_id: str) -> dict: ...
    def get_client(self, client_id: str) -> dict: ...
    def connects(self) -> dict: ...
    def market_stats(self, category: str) -> dict: ...
    def policy(self) -> dict: ...
    def submit_proposal(self, job_id: str, cover_letter: str, bid_amount: float, screening_answers: list[str],
                        idempotency_key: str, dry_run: bool, variant: str | None) -> dict: ...
    def list_proposals(self) -> dict: ...
    def list_threads(self) -> dict: ...
    def get_messages(self, thread_id: str) -> dict: ...
    def send_message(self, thread_id: str, text: str, idempotency_key: str, dry_run: bool) -> dict: ...
    def events(self, after: int) -> dict: ...
