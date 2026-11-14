"""Multi-user auth: PBKDF2 password hashes, HS256 JWT sessions, user dependency."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import insert, select

from apps.api import db

SECRET = os.getenv("JWT_SECRET") or secrets.token_hex(32)
_bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 240_000)
    return f"pbkdf2${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(s), 240_000)
        return hmac.compare_digest(dk, base64.b64decode(h))
    except ValueError:
        return False


def make_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "exp": int(time.time()) + 7 * 86400}, SECRET, algorithm="HS256")


def create_user(email: str, password: str, persona: str | None = None, settings: dict | None = None) -> str:
    uid = "u-" + uuid.uuid4().hex[:12]
    with db.engine.begin() as c:
        c.execute(insert(db.users).values(id=uid, email=email.lower(), password_hash=hash_password(password), persona=persona,
                                          settings=settings or {}, created=time.time()))
    return uid


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if not cred:
        raise HTTPException(401, "not signed in")
    try:
        uid = jwt.decode(cred.credentials, SECRET, algorithms=["HS256"])["sub"]
    except JWTError:
        raise HTTPException(401, "invalid session")
    with db.engine.connect() as c:
        r = c.execute(select(db.users).where(db.users.c.id == uid)).first()
    if not r:
        raise HTTPException(401, "unknown user")
    return dict(r._mapping)


def user_from_token(token: str) -> dict | None:
    try:
        uid = jwt.decode(token, SECRET, algorithms=["HS256"])["sub"]
    except JWTError:
        return None
    with db.engine.connect() as c:
        r = c.execute(select(db.users).where(db.users.c.id == uid)).first()
    return dict(r._mapping) if r else None
