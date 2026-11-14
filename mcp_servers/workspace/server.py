"""GigBid Workspace MCP server: free calendar slots, tentative interview holds and
email drafts. Backed by a local mock calendar (SQLite) - the agent sees MCP tools
only, so swapping in Google Calendar/Gmail APIs changes only this file.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.settings import HOME
from mcp_servers.common import audit, request_headers

mcp = FastMCP("gigbid-workspace", host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("WORKSPACE_MCP_PORT", "8203")),
              stateless_http=True, json_response=True)
WORK_HOURS = (9, 17)


def _db():
    p = HOME / "var" / "workspace.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, user TEXT, start TEXT, end TEXT, title TEXT, status TEXT, idem TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, user TEXT, to_label TEXT, subject TEXT, body TEXT, created TEXT, idem TEXT UNIQUE)")
    return c


def _user(ctx) -> str:
    return request_headers(ctx).get("x-gigbid-user", "") or os.getenv("WORKSPACE_DEFAULT_USER", "demo")


class Slot(BaseModel):
    start: str
    end: str


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def free_slots(from_date: Annotated[str, Field(description="ISO date, e.g. 2026-11-16")],
               days: Annotated[int, Field(ge=1, le=14)] = 5, duration_minutes: Annotated[int, Field(ge=15, le=180)] = 30,
               max_slots: Annotated[int, Field(ge=1, le=10)] = 3, ctx: Context | None = None) -> list[Slot]:
    """Free interview slots on working days (09:00-17:00), skipping existing events/holds."""
    user = _user(ctx)
    c = _db()
    busy = [(datetime.fromisoformat(s), datetime.fromisoformat(e)) for s, e in
            c.execute("SELECT start, end FROM events WHERE user=? AND status!='cancelled'", (user,)).fetchall()]
    out = []
    day = datetime.fromisoformat(from_date[:10])
    for d in range(days):
        cur = day + timedelta(days=d)
        if cur.weekday() >= 5:
            continue
        t = cur.replace(hour=WORK_HOURS[0] + (d % 3) * 2)  # spread suggestions across the day
        while t.hour < WORK_HOURS[1] and len(out) < max_slots:
            end = t + timedelta(minutes=duration_minutes)
            if not any(s < end and t < e for s, e in busy):
                out.append(Slot(start=t.isoformat(timespec="minutes"), end=end.isoformat(timespec="minutes")))
                break
            t += timedelta(minutes=30)
        if len(out) >= max_slots:
            break
    audit("workspace", user, "free_slots", {"from_date": from_date, "days": days}, [s.model_dump() for s in out])
    return out


class Hold(BaseModel):
    id: str
    start: str
    end: str
    title: str
    status: str


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def create_tentative_hold(start: str, duration_minutes: Annotated[int, Field(ge=15, le=180)],
                          title: Annotated[str, Field(max_length=120)], idempotency_key: Annotated[str, Field(min_length=8)],
                          ctx: Context | None = None) -> Hold:
    """Place a TENTATIVE calendar hold for a proposed interview slot (no invite is sent)."""
    user = _user(ctx)
    c = _db()
    r = c.execute("SELECT id, start, end, title, status FROM events WHERE idem=?", (idempotency_key,)).fetchone()
    if r:
        return Hold(id=r[0], start=r[1], end=r[2], title=r[3], status=r[4])
    s = datetime.fromisoformat(start)
    e = s + timedelta(minutes=duration_minutes)
    hid = "h-" + uuid.uuid4().hex[:10]
    c.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (hid, user, s.isoformat(), e.isoformat(), title, "tentative", idempotency_key))
    c.commit()
    audit("workspace", user, "create_tentative_hold", {"start": start, "title": title}, hid)
    return Hold(id=hid, start=s.isoformat(), end=e.isoformat(), title=title, status="tentative")


class EmailDraft(BaseModel):
    id: str
    to_label: str
    subject: str
    body: str


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def create_email_draft(to_label: Annotated[str, Field(max_length=120, description="Who it is for (no address needed)")],
                       subject: Annotated[str, Field(max_length=200)], body: Annotated[str, Field(max_length=5000)],
                       idempotency_key: Annotated[str, Field(min_length=8)], ctx: Context | None = None) -> EmailDraft:
    """Save an email DRAFT (never sends)."""
    user = _user(ctx)
    c = _db()
    r = c.execute("SELECT id, to_label, subject, body FROM drafts WHERE idem=?", (idempotency_key,)).fetchone()
    if r:
        return EmailDraft(id=r[0], to_label=r[1], subject=r[2], body=r[3])
    did = "e-" + uuid.uuid4().hex[:10]
    c.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?)", (did, user, to_label, subject, body, datetime.now().isoformat(), idempotency_key))
    c.commit()
    audit("workspace", user, "create_email_draft", {"to_label": to_label, "subject": subject}, did)
    return EmailDraft(id=did, to_label=to_label, subject=subject, body=body)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
