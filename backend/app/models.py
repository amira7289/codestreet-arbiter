import enum

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class CaseStatus(str, enum.Enum):
    filed = "filed"
    evidence_gathering = "evidence_gathering"
    scored = "scored"
    resolved = "resolved"


class ClaimType(str, enum.Enum):
    item_not_received = "item_not_received"
    not_as_described = "not_as_described"
    duplicate_charge = "duplicate_charge"
    refund_not_processed = "refund_not_processed"


class Party(str, enum.Enum):
    card_member = "card_member"
    merchant = "merchant"


class EvidenceType(str, enum.Enum):
    tracking_data = "tracking_data"
    receipt = "receipt"
    policy_text = "policy_text"
    email = "email"
    chat_log = "chat_log"
    photo = "photo"


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


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("dispute_cases.id"), nullable=False)
    submitted_by = Column(Enum(Party), nullable=False)
    evidence_type = Column(Enum(EvidenceType), nullable=False)
    raw_content = Column(Text, nullable=False)
    parsed_facts = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("DisputeCase", back_populates="evidence")


class ScoreSignal(Base):
    __tablename__ = "score_signals"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("dispute_cases.id"), nullable=False)
    signal_name = Column(String, nullable=False)
    detail = Column(String, nullable=False)
    weight = Column(Float, nullable=False)
    favors = Column(Enum(Party), nullable=True)

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
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("DisputeCase", back_populates="verdict")
