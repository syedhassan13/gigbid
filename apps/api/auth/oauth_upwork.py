"""OAuth 2.1 (authorization code + PKCE, dynamic client registration) against the official
Upwork MCP server, following the MCP authorization spec:
  1. GET {mcp}/.well-known/oauth-protected-resource  -> authorization server
  2. GET {as}/.well-known/oauth-authorization-server -> endpoints
  3. POST registration_endpoint (DCR) -> client_id
  4. redirect user to authorization_endpoint with PKCE S256
  5. callback: exchange code -> tokens, stored ENCRYPTED per user (auth/tokens.py)
Live mode is never graded; this path is exercised only with a real Upwork account.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode, urlparse

import httpx

from apps.api.auth.tokens import save_token
from mcp_servers.marketplace.adapters.upwork_live import UPWORK_MCP_URL

_pending: dict[str, dict] = {}  # state -> {verifier, user_id, client_id, token_endpoint}


def _discover() -> dict:
    u = urlparse(UPWORK_MCP_URL)
    base = f"{u.scheme}://{u.netloc}"
    prm = httpx.get(f"{base}/.well-known/oauth-protected-resource", timeout=10).json()
    as_url = prm["authorization_servers"][0].rstrip("/")
    return httpx.get(f"{as_url}/.well-known/oauth-authorization-server", timeout=10).json()


def start(user_id: str, redirect_uri: str) -> str:
    meta = _discover()
    client_id = os.getenv("UPWORK_CLIENT_ID")
    if not client_id and meta.get("registration_endpoint"):
        reg = httpx.post(meta["registration_endpoint"], json={"client_name": "GigBid", "redirect_uris": [redirect_uri],
                                                              "grant_types": ["authorization_code", "refresh_token"],
                                                              "token_endpoint_auth_method": "none"}, timeout=10).json()
        client_id = reg["client_id"]
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    _pending[state] = {"verifier": verifier, "user_id": user_id, "client_id": client_id, "token_endpoint": meta["token_endpoint"],
                       "redirect_uri": redirect_uri}
    return meta["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "resource": UPWORK_MCP_URL})


def callback(state: str, code: str) -> str:
    p = _pending.pop(state, None)
    if not p:
        raise PermissionError("invalid OAuth state")
    tok = httpx.post(p["token_endpoint"], data={"grant_type": "authorization_code", "code": code, "redirect_uri": p["redirect_uri"],
                                                "client_id": p["client_id"], "code_verifier": p["verifier"], "resource": UPWORK_MCP_URL},
                     timeout=10).json()
    if "access_token" not in tok:
        raise PermissionError("token exchange failed")
    save_token(p["user_id"], "upwork", tok)
    return p["user_id"]
