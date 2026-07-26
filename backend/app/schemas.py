from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from .models import CaseStatus, ClaimType, EvidenceType, Party


class CaseCreate(BaseModel):
    transaction_id: str
    card_member_name: str
    card_member_address: str
    merchant_name: str
    amount: float
    claim_type: ClaimType
    claim_text: str


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
    created_at: datetime

    class Config:
        from_attributes = True


class SignalOut(BaseModel):
    signal_name: str
    detail: str
    weight: float
    favors: Optional[Party] = None

    class Config:
        from_attributes = True


class VerdictOut(BaseModel):
    winner: Party
    card_member_score: float
    merchant_score: float
    confidence: float
    explanation: str
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
    created_at: datetime

    class Config:
        from_attributes = True
