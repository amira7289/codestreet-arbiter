from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import llm, models, schemas
from ..database import get_db
from ..scoring import score_case

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=schemas.CaseOut)
def create_case(payload: schemas.CaseCreate, db: Session = Depends(get_db)):
    case = models.DisputeCase(**payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=list[schemas.CaseSummaryOut])
def list_cases(db: Session = Depends(get_db)):
    return db.query(models.DisputeCase).order_by(models.DisputeCase.created_at.desc()).all()


@router.get("/{case_id}", response_model=schemas.CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = db.get(models.DisputeCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


@router.post("/{case_id}/evidence", response_model=schemas.EvidenceOut)
def submit_evidence(case_id: int, payload: schemas.EvidenceCreate, db: Session = Depends(get_db)):
    case = db.get(models.DisputeCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    parsed_facts = llm.parse_evidence(payload.evidence_type.value, payload.raw_content)
    evidence = models.Evidence(case_id=case_id, parsed_facts=parsed_facts, **payload.model_dump())
    db.add(evidence)

    if case.status == models.CaseStatus.filed:
        case.status = models.CaseStatus.evidence_gathering

    db.commit()
    db.refresh(evidence)
    return evidence


@router.post("/{case_id}/resolve", response_model=schemas.VerdictOut)
def resolve_case(case_id: int, db: Session = Depends(get_db)):
    case = db.get(models.DisputeCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    signals, winner, card_member_score, merchant_score, confidence = score_case(case, case.evidence)

    db.query(models.ScoreSignal).filter(models.ScoreSignal.case_id == case_id).delete()
    for s in signals:
        db.add(models.ScoreSignal(
            case_id=case_id, signal_name=s.signal_name, detail=s.detail, weight=s.weight, favors=s.favors,
        ))

    winning_signals = [s for s in signals if s.favors == winner]
    explanation = llm.generate_explanation(case, winning_signals, confidence)

    existing = db.query(models.Verdict).filter(models.Verdict.case_id == case_id).first()
    if existing:
        db.delete(existing)
        db.flush()

    verdict = models.Verdict(
        case_id=case_id,
        winner=winner,
        card_member_score=card_member_score,
        merchant_score=merchant_score,
        confidence=confidence,
        explanation=explanation,
    )
    db.add(verdict)
    case.status = models.CaseStatus.resolved
    db.commit()
    db.refresh(verdict)
    return verdict
