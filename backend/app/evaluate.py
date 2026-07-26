"""Offline evaluation harness for the dispute scorecard.

Replays the labelled corpus in tests/goldens.json through the real evidence
parser and the real scorer, then reports accuracy, calibration, fairness and
latency. No database, no server, no network — run it any time:

    python -m app.evaluate

Every phase of the build is expected to move one of these numbers, so record
the output before making scorer changes.
"""
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import llm, reason_codes
from .scoring import counterfactual_statement, score_case

GOLDENS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "goldens.json")

# Signals that exist to disclose a policy choice rather than to weigh evidence.
# Bias traceable to these is defensible; bias that is not is a defect.
DISCLOSURE_SIGNALS = {
    "insufficient_evidence",
    "provisional_credit_no_evidence",
    "tie_break_provisional_credit",
}

PARTIES = ("card_member", "merchant")


# --- duck-typed stand-ins for the ORM objects score_case expects -----------

@dataclass
class _Case:
    transaction_id: str
    card_member_name: str
    card_member_address: str
    merchant_name: str
    amount: float
    claim_type: str
    claim_text: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class _Evidence:
    id: int
    submitted_by: str
    evidence_type: str
    raw_content: str
    parsed_facts: Dict[str, Any]


@dataclass
class ReplayResult:
    id: str
    transaction_id: str
    claim_type: str
    difficulty: str
    expected: Optional[str]
    actual: str
    card_member_score: float
    merchant_score: float
    confidence: float
    signals: List[str]
    elapsed_ms: float

    @property
    def arbitrable(self) -> bool:
        return self.expected is not None

    @property
    def correct(self) -> bool:
        return self.arbitrable and self.expected == self.actual

    @property
    def disclosure_driven(self) -> bool:
        return any(s in DISCLOSURE_SIGNALS for s in self.signals)


