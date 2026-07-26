from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field

from .readable import describe

from .models import CaseStatus, ClaimType, EvidenceType, OfferStatus, OfferType, Party


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

    @computed_field
    @property
    def readable_facts(self) -> list[str]:
        """Plain English for the parties; parsed_facts stays available underneath
        for anyone auditing exactly what the parser established."""
        return describe(self.evidence_type, self.parsed_facts)

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


class OfferCreate(BaseModel):
    proposed_by: Party
    offer_type: OfferType
    # Required for partial_refund and rejected for every other type — the route
    # enforces that, because "half of nothing" is not a coherent settlement.
    amount: Optional[float] = Field(default=None, gt=0)
    message: Optional[str] = Field(default=None, max_length=1000)


class OfferRespond(BaseModel):
    # The responding party is derived from the offer, not supplied: letting the caller
    # name it would let one side accept its own proposal.
    action: str = Field(pattern="^(accept|decline)$")


class OfferOut(BaseModel):
    id: int
    proposed_by: Party
    offer_type: OfferType
    amount: Optional[float] = None
    message: Optional[str] = None
    status: OfferStatus
    created_at: datetime
    responded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ForecastOut(BaseModel):
    """What the scorecard would rule if asked right now, without recording anything.

    Shown identically to both parties. A negotiation where only one side can estimate
    the outcome is not a negotiation, it is a squeeze."""
    winner: Party
    card_member_score: float
    merchant_score: float
    confidence: float
    counterfactual: str
    signals: List["SignalPreviewOut"] = []


class SignalPreviewOut(BaseModel):
    signal_name: str
    detail: str
    weight: float
    favors: Optional[Party] = None


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
    offers: list[OfferOut] = []

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
