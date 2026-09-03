"""The output contract. The report is validated against these models before it is written, so a
consumer of the API gets a stable, auditable shape: who the person is and how sure we are, every
finding with a source and how it was found, the inferences we drew, what we could not confirm,
where sources disagree, findings we excluded as the wrong person, and the evidence graph."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["resolved", "ambiguous", "unresolved"]
Category = Literal["identity_contact", "professional_history", "education", "online_presence",
                   "achievements", "personal", "connections", "sensitive"]


class Source(BaseModel):
    url: str | None = None
    excerpt: str | None = None


class Finding(BaseModel):
    category: str | None = None
    field: str
    value: str
    confidence: float = 0.0
    sensitive: bool = False
    source_url: str | None = None
    method: str | None = None
    candidate_id: str | None = None


class Synthesis(BaseModel):
    claim: str
    based_on: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class RejectedCandidate(BaseModel):
    id: str | None = None
    label: str | None = None
    score: float = 0.0
    reason: str | None = None


class Identity(BaseModel):
    status: Status = "unresolved"
    name: str | None = None
    summary: str | None = None
    score: float = 0.0
    matched_markers: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    candidates_considered: int = 0
    same_person_ids: list[str] = Field(default_factory=list)
    best_candidate: dict[str, Any] | None = None
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    judge: dict[str, Any] | None = None


class RunStats(BaseModel):
    duration_s: float = 0.0
    stop_reason: str | None = None
    error: str | None = None
    model: str | None = None
    llm_calls: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    transient_errors: int = 0
    tokens: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float = 0.0
    llm_latency_ms: int = 0
    tool_latency_ms: int = 0
    trace_path: str | None = None

    model_config = {"extra": "allow"}


class Report(BaseModel):
    target: str
    run_id: str
    anchor: dict[str, Any]
    identity: Identity
    findings: list[Finding] = Field(default_factory=list)
    synthesis: list[Synthesis] = Field(default_factory=list)
    excluded_findings: list[dict[str, Any]] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    graph: dict[str, Any] = Field(default_factory=dict)
    answer_text: str | None = None
    run: RunStats

    model_config = {"extra": "allow"}


def validate_report(report: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate without mutating. Returns (ok, error). Used to flag a malformed report, not block it."""
    try:
        Report(**report)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:400]
