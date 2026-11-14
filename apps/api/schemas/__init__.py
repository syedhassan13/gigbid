"""Request/response models - the typed API contract (TypeScript client is generated from these)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class TokenOut(BaseModel):
    token: str
    user: "UserOut"


class UserOut(BaseModel):
    id: str
    email: str
    persona: str | None
    settings: dict[str, Any] = {}


class Onboarding(BaseModel):
    persona: Literal["ai_ml", "fullstack", "data_analyst"]
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"
    rate_floor: float = Field(gt=0, le=1000)
    target_rate: float = Field(gt=0, le=1000)
    weekly_connects_budget: int = Field(ge=0, le=1000, default=120)
    saved_searches: list[str] = []
    categories: list[str] = []


class SettingsIn(BaseModel):
    autonomy: Literal["suggest", "auto_skip_low_fit"] | None = None
    rate_floor: float | None = Field(None, gt=0, le=1000)
    target_rate: float | None = Field(None, gt=0, le=1000)
    weekly_connects_budget: int | None = Field(None, ge=0, le=1000)
    saved_searches: list[str] | None = None


class InboxItem(BaseModel):
    job_id: str
    thread_id: str | None = None
    title: str | None = None
    status: str | None = None
    action: str | None = None
    fit: float | None = None
    risk: float | None = None
    is_scam: int | None = None
    price: float | None = None
    price_unit: str | None = None
    connects: int | None = None
    category: str | None = None
    posted_at: str | None = None
    pipeline: str | None = None
    variant: str | None = None
    proposal_id: str | None = None
    reject_reason: str | None = None


class JobDetail(BaseModel):
    job: dict[str, Any]
    client: dict[str, Any] = {}
    status: str | None = None
    analyses: dict[str, Any] = {}
    decision: dict[str, Any] = {}
    price: dict[str, Any] = {}
    draft: dict[str, Any] = {}
    verification: dict[str, Any] = {}
    critiques: list[dict[str, Any]] = []
    compliance: dict[str, Any] = {}
    interrupt: dict[str, Any] | None = None
    thread_id: str | None = None
    error: str | None = None


class Decision(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(None, max_length=6000)
    reason: str | None = Field(None, max_length=500)


class RunStarted(BaseModel):
    thread_id: str
    queued: bool = True


class Pending(BaseModel):
    thread_id: str
    kind: Literal["bid", "conv"]
    title: str | None = None
    payload: dict[str, Any]


class Health(BaseModel):
    api: str = "ok"
    marketplace: Literal["up", "down"]
    mcp: dict[str, str]
    llm_profile: str
    llm_available: bool
    worker: str


TokenOut.model_rebuild()
