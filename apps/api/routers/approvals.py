"""Approvals resume the interrupted LangGraph thread. Pending approvals live in the
checkpointer, so a page refresh (or an API restart) never loses one."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import current_user
from apps.api.dispatch import dispatch
from apps.api.schemas import Decision, Pending, RunStarted
from worker import tasks

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[Pending])
async def pending(user: dict = Depends(current_user)):
    rt = await tasks.runtime()
    with db.engine.connect() as c:
        rows = c.execute(select(db.runs).where(db.runs.c.user_id == user["id"], db.runs.c.status == "awaiting_approval")).fetchall()
    out = []
    for r in rows:
        st = await rt.state(r.kind, r.thread_id)
        if st["interrupts"]:
            p = st["interrupts"][0]
            out.append(Pending(thread_id=r.thread_id, kind=r.kind, title=(p.get("job") or {}).get("title") or p.get("thread_id"), payload=p))
    return out


class RegenIn(BaseModel):
    paragraph: str = Field(min_length=10, max_length=3000)
    instruction: str | None = Field(None, max_length=300)


@router.post("/{thread_id}/regenerate", response_model=dict)
async def regenerate(thread_id: str, body: RegenIn, user: dict = Depends(current_user)):
    """Rewrite ONE paragraph of a pending draft, grounded in the same evidence; the result goes back into the
    editor (it is only sent if the user then approves it as an edit, which re-runs Compliance)."""
    from agent import llm
    from rag.verify import apply_fixes, verify_claims
    if f":{user['id']}:" not in thread_id:
        raise HTTPException(403, "not your thread")
    st = (await (await tasks.runtime()).state("bid", thread_id))["values"]
    ev = "\n".join(f"- {v['claim']} [{', '.join(v['evidence_ids'])}]" for v in (st.get("verification") or {}).get("verdicts", []) if v["label"] == "supported")
    out = llm.complete_text("writer", llm.prompt("writer") + "\nRewrite ONLY the paragraph given; output the paragraph text only.",
                            f"PARAGRAPH:\n{body.paragraph}\n\nINSTRUCTION: {body.instruction or 'make it more specific to the client'}\n\nSUPPORTED CLAIMS YOU MAY USE:\n{ev}",
                            max_tokens=400)
    text = out or body.paragraph
    v = verify_claims(text, user["persona"], use_llm=False)
    return {"text": apply_fixes(text, v), "llm": bool(out), "removed_unsupported": sum(x.label == "unsupported" for x in v)}


@router.post("/{thread_id}", response_model=RunStarted)
async def decide(thread_id: str, body: Decision, user: dict = Depends(current_user)):
    if f":{user['id']}:" not in thread_id:
        raise HTTPException(403, "not your thread")
    if body.decision == "edit" and not (body.edited_text or "").strip():
        raise HTTPException(422, "edited_text required for edit")
    if body.decision == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    kind = "bid" if thread_id.startswith("bid:") else "conv"
    st = await (await tasks.runtime()).state(kind, thread_id)
    if not st["interrupts"]:
        raise HTTPException(409, "nothing awaiting approval on this thread")
    db.upsert_run(thread_id, status="resuming")
    await dispatch("job_resume_bid" if kind == "bid" else "job_resume_conv", user["id"], thread_id, body.model_dump())
    return RunStarted(thread_id=thread_id)