def load_goldens(path: str = GOLDENS_PATH) -> List[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def replay(golden: dict) -> ReplayResult:
    """Parse every piece of evidence and score the case, exactly as the API does."""
    start = time.perf_counter()

    # A case with no pinned filing date is treated as filed today. Cases whose
    # outcome depends on a return window carry `filed_on`, or they would age against
    # the wall clock and quietly change answer between runs.
    filed_on = golden.get("filed_on")
    case = _Case(
        transaction_id=golden["transaction_id"],
        card_member_name=golden["card_member_name"],
        card_member_address=golden["card_member_address"],
        merchant_name=golden["merchant_name"],
        amount=golden["amount"],
        claim_type=golden["claim_type"],
        claim_text=golden["claim_text"],
        created_at=(datetime.strptime(filed_on, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if filed_on else datetime.now(timezone.utc)),
    )
    evidence = [
        _Evidence(
            id=index,
            submitted_by=submitted_by,
            evidence_type=evidence_type,
            raw_content=raw_content,
            parsed_facts=llm.parse_evidence(evidence_type, raw_content),
        )
        for index, (submitted_by, evidence_type, raw_content) in enumerate(golden["evidence"], start=1)
    ]

    signals, winner, cm_score, m_score, confidence = score_case(case, evidence)
    # Included so the measured latency covers the whole pipeline the demo runs —
    # reason-code derivation, explanation and counterfactual all sit on the resolve path.
    code, code_label = reason_codes.derive_reason_code(case, signals)
    llm.generate_explanation(case, signals, winner, confidence, code_label, evidence)
    counterfactual_statement(signals, winner, cm_score, m_score)

    return ReplayResult(
        id=golden["id"],
        transaction_id=golden["transaction_id"],
        claim_type=golden["claim_type"],
        difficulty=golden["difficulty"],
        expected=golden["expected_winner"],
        actual=winner,
        card_member_score=cm_score,
        merchant_score=m_score,
        confidence=confidence,
        signals=[s.signal_name for s in signals],
        elapsed_ms=(time.perf_counter() - start) * 1000,
    )


# --- reports ---------------------------------------------------------------

def accuracy_report(results: List[ReplayResult]) -> dict:
    arbitrable = [r for r in results if r.arbitrable]
    correct = [r for r in arbitrable if r.correct]

    per_type: Dict[str, Dict[str, int]] = {}
    for r in arbitrable:
        bucket = per_type.setdefault(r.claim_type, {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += int(r.correct)

    per_difficulty: Dict[str, Dict[str, int]] = {}
    for r in arbitrable:
        bucket = per_difficulty.setdefault(r.difficulty, {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += int(r.correct)

    return {
        "total": len(results),
        "arbitrable": len(arbitrable),
        "abstained": len(results) - len(arbitrable),
        "correct": len(correct),
        "accuracy": len(correct) / len(arbitrable) if arbitrable else 0.0,
        "per_claim_type": per_type,
        "per_difficulty": per_difficulty,
        "failures": [r for r in arbitrable if not r.correct],
    }


def bias_report(results: List[ReplayResult]) -> dict:
    """Directional fairness.

    bias_gap is the difference in recall between the two parties: how much more
    reliably the scorer finds for one side than the other. attributed_share is
    the fraction of wrong verdicts that a disclosed policy signal accounts for.
    The target is not a zero gap — it is a gap fully explained by a rule we
    state out loud.
    """
    arbitrable = [r for r in results if r.arbitrable]

    recall = {}
    for party in PARTIES:
        expected = [r for r in arbitrable if r.expected == party]
        hits = [r for r in expected if r.correct]
        recall[party] = len(hits) / len(expected) if expected else None

    both = [recall[p] for p in PARTIES if recall[p] is not None]
    gap = abs(both[0] - both[1]) if len(both) == 2 else 0.0

    errors = [r for r in arbitrable if not r.correct]
    favouring = {p: [r for r in errors if r.actual == p] for p in PARTIES}
    attributed = [r for r in errors if r.disclosure_driven]

    verdicts = {p: sum(1 for r in results if r.actual == p) for p in PARTIES}
    labels = {p: sum(1 for r in results if r.expected == p) for p in PARTIES}

    return {
        "recall": recall,
        "bias_gap": gap,
        "errors": len(errors),
        "errors_favouring_card_member": len(favouring["card_member"]),
        "errors_favouring_merchant": len(favouring["merchant"]),
        "attributed_to_disclosed_policy": len(attributed),
        "attributed_share": len(attributed) / len(errors) if errors else 1.0,
        "verdict_distribution": verdicts,
        "label_distribution": labels,
        "verdict_share_card_member": verdicts["card_member"] / len(results) if results else 0.0,
        "label_share_card_member": labels["card_member"] / len(results) if results else 0.0,
        "disclosure_driven_cases": [r for r in results if r.disclosure_driven],
    }


def calibration_report(results: List[ReplayResult]) -> dict:
    """Confidence should be high when right and low when wrong. Confidently wrong
    verdicts are the ones that do real damage, on stage and in production."""
    arbitrable = [r for r in results if r.arbitrable]
    correct = [r.confidence for r in arbitrable if r.correct]
    wrong = [r.confidence for r in arbitrable if not r.correct]

    return {
        "mean_confidence_correct": statistics.mean(correct) if correct else 0.0,
        "mean_confidence_wrong": statistics.mean(wrong) if wrong else 0.0,
        "separation": (statistics.mean(correct) if correct else 0.0) - (statistics.mean(wrong) if wrong else 0.0),
        "confidently_wrong": [r for r in arbitrable if not r.correct and r.confidence >= 0.8],
        "max_confidence_single_signal": [
            r for r in results if r.confidence >= 0.99 and len([s for s in r.signals]) <= 1
        ],
    }


def latency_report(results: List[ReplayResult]) -> dict:
    times = sorted(r.elapsed_ms for r in results)
    if not times:
        return {"p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "p50": times[len(times) // 2],
        "p95": times[min(len(times) - 1, int(len(times) * 0.95))],
        "max": times[-1],
        "total_ms": sum(times),
    }


# --- rendering -------------------------------------------------------------

def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else "{:.0%}".format(value)


def _render(results: List[ReplayResult]) -> str:
    acc = accuracy_report(results)
    bias = bias_report(results)
    cal = calibration_report(results)
    lat = latency_report(results)

    out: List[str] = []
    add = out.append

    add("# Dispute scorecard evaluation\n")
    add("Corpus: {} cases ({} arbitrable, {} abstained)\n".format(
        acc["total"], acc["arbitrable"], acc["abstained"]))

    add("## Per-case results\n")
    add("| ID | TX | Claim type | Difficulty | Expected | Actual | CM | MCH | Conf | OK |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        mark = "—" if not r.arbitrable else ("YES" if r.correct else "**NO**")
        add("| {} | {} | {} | {} | {} | {} | {:.0f} | {:.0f} | {:.0%} | {} |".format(
            r.id, r.transaction_id, r.claim_type, r.difficulty,
            r.expected or "(abstain)", r.actual,
            r.card_member_score, r.merchant_score, r.confidence, mark))

    add("\n## Accuracy\n")
    add("**{}** ({}/{} arbitrable cases)\n".format(
        _pct(acc["accuracy"]), acc["correct"], acc["arbitrable"]))
    add("| Claim type | Correct | Total | Accuracy |")
    add("|---|---|---|---|")
    for claim_type in sorted(acc["per_claim_type"]):
        bucket = acc["per_claim_type"][claim_type]
        add("| {} | {} | {} | {} |".format(
            claim_type, bucket["correct"], bucket["n"], _pct(bucket["correct"] / bucket["n"])))
    add("")
    add("| Difficulty | Correct | Total | Accuracy |")
    add("|---|---|---|---|")
    for difficulty in sorted(acc["per_difficulty"]):
        bucket = acc["per_difficulty"][difficulty]
        add("| {} | {} | {} | {} |".format(
            difficulty, bucket["correct"], bucket["n"], _pct(bucket["correct"] / bucket["n"])))

    if acc["failures"]:
        add("\n### Incorrect verdicts\n")
        for r in acc["failures"]:
            add("- **{} ({})** expected `{}`, got `{}` at {:.0%} confidence — signals: {}".format(
                r.id, r.transaction_id, r.expected, r.actual, r.confidence,
                ", ".join(r.signals) or "none"))

    add("\n## Fairness\n")
    add("| Metric | Value |")
    add("|---|---|")
    add("| Recall, card member | {} |".format(_pct(bias["recall"]["card_member"])))
    add("| Recall, merchant | {} |".format(_pct(bias["recall"]["merchant"])))
    add("| **bias_gap** | **{:.3f}** |".format(bias["bias_gap"]))
    add("| Verdicts favouring card member | {} ({}) |".format(
        bias["verdict_distribution"]["card_member"], _pct(bias["verdict_share_card_member"])))
    add("| Labels favouring card member | {} ({}) |".format(
        bias["label_distribution"]["card_member"], _pct(bias["label_share_card_member"])))
    add("| Errors favouring card member | {} |".format(bias["errors_favouring_card_member"]))
    add("| Errors favouring merchant | {} |".format(bias["errors_favouring_merchant"]))
    add("| **attributed to disclosed policy** | **{}/{} ({})** |".format(
        bias["attributed_to_disclosed_policy"], bias["errors"], _pct(bias["attributed_share"])))
    add("\n> Target is not `bias_gap == 0`. It is that every point of directional")
    add("> bias is traceable to a policy the system states out loud.\n")

    if bias["disclosure_driven_cases"]:
        add("Cases resolved by a disclosed policy signal rather than by evidence:\n")
        for r in bias["disclosure_driven_cases"]:
            add("- {} ({}) → `{}` — {}".format(
                r.id, r.transaction_id, r.actual,
                ", ".join(s for s in r.signals if s in DISCLOSURE_SIGNALS)))

    add("\n## Calibration\n")
    add("| Metric | Value |")
    add("|---|---|")
    add("| Mean confidence when correct | {:.0%} |".format(cal["mean_confidence_correct"]))
    add("| Mean confidence when wrong | {:.0%} |".format(cal["mean_confidence_wrong"]))
    add("| Separation (higher is better) | {:.3f} |".format(cal["separation"]))
    add("| Confidently wrong (>=80%) | {} |".format(len(cal["confidently_wrong"])))
    add("| 100% confidence off <=1 signal | {} |".format(len(cal["max_confidence_single_signal"])))
    for r in cal["confidently_wrong"]:
        add("\n- ⚠️ **{} ({})** — {:.0%} confidence, and wrong. Signals: {}".format(
            r.id, r.transaction_id, r.confidence, ", ".join(r.signals) or "none"))

    add("\n## Latency (offline, parse + score + explain)\n")
    add("| Metric | ms |")
    add("|---|---|")
    add("| p50 | {:.2f} |".format(lat["p50"]))
    add("| p95 | {:.2f} |".format(lat["p95"]))
    add("| max | {:.2f} |".format(lat["max"]))
    add("| total for corpus | {:.2f} |".format(lat["total_ms"]))

    return "\n".join(out)


def main() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("NOTE: ANTHROPIC_API_KEY is set — this run will hit the API and will not be "
              "reproducible. Unset it to measure the offline pipeline.\n")
    results = [replay(g) for g in load_goldens()]
    print(_render(results))


if __name__ == "__main__":
    main()
