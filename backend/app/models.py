import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class CaseStatus(str, enum.Enum):
    filed = "filed"
    evidence_gathering = "evidence_gathering"
    negotiating = "negotiating"
    scored = "scored"
    resolved = "resolved"
    # Agreed between the parties. Distinct from `resolved`, which means the scorecard
    # adjudicated: a settled case has no verdict and never needed one.
    settled = "settled"


class ClaimType(str, enum.Enum):
    item_not_received = "item_not_received"
    not_as_described = "not_as_described"
    duplicate_charge = "duplicate_charge"
    refund_not_processed = "refund_not_processed"


class Party(str, enum.Enum):
    card_member = "card_member"
    merchant = "merchant"


class OfferType(str, enum.Enum):
    full_refund = "full_refund"
    partial_refund = "partial_refund"
    replacement = "replacement"
    withdraw_dispute = "withdraw_dispute"


class OfferStatus(str, enum.Enum):
    open = "open"
    accepted = "accepted"
    declined = "declined"
    # Replaced by a later offer from either side. Kept rather than deleted so the
    # negotiation reads as a thread both parties can audit afterwards.
    superseded = "superseded"


class EvidenceType(str, enum.Enum):
    tracking_data = "tracking_data"
    receipt = "receipt"
    policy_text = "policy_text"
    email = "email"
    chat_log = "chat_log"
    photo = "photo"
    processor_ledger = "processor_ledger"


class DisputeCase(Base):
    __tablename__ = "dispute_cases"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, nullable=False)
    card_member_name = Column(String, nullable=False)
    card_member_address = Column(String, nullable=False)
    merchant_name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    claim_type = Column(Enum(ClaimType), nullable=False)
    claim_text = Column(Text, nullable=False)
    status = Column(Enum(CaseStatus), default=CaseStatus.filed, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    evidence = relationship("Evidence", back_populates="case", cascade="all, delete-orphan")
    signals = relationship("ScoreSignal", back_populates="case", cascade="all, delete-orphan")
    verdict = relationship("Verdict", back_populates="case", uselist=False, cascade="all, delete-orphan")
    gather_log = relationship("GatherLog", back_populates="case", cascade="all, delete-orphan")
    offers = relationship("SettlementOffer", back_populates="case", cascade="all, delete-orphan",
                          order_by="SettlementOffer.id")


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("dispute_cases.id"), nullable=False)
    submitted_by = Column(Enum(Party), nullable=False)
    evidence_type = Column(Enum(EvidenceType), nullable=False)
    raw_content = Column(Text, nullable=False)
    parsed_facts = Column(JSON, nullable=True)
    # Which system produced this — a connector name, or "manual_upload" when a party
    # pasted it in. auto_gathered is denormalised from it so the UI can badge items
    # without knowing the connector inventory.
    source = Column(String, nullable=False, default="manual_upload")
    auto_gathered = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("DisputeCase", back_populates="evidence")


class GatherLog(Base):
    """One row per source queried, hit or miss. Misses are the point: an adverse
    inference against a party is only defensible when the record shows the system
    asked their systems and got nothing back."""

    __tablename__ = "gather_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("dispute_cases.id"), nullable=False)
    source = Column(String, nullable=False)
    status = Column(String, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    summary = Column(String, nullable=False)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("DisputeCase", back_populates="gather_log")


class ScoreSignal(Base):
    __tablename__ = "score_signals"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("dispute_cases.id"), nullable=False)
    signal_name = Column(String, nullable=False)
    detail = Column(String, nullable=False)
    weight = Column(Float, nullable=False)
    favors = Column(Enum(Party), nullable=True)
    # Every document this signal was read from. A list because corroborating filings
    # collapse into one signal and all of them were still examined; empty for
    # procedural and disclosed-policy signals, which arise from the shape of the case.
    evidence_ids = Column(JSON, nullable=False, default=list)

    case = relationship("DisputeCase", back_populates="signals")


class Verdict(Base):
    __tablename__ = "verdicts"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("dispute_cases.id"), nullable=False)
    winner = Column(Enum(Party), nullable=False)
    card_member_score = Column(Float, nullable=False)
    merchant_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    explanation = Column(Text, nullable=False)
    reason_code = Column(String, nullable=True)
    reason_code_label = Column(String, nullable=True)
    # Deterministic "what would have had to be different" statement, derived by
    # arithmetic over the scorecard rather than generated, so it cannot drift.
    counterfactual = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("DisputeCase", back_populates="verdict")


class SettlementOffer(Base):
    """One move in a negotiation.

    Adjudication is the fallback, not the first step. Most disputes have a number both
    sides would accept, and finding it costs nothing compared with arbitrating — so the
    parties get to propose terms before the scorecard is asked to rule at all.
    """

    __tablename__ = "settlement_offers"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("dispute_cases.id"), nullable=False)
    proposed_by = Column(Enum(Party), nullable=False)
    offer_type = Column(Enum(OfferType), nullable=False)
    # Only meaningful for partial_refund; the other types imply their own amount.
    amount = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(Enum(OfferStatus), default=OfferStatus.open, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    responded_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("DisputeCase", back_populates="offers")
