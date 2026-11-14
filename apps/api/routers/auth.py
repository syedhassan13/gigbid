from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update

from apps.api import db
from apps.api.auth import oauth_upwork
from apps.api.auth.security import create_user, current_user, make_token, verify_password
from apps.api.schemas import Credentials, Onboarding, TokenOut, UserOut
from mcp_servers.common import write_account

router = APIRouter(prefix="/auth", tags=["auth"])

GIGSIM_TOKENS = {"ai_ml": os.getenv("GIGSIM_TOKEN_AI_ML", "gs-ai-ml-dev-token"),
                 "fullstack": os.getenv("GIGSIM_TOKEN_FULLSTACK", "gs-fullstack-dev-token"),
                 "data_analyst": os.getenv("GIGSIM_TOKEN_DATA_ANALYST", "gs-data-analyst-dev-token")}


def _out(u: dict) -> UserOut:
    s = {k: v for k, v in (u.get("settings") or {}).items() if k != "marketplace_token"}
    return UserOut(id=u["id"], email=u["email"], persona=u.get("persona"), settings=s)


@router.post("/register", response_model=TokenOut)
def register(body: Credentials):
    with db.engine.connect() as c:
        if c.execute(select(db.users.c.id).where(db.users.c.email == body.email.lower())).first():
            raise HTTPException(409, "email already registered")
    uid = create_user(body.email, body.password)
    return TokenOut(token=make_token(uid), user=UserOut(id=uid, email=body.email.lower(), persona=None))


@router.post("/login", response_model=TokenOut)
def login(body: Credentials):
    with db.engine.connect() as c:
        r = c.execute(select(db.users).where(db.users.c.email == body.email.lower())).first()
    if not r or not verify_password(body.password, r.password_hash):
        raise HTTPException(401, "wrong email or password")
    return TokenOut(token=make_token(r.id), user=_out(dict(r._mapping)))


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(current_user)):
    return _out(user)


@router.post("/onboarding", response_model=UserOut)
def onboarding(body: Onboarding, user: dict = Depends(current_user)):
    s = dict(user.get("settings") or {})
    token = s.get("marketplace_token") or "mcp-" + secrets.token_urlsafe(24)
    account = {"user": user["id"], "adapter": body.marketplace, "gigsim_token": GIGSIM_TOKENS[body.persona]}
    write_account(token, account)  # Marketplace MCP bearer token -> this user's marketplace account
    s.update({"marketplace": body.marketplace, "marketplace_token": token, "rate_floor": body.rate_floor, "target_rate": body.target_rate,
              "weekly_connects_budget": body.weekly_connects_budget, "saved_searches": body.saved_searches,
              "categories": body.categories, "autonomy": s.get("autonomy", "suggest")})
    with db.engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.id == user["id"]).values(persona=body.persona, settings=s))
    return _out({**user, "persona": body.persona, "settings": s})


@router.get("/upwork/start")
def upwork_start(request: Request, user: dict = Depends(current_user)):
    try:
        url = oauth_upwork.start(user["id"], str(request.url_for("upwork_callback")))
    except Exception as e:
        raise HTTPException(502, f"Upwork OAuth discovery failed: {e}")
    return {"authorize_url": url}


@router.get("/upwork/callback", name="upwork_callback")
def upwork_callback(state: str, code: str):
    try:
        oauth_upwork.callback(state, code)
    except PermissionError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse(os.getenv("WEB_URL", "/") + "/settings?upwork=connected")
