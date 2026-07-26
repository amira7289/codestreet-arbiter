from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .models import CaseStatus, ClaimType, EvidenceType, Party


class CaseCreate(BaseModel):
    # A dispute over a negative amount, or one filed by an empty-string party, is not a
    # dispute. Without these the API accepted both and rendered "$-500.00" in the UI.
    transaction_id: str = Field(min_length=1, max_length=64)
    card_member_name: str = Field(min_length=1, max_length=200)
    card_member_address: str = Field(min_length=1, max_length=300)
    merchant_name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0)
    claim_type: ClaimType
    claim_text: str = Field(min_length=1, max_length=2000)


class EvidenceCreate(BaseModel):
    submitted_by: Party
    evidence_type: EvidenceType
    raw_content: str


class EvidenceOut(BaseModel):
    id: int
    submitted_by: Party
    evidence_type: EvidenceType
    raw_content: str
    parsed_facts: Optional[dict] = None
    source: str = "manual_upload"
    auto_gathered: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class GatherEntryOut(BaseModel):
    source: str
    status: str
    latency_ms: int
    summary: str
    evidence_id: Optional[int] = None
    # Only carried on the live gather response; GatherLog rows point at the evidence
    # row instead of duplicating its type.
    evidence_type: Optional[EvidenceType] = None

    class Config:
        from_attributes = True


class GatherRunOut(BaseModel):
    case_id: int
    elapsed_ms: int
    evidence_created: int
    entries: list[GatherEntryOut] = []


class GatherQueuedOut(BaseModel):
    """Returned with 202 from the async gather. The run itself reports through
    GET /cases/{id}/gather-log, one row at a time as each source answers."""

    case_id: int
    sources_queued: int


class SignalOut(BaseModel):
    # Auto-gather makes repeated signal names routine — two carrier records can both
    # raise delivery_confirmation_thirdparty — so the name is not a usable React key.
    id: int
    signal_name: str
    detail: str
    weight: float
    favors: Optional[Party] = None
    # Lets the UI distinguish evidence that was weighed and found against a party
    # from evidence no rule in the scorecard reads at all.
    evidence_ids: List[int] = []

    class Config:
        from_attributes = True


class VerdictOut(BaseModel):
    winner: Party
    card_member_score: float
    merchant_score: float
    confidence: float
    explanation: str
    reason_code: Optional[str] = None
    reason_code_label: Optional[str] = None
    counterfactual: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CaseOut(BaseModel):
    id: int
    transaction_id: str
    card_member_name: str
    card_member_address: str
    merchant_name: str
    amount: float
    claim_type: ClaimType
    claim_text: str
    status: CaseStatus
    created_at: datetime
    evidence: list[EvidenceOut] = []
    signals: list[SignalOut] = []
    verdict: Optional[VerdictOut] = None
    gather_log: list[GatherEntryOut] = []

    class Config:
        from_attributes = True


class VerdictSummaryOut(BaseModel):
    """Just enough of a verdict for a queue row. The full VerdictOut carries the
    explanation and counterfactual, which no list view needs."""
    winner: Party
    confidence: float
    reason_code: Optional[str] = None

    class Config:
        from_attributes = True


class CaseSummaryOut(BaseModel):
    id: int
    transaction_id: str
    card_member_name: str
    merchant_name: str
    amount: float
    claim_type: ClaimType
    status: CaseStatus
    verdict: Optional[VerdictSummaryOut] = None
    created_at: datetime

    class Config:
        from_attributes = True
