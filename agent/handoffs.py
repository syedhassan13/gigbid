"""Structured hand-offs between agents (C3). Anything a later step decides on is one
of these Pydantic objects - never free text."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    deliverables: list[str] = []
    requirements: list[str] = Field(default_factory=list, description="atomic skills/requirements, one per item")
    budget_type: Literal["fixed", "hourly"] = "fixed"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline: str | None = None
    screening_questions: list[str] = []
    hidden_needs: list[str] = Field(default_factory=list, description="needs implied but not stated")
    category: str = "other"
    vague: bool = False


class RiskFlag(BaseModel):
    code: Literal["off_platform", "free_work", "payment_scam", "injection", "unverified_payment", "no_history",
                  "low_rating", "low_budget", "vague_scope", "duplicate"]
    severity: float = Field(ge=0, le=1)
    evidence: str


class RiskReport(BaseModel):
    job_id: str
    client_score: float = Field(ge=0, le=1, description="client quality, 1 = excellent")
    risk_score: float = Field(ge=0, le=1, description="0 = safe, 1 = certainly scam/unsafe")
    is_scam: bool
    injection_detected: bool
    flags: list[RiskFlag] = []
    summary: str = ""


class RequirementMatch(BaseModel):
    requirement: str
    evidence_ids: list[str] = []
    best_score: float = 0.0
    covered: bool = False
    note: str = ""


class FitReport(BaseModel):
    job_id: str
    fit_score: float = Field(ge=0, le=1)
    matches: list[RequirementMatch] = []
    missing: list[str] = []
    reasons: list[str] = []


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str]
    expected_value_usd: float = 0.0
    auto: bool = False


class PriceQuote(BaseModel):
    amount: float
    unit: Literal["hourly", "fixed"]
    rationale: list[str]
    connects_cost: int | None = None
    connects_usd: float = 0.0
    worth_connects: bool = True
    market: dict = {}


class Citation(BaseModel):
    sentence: str
    evidence_ids: list[str]


class ProposalDraft(BaseModel):
    cover_letter: str
    screening_answers: list[str] = []
    citations: list[Citation] = []
    variant: str | None = None
    revision: int = 0


class Critique(BaseModel):
    passed: bool
    issues: list[str] = []
    grounding_ok: bool = True
    personalisation_ok: bool = True
    length_ok: bool = True
    score: float = Field(0.0, ge=0, le=10)


class ComplianceVerdict(BaseModel):
    allowed: bool
    blocked_reason: str | None = None
    fixes_applied: list[str] = []
    text: str


class Approval(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None
    user: str | None = None


class LiaisonIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    confidence: float = 0.5
    summary: str = ""
