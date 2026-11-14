import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.workspace.server import mcp


@pytest.mark.asyncio
async def test_slots_and_idempotent_hold():
    async with connect(mcp._mcp_server) as s:
        slots = (await s.call_tool("free_slots", {"from_date": "2026-11-16", "max_slots": 2})).structuredContent["result"]
        assert len(slots) == 2
        a = (await s.call_tool("create_tentative_hold", {"start": slots[0]["start"], "duration_minutes": 30, "title": "t", "idempotency_key": "hold-key-123"})).structuredContent
        b = (await s.call_tool("create_tentative_hold", {"start": slots[0]["start"], "duration_minutes": 30, "title": "t", "idempotency_key": "hold-key-123"})).structuredContent
        assert a["id"] == b["id"] and a["status"] == "tentative"
