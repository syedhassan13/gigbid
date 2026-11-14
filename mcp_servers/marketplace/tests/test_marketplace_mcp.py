"""Marketplace server through an in-memory MCP client, with a fake adapter (no GigSim needed)."""
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.marketplace import server as srv


class FakeAdapter:
    name = "fake"
    calls = []

    def submit_proposal(self, job_id, cover_letter, bid_amount, screening_answers, idempotency_key, dry_run, variant):
        FakeAdapter.calls.append((idempotency_key, dry_run))
        return {"id": "p-1", "status": "submitted", "connects_cost": 12, "connects_balance_after": 88, "dry_run": dry_run, "violations": []}

    def get_job(self, job_id):
        from mcp_servers.marketplace.adapters.base import NotFound
        raise NotFound("job not found")


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(srv, "_adapter", lambda acct, trace: FakeAdapter())
    FakeAdapter.calls.clear()


@pytest.mark.asyncio
async def test_annotations_and_schemas():
    async with connect(srv.mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert tools["search_jobs"].annotations.readOnlyHint is True
        assert tools["submit_proposal"].annotations.destructiveHint is True and tools["submit_proposal"].annotations.idempotentHint is True
        assert tools["create_proposal_draft"].inputSchema["$defs"]["ProposalDraftIn"]["properties"]["cover_letter"]["minLength"] == 50


@pytest.mark.asyncio
async def test_idempotent_submit_never_submits_twice():
    draft = {"job_id": "j-123", "cover_letter": "x" * 60, "bid_amount": 50}
    async with connect(srv.mcp._mcp_server) as s:
        d = (await s.call_tool("create_proposal_draft", {"draft": draft, "idempotency_key": "test-draft-key-1"})).structuredContent
        k = "test-submit-key-" + d["draft_id"]
        r1 = (await s.call_tool("submit_proposal", {"draft_id": d["draft_id"], "idempotency_key": k})).structuredContent
        r2 = (await s.call_tool("submit_proposal", {"draft_id": d["draft_id"], "idempotency_key": k})).structuredContent
    assert r1["status"] == "submitted" and r2["idempotent_replay"] is True
    assert [c for c in FakeAdapter.calls if not c[1]].count((k, False)) <= 1


@pytest.mark.asyncio
async def test_errors_are_structured():
    async with connect(srv.mcp._mcp_server) as s:
        r = await s.call_tool("get_job", {"job_id": "j-missing"})
        assert r.isError and "not_found" in r.content[0].text
