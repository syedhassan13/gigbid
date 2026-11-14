"""Graph runs against a live GigSim (started by the fixture): scam skipped, proposal approved and
submitted exactly once even when the process "crashes" after approval and the run is resumed
from the durable checkpoint with a NEW runtime."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
PORT = 8199


@pytest.fixture(scope="module")
def gigsim(tmp_path_factory):
    db = tmp_path_factory.mktemp("gs") / "gigsim.db"
    env = {**os.environ, "GIGSIM_DB": str(db), "GIGSIM_ERROR_RATE": "0", "GIGSIM_RATE_LIMIT": "100000", "PYTHONPATH": str(ROOT)}
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "gigsim.app:app", "--port", str(PORT)], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    os.environ["GIGSIM_URL"] = f"http://127.0.0.1:{PORT}"
    os.environ["MARKETPLACE_RATE_PER_MIN"] = "100000"
    yield
    p.terminate()


def dev(pred):
    for l in (ROOT / "evals/datasets/dev_ai_ml.jsonl").read_text().splitlines():
        j = json.loads(l)
        if pred(j["gold"]):
            return j


@pytest.mark.asyncio
@pytest.mark.slow
async def test_scam_skipped_and_exactly_once_after_crash(gigsim, tmp_path):
    os.environ["GIGBID_HOME"] = str(tmp_path)
    from agent.marketplace_port import MarketplacePort
    from agent.runtime import Runtime
    port = MarketplacePort(token="mcp-dev-ai_ml", user="it")

    rt = await Runtime().start()
    scam = dev(lambda g: g["is_scam"])
    r = await rt.run("bid", "it-scam", {"job_id": scam["id"], "persona": "ai_ml", "user_id": "it"}, port, "ai_ml")
    assert r["status"] == "skipped"

    good = dev(lambda g: g["action"] == "bid" and g["job_type"] == "multi_req")
    r = await rt.run("bid", "it-bid", {"job_id": good["id"], "persona": "ai_ml", "user_id": "it", "force_bid": True}, port, "ai_ml")
    assert r["status"] == "awaiting_approval" and r["next"] == ["approval"]
    await rt.stop()  # "kill the API" while the proposal waits for approval

    rt2 = await Runtime().start()  # restart: pending approval survives in the checkpointer
    st = await rt2.state("bid", "it-bid")
    assert st["interrupts"] and st["interrupts"][0]["type"] == "proposal_approval"
    r = await rt2.resume("bid", "it-bid", {"decision": "approve"}, port, "ai_ml")
    assert r["status"] == "submitted"
    # crash AFTER submit but before the run is recorded: re-drive the submit node with the same key
    await rt2.bid.aupdate_state({"configurable": {"thread_id": "it-bid"}}, {"status": "approved"}, as_node="approval")
    await rt2.run("bid", "it-bid", None, port, "ai_ml")
    props = httpx.get(f"http://127.0.0.1:{PORT}/v1/proposals", headers={"Authorization": "Bearer gs-ai-ml-dev-token"}).json()["proposals"]
    assert sum(p["job_id"] == good["id"] for p in props) == 1  # submitted exactly once
    await rt2.stop()
