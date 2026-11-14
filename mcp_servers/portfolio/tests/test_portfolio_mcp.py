"""Portfolio server through an in-memory MCP client (real JSON-RPC, no network)."""
import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.portfolio.server import mcp


@pytest.mark.asyncio
async def test_lists_tools_resources_prompts():
    async with connect(mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert {"search_evidence", "get_case_study", "list_skills"} <= set(tools)
        assert all(t.annotations.readOnlyHint for t in tools.values())
        assert tools["search_evidence"].outputSchema is not None
        uris = {r.uriTemplate for r in (await s.list_resource_templates()).resourceTemplates}
        assert {"portfolio://case/{id}", "portfolio://proposal/{id}"} <= uris
        assert "answer_screening_question" in {p.name for p in (await s.list_prompts()).prompts}


@pytest.mark.asyncio
async def test_get_case_study_and_resource():
    async with connect(mcp._mcp_server) as s:
        r = await s.call_tool("get_case_study", {"id": "case:ai_ml-rag-chatbot-00"})
        assert r.structuredContent["type"] == "case_study" and r.structuredContent["related"]
        res = await s.read_resource("portfolio://case/ai_ml-rag-chatbot-00")
        assert "problem" in res.contents[0].text.lower()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_search_evidence_finds_library_only_in_code():
    async with connect(mcp._mcp_server) as s:
        r = await s.call_tool("search_evidence", {"requirement": "celery background jobs", "k": 3})
        ids = [i["id"] for i in r.structuredContent["items"]]
        assert any("churn-deploy" in i for i in ids)
