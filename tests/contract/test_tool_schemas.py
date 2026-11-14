"""MCP tool-schema snapshot: fails CI when a tool signature changes unintentionally.
Update intentionally with:  UPDATE_SNAPSHOTS=1 pytest tests/contract"""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.marketplace.server import mcp as market
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace

SNAP = Path(__file__).parent / "tool_schemas.snapshot.json"


async def current() -> dict:
    out = {}
    for m in (portfolio, market, workspace):
        async with connect(m._mcp_server) as s:
            for t in (await s.list_tools()).tools:
                out[f"{m.name}.{t.name}"] = {"input": t.inputSchema, "output": t.outputSchema,
                                             "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None}
    return out


@pytest.mark.asyncio
async def test_tool_schemas_match_snapshot():
    cur = await current()
    if os.getenv("UPDATE_SNAPSHOTS") or not SNAP.exists():
        SNAP.write_text(json.dumps(cur, indent=1, sort_keys=True))
    snap = json.loads(SNAP.read_text())
    changed = sorted(k for k in set(cur) | set(snap) if cur.get(k) != snap.get(k))
    assert not changed, f"MCP tool signatures changed: {changed}. If intended: UPDATE_SNAPSHOTS=1 pytest tests/contract"
