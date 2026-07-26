import random
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import connectors, llm, models, reason_codes, schemas
from ..database import SessionLocal, get_db
from ..scoring import counterfactual_statement, score_case

router = APIRouter(prefix="/cases", tags=["cases"])

# connectors.gather() deliberately never sleeps, so seeding and the eval harness stay
# instant. The pacing belongs here instead: the async run is the only path where a
# human watches sources land, and it is the only place the delay is worth anything.
GATHER_PACING_S = (0.3, 0.8)


@router.post("", response_model=schemas.CaseOut)
def create_case(payload: schemas.CaseCreate, db: Session = Depends(get_db)):
    case = models.DisputeCase(**payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=list[schemas.CaseSummaryOut])
def list_cases(db: Session = Depends(get_db)):
    # created_at is second-granular in SQLite and the whole corpus seeds inside one
    # second, so without the id tiebreaker the list reshuffles between refreshes.
    return (db.query(models.DisputeCase)
              .order_by(models.DisputeCase.created_at.desc(), models.DisputeCase.id.desc())
              .all())


@router.get("/{case_id}", response_model=schemas.CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = db.get(models.DisputeCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


def _withdraw_verdict(db: Session, case_id: int) -> None:
    """Drop the ruling and the scorecard behind it. Used both when re-resolving and
    when late evidence arrives — a verdict must never outlive the evidence set it was
    computed from."""
    db.query(models.Verdict).filter(models.Verdict.case_id == case_id).delete()
    db.query(models.ScoreSignal).filter(models.ScoreSignal.case_id == case_id).delete()


@router.post("/{case_id}/evidence", response_model=schemas.EvidenceOut)
def submit_evidence(case_id: int, payload: schemas.EvidenceCreate, db: Session = Depends(get_db)):
    case = db.get(models.DisputeCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    parsed_facts = llm.parse_evidence(payload.evidence_type.value, payload.raw_content)
    evidence = models.Evidence(case_id=case_id, parsed_facts=parsed_facts, **payload.model_dump())
    db.add(evidence)

    # A ruling that has not been weighed against everything on file is stale, not
    # settled. Evidence arriving after resolution withdraws it and re-opens the case,
    # so a contradicted verdict can never be left standing as the final word.
    if case.status in (models.CaseStatus.scored, models.CaseStatus.resolved):
        _withdraw_verdict(db, case_id)
    case.status = models.CaseStatus.evidence_gathering

    db.commit()
    db.refresh(evidence)
    return evidence


def _record_result(
    db: Session,
    case: models.DisputeCase,
    result: connectors.ConnectorResult,
    seen: Set[Tuple[str, Optional[str]]],
) -> Dict:
    """Persist one connector outcome: the evidence row if it is new, and the log row
    either way. Shared by the synchronous and background runs so both write exactly
    the same history."""
    status, summary, evidence_id = result.status, result.summary, None

    if result.status == "hit":
        # Re-gathering must not duplicate the corpus. The scorer collapses identical
        # signals, but a second identical evidence row is still noise in both parties'
        # panels, so the skip is recorded rather than silently swallowed.
        if (result.source, result.raw_content) in seen:
            status = "skipped"
            summary = "Already on file from an earlier gather — no new evidence created."
        else:
            evidence = models.Evidence(
                case_id=case.id,
                submitted_by=result.submitted_by,
                evidence_type=result.evidence_type,
                raw_content=result.raw_content,
                parsed_facts=llm.parse_evidence(result.evidence_type, result.raw_content),
                source=result.source,
                auto_gathered=True,
            )
            db.add(evidence)
            db.flush()
            evidence_id = evidence.id
            seen.add((result.source, result.raw_content))

    db.add(models.GatherLog(
        case_id=case.id, source=result.source, status=status,
        latency_ms=result.latency_ms, summary=summary, evidence_id=evidence_id,
    ))
    return {
        "source": result.source,
        "status": status,
        "latency_ms": result.latency_ms,
        "summary": summary,
        "evidence_id": evidence_id,
        "evidence_type": result.evidence_type,
    }


def _reopen_if_resolved(db: Session, case: models.DisputeCase) -> bool:
    """Auto-gathered evidence invalidates a standing ruling exactly as a manual filing
    does. Without this the demo is one click from showing a verdict sitting above three
    documents it never saw."""
    if case.status in (models.CaseStatus.scored, models.CaseStatus.resolved):
        _withdraw_verdict(db, case.id)
        return True
    return False


# One gather at a time per case. Two runs racing each other both snapshot an empty
# `seen` set and each insert the full corpus, which the scorecard then reports as
# "corroborated by 2 documents" — one carrier record fetched twice. Single-process
# only; a multi-worker deployment would need a unique index on (case_id, source,
# raw_content) instead.
_gather_locks: Dict[int, threading.Lock] = defaultdict(threading.Lock)


def run_gather(db: Session, case: models.DisputeCase) -> Tuple[List[Dict], int]:
    """Query every source routed for this claim type, parse each hit into typed facts
    and persist it, and log every outcome — hits, misses alike.

    Lives here rather than in connectors.py so that layer stays a pure fetch
    simulation, and is shared with app.seed so the seeded corpus is produced by
    exactly the path the API runs. Returns the entries and the count of new evidence.
    """
    with _gather_locks[case.id]:
        db.refresh(case)
        seen = {(e.source, e.raw_content) for e in case.evidence}
        entries = [_record_result(db, case, r, seen) for r in connectors.gather(case)]
        created = sum(1 for e in entries if e["evidence_id"] is not None)
        # Only a gather that actually changed the evidence set may change the case's
        # state. A re-gather that finds nothing new used to un-resolve the case anyway,
        # leaving a settled ruling sitting under a "Gathering Evidence" badge forever.
        if created:
            _reopen_if_resolved(db, case)
            case.status = models.CaseStatus.evidence_gathering
        db.commit()
    return entries, created


def _gather_in_background(case_id: int) -> None:
    """Opens its own session on purpose: the request-scoped session from get_db is
    closed the moment the 202 is sent. Committing after each source is what lets the
    timeline fill in row by row instead of appearing all at once when the run ends.
    """
    db = SessionLocal()
    try:
        with _gather_locks[case_id]:
            case = db.get(models.DisputeCase, case_id)
            if case is None:
                return

            seen = {(e.source, e.raw_content) for e in case.evidence}
            for result in connectors.gather(case):
                # Per source, not per run. The UI waits for one log row per queued
                # source before it re-enables the button, so a single error row for a
                # run that failed on source 2 of 3 leaves it disabled forever.
                try:
                    time.sleep(random.uniform(*GATHER_PACING_S))
                    entry = _record_result(db, case, result, seen)
                    if entry["evidence_id"] is not None:
                        _reopen_if_resolved(db, case)
                        case.status = models.CaseStatus.evidence_gathering
                    db.commit()
                except Exception:
                    db.rollback()
                    db.add(models.GatherLog(
                        case_id=case_id, source=result.source, status="error",
                        latency_ms=result.latency_ms, evidence_id=None,
                        summary="This source failed to respond. Retry to query it again.",
                    ))
                    db.commit()
    finally:
        db.close()


# response_model is unset because the two modes answer with different shapes: 200 with
# the completed run, or 202 with a receipt for one still in flight.
@router.post("/{case_id}/gather", response_model=None, responses={
    200: {"model": schemas.GatherRunOut},
    202: {"model": schemas.GatherQueuedOut},
})
def gather_evidence(
    case_id: int,
    background_tasks: BackgroundTasks,
    async_mode: bool = False,
    db: Session = Depends(get_db),
):
    case = db.get(models.DisputeCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    if async_mode:
        queued = schemas.GatherQueuedOut(
            case_id=case_id,
            sources_queued=len(connectors.applicable_sources(case.claim_type)),
        )
        # Deliberately does NOT touch status. Flipping it to evidence_gathering here
        # closed the `resolved` gate before the background task could read it, so the
        # task never withdrew the standing verdict — and this is the path the UI calls.
        # Resolved cases are polled on their own cadence, so nothing needs the nudge.
        background_tasks.add_task(_gather_in_background, case_id)
        return JSONResponse(status_code=202, content=queued.model_dump())

    entries, created = run_gather(db, case)
    db.commit()

    return schemas.GatherRunOut(
        case_id=case_id,
        # Simulated sources are queried sequentially, so the wall-clock cost this
        # stands in for is the sum of their reported latencies.
        elapsed_ms=sum(e["latency_ms"] for e in entries),
        evidence_created=created,
        entries=entries,
    )


@router.get("/{case_id}/gather-log", response_model=list[schemas.GatherEntryOut])
def get_gather_log(case_id: int, db: Session = Depends(get_db)):
    case = db.get(models.DisputeCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    return (db.query(models.GatherLog)
              .filter(models.GatherLog.case_id == case_id)
              .order_by(models.GatherLog.id)
              .all())


@router.post("/{case_id}/resolve", response_model=schemas.VerdictOut)
def resolve_case(case_id: int, db: Session = Depends(get_db)):
    case = db.get(models.DisputeCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    signals, winner, card_member_score, merchant_score, confidence = score_case(case, case.evidence)

    _withdraw_verdict(db, case_id)
    for s in signals:
        db.add(models.ScoreSignal(
            case_id=case_id, signal_name=s.signal_name, detail=s.detail, weight=s.weight,
            favors=s.favors, evidence_ids=s.evidence_ids,
        ))

    # The scorecard has run and is on record, but nothing has been said about it yet.
    # Committing here makes that intermediate state real for a polling client rather
    # than leaving `scored` a declared-but-unreachable status. Offline the explanation
    # is instant, so the step passes through fast — that is the honest timing, and
    # padding it with a sleep would be staging a transition rather than reporting one.
    case.status = models.CaseStatus.scored
    db.commit()

    code, code_label = reason_codes.derive_reason_code(case, signals)
    explanation = llm.generate_explanation(case, signals, winner, confidence, code_label, case.evidence)

    verdict = models.Verdict(
        case_id=case_id,
        winner=winner,
        card_member_score=card_member_score,
        merchant_score=merchant_score,
        confidence=confidence,
        explanation=explanation,
        reason_code=code,
        reason_code_label=code_label,
        counterfactual=counterfactual_statement(signals, winner, card_member_score, merchant_score),
    )
    db.add(verdict)
    case.status = models.CaseStatus.resolved
    db.commit()
    db.refresh(verdict)
    return verdict
