from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select, update

from agent.settings import HOME, config
from apps.api import db
from apps.api.auth.security import current_user
from apps.api.schemas import SettingsIn
from rag.pipeline import invalidate
from worker import tasks

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=dict)
def get_settings(user: dict = Depends(current_user)):
    s = {k: v for k, v in (user.get("settings") or {}).items() if k != "marketplace_token"}
    s.setdefault("saved_searches", config()["scout"]["saved_searches"].get(user.get("persona") or "", []))
    with db.engine.connect() as c:
        upwork = c.execute(select(db.oauth_tokens.c.updated).where(db.oauth_tokens.c.user_id == user["id"], db.oauth_tokens.c.provider == "upwork")).first()
    return {**s, "persona": user.get("persona"), "connected": {"gigsim": bool(user.get("persona")), "upwork": bool(upwork)},
            "llm_profile": config()["profile"], "rag_variant": config()["rag"]["variant"]}


@router.put("", response_model=dict)
def put_settings(body: SettingsIn, user: dict = Depends(current_user)):
    s = dict(user.get("settings") or {})
    s.update({k: v for k, v in body.model_dump().items() if v is not None})
    with db.engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.id == user["id"]).values(settings=s))
    return {k: v for k, v in s.items() if k != "marketplace_token"}


@router.get("/memory", response_model=dict)
async def memory(user: dict = Depends(current_user)):
    store = (await tasks.runtime()).store
    ns = lambda n: [{"key": i.key, **i.value} for i in store.search((n, user["id"]), limit=100)]  # noqa: E731
    return {"style": ns("style"), "style_candidates": ns("style_candidates"), "outcome": ns("outcome")}


@router.delete("/memory/{namespace}/{key}", response_model=dict)
async def delete_memory(namespace: str, key: str, user: dict = Depends(current_user)):
    if namespace not in ("style", "style_candidates", "outcome"):
        raise HTTPException(400, "unknown namespace")
    store = (await tasks.runtime()).store
    store.delete((namespace, user["id"]), key)
    return {"deleted": key}


@router.post("/portfolio", response_model=dict)
async def upload_portfolio(file: UploadFile, user: dict = Depends(current_user)):
    """Add work (Markdown case study or PDF CV/case study). Incremental re-index: only new chunks are embedded."""
    name = Path(file.filename or "upload.md").name
    if not name.lower().endswith((".md", ".pdf", ".txt")):
        raise HTTPException(415, "upload .md, .txt or .pdf")
    d = HOME / "var" / "uploads" / user["persona"]
    d.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "max 5 MB")
    if name.endswith(".txt"):
        name = name[:-4] + ".md"
    if name.endswith(".md") and not data.startswith(b"---"):
        data = (f'---\nid: "upload:{user["id"]}:{Path(name).stem}"\ntype: "user_upload"\npersona: "{user["persona"]}"\nsynthetic: false\n---\n').encode() + data
    (d / name).write_bytes(data)
    invalidate(user["persona"])
    return {"saved": name, "reindexed": True}
