"""Encrypted per-user OAuth token store (Fernet). Tokens are never logged."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time

from cryptography.fernet import Fernet
from sqlalchemy import delete, insert, select

from apps.api import db


def _fernet() -> Fernet:
    key = os.getenv("TOKEN_ENC_KEY")
    if not key:  # derive from JWT secret so dev works; production MUST set TOKEN_ENC_KEY
        key = base64.urlsafe_b64encode(hashlib.sha256((os.getenv("JWT_SECRET", "dev")).encode()).digest()).decode()
    return Fernet(key)


def save_token(user_id: str, provider: str, token: dict) -> None:
    enc = _fernet().encrypt(json.dumps(token).encode()).decode()
    with db.engine.begin() as c:
        c.execute(delete(db.oauth_tokens).where(db.oauth_tokens.c.user_id == user_id, db.oauth_tokens.c.provider == provider))
        c.execute(insert(db.oauth_tokens).values(user_id=user_id, provider=provider, enc_token=enc, updated=time.time()))


def load_token(user_id: str, provider: str) -> dict | None:
    with db.engine.connect() as c:
        r = c.execute(select(db.oauth_tokens.c.enc_token).where(db.oauth_tokens.c.user_id == user_id,
                                                                  db.oauth_tokens.c.provider == provider)).first()
    return json.loads(_fernet().decrypt(r[0].encode())) if r else None


def get_upwork_access_token(user_id: str) -> str:
    t = load_token(user_id, "upwork")
    if not t:
        raise PermissionError("Upwork account not connected")
    return t["access_token"]
