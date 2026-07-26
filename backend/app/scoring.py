import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

# Above this much total evidence, confidence is allowed to reach its full margin.
# Below it, confidence is damped in proportion to how little evidence exists —
# a 15-0 split off one procedural signal is not the same certainty as 45-0 off
# carrier records, and reporting both as 100% is what made verdicts untrustworthy.
CONFIDENCE_SATURATION_POINTS = 60.0

# Minimum share of street-name tokens two addresses must share to be the same place.
_STREET_SIMILARITY = 0.5

# A parcel in transit longer than this, with no further scan, reads as undelivered.
STALE_TRANSIT_DAYS = 14

# Settlements further apart than this are more likely two real orders than one
# double-posted charge.
DUPLICATE_GAP_MINUTES = 1440


@dataclass
class Signal:
    signal_name: str
    detail: str
    weight: float
    favors: Optional[str]  # "card_member" | "merchant" | None
    # Every document that produced this signal — a list, not a single id, because
    # corroborating filings collapse into one signal and all of them were still read.
    # Keeping only the first made a corroborating document look unexamined, so the UI
    # could show "(corroborated by 2 documents)" and "no rule reads this" side by side.
    # Empty for procedural and disclosed-policy signals, which arise from the shape of
    # the case rather than from any filing. This is what lets the UI tell "your evidence
    # was weighed and went against you" apart from "no rule reads what you filed".
    evidence_ids: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class SignalSpec:
    weight: float
    favors: Optional[str]
    # Amex chargeback reason code. Deliberately unset — Phase 5 populates these
    # only after checking them against the official Amex guide. Shipping a wrong
    # code on a slide that cites that guide is worse than shipping none.
    reason_code: Optional[str] = None


# Every weight in the system lives here, so the scorecard can be printed, audited
# for asymmetry, and tuned in one place instead of being buried in branch bodies.
SIGNAL_CATALOG: Dict[str, SignalSpec] = {
    # --- delivery / carrier ------------------------------------------------
    "address_match": SignalSpec(25, "merchant"),
    "address_mismatch": SignalSpec(25, "card_member"),
    "not_shipped": SignalSpec(30, "card_member"),
    "returned_to_sender": SignalSpec(20, "card_member"),
    "stale_in_transit": SignalSpec(20, "card_member"),
    "delivery_confirmation_named": SignalSpec(20, "merchant"),
    "delivery_confirmation_thirdparty": SignalSpec(8, "merchant"),

    # --- merchant policy ---------------------------------------------------
    "policy_no_refund": SignalSpec(15, "merchant"),
    "policy_allows_refund": SignalSpec(15, "card_member"),
    "within_return_window": SignalSpec(15, "card_member"),
    "outside_return_window": SignalSpec(15, "merchant"),

    # --- correspondence ----------------------------------------------------
    "merchant_admission": SignalSpec(20, "card_member"),
    "refund_already_claimed": SignalSpec(25, "merchant"),

    # --- processor ledger --------------------------------------------------
    # Ledger evidence outweighs policy text on both sides: a ledger records what
    # happened, a policy only records what should have.
    "duplicate_settlement_confirmed": SignalSpec(35, "card_member"),
    "single_settlement_only": SignalSpec(30, "merchant"),
    "refund_already_issued": SignalSpec(30, "merchant"),
    "settlements_far_apart": SignalSpec(10, "merchant"),
    "no_refund_in_ledger": SignalSpec(25, "card_member"),
    "refund_posted_in_ledger": SignalSpec(30, "merchant"),

    # --- condition of goods ------------------------------------------------
    # Asymmetric on purpose: damage visible in a photo is stronger evidence than
    # its absence in one frame the merchant chose to take. Phase 6's asymmetry
    # audit allow-lists this pair so the choice stays documented, not hidden.
    "photo_shows_damage": SignalSpec(25, "card_member"),
    "photo_shows_no_damage": SignalSpec(15, "merchant"),

    # --- procedural --------------------------------------------------------
    # Weaker than any evidentiary signal. Once the system auto-gathers on both
    # parties' behalf, silence says much less than it used to.
    "no_merchant_evidence": SignalSpec(15, "card_member"),
    "no_card_member_evidence": SignalSpec(10, "merchant"),

    # --- disclosed policy (zero weight, shown on the verdict) --------------
    "provisional_credit_no_evidence": SignalSpec(0, None),
    "tie_break_provisional_credit": SignalSpec(0, None),
}


def _emit(signals: List[Signal], name: str, detail: str, evidence=None) -> None:
    spec = SIGNAL_CATALOG[name]
    evidence_id = getattr(evidence, "id", None)
    signals.append(Signal(name, detail, spec.weight, spec.favors,
                          [evidence_id] if evidence_id is not None else []))


# --- helpers ---------------------------------------------------------------

# Carriers and billing systems disagree on street-type spelling, so "45 Oak St" and
# "45 Oak Street" must compare equal. Normalised to the short form before matching.
_STREET_SUFFIXES = {
    "street": "st", "avenue": "ave", "road": "rd", "drive": "dr",
    "boulevard": "blvd", "lane": "ln", "court": "ct", "terrace": "ter",
    "parkway": "pkwy", "crescent": "cres", "place": "pl", "square": "sq",
    "highway": "hwy", "circle": "cir", "trail": "trl", "close": "cl",
}


def _parse_address(s: Optional[str]) -> Dict:
    """Split an address into house number, street tokens and locality tokens.

    The house number must lead the first comma-segment. That rule is what stops a
    bare postcode ("Dunmore 41022") from being read as a building number.
    """
    parts = [p.strip() for p in (s or "").split(",")]
    head_tokens = re.findall(r"[a-z0-9]+", parts[0].lower()) if parts else []
    tail_tokens = re.findall(r"[a-z0-9]+", " ".join(parts[1:]).lower())

    number = head_tokens[0] if head_tokens and head_tokens[0].isdigit() else None
    street = head_tokens[1:] if number else head_tokens
    return {
        "number": number,
        "street_tokens": {_STREET_SUFFIXES.get(t, t) for t in street},
        "locality_tokens": {_STREET_SUFFIXES.get(t, t) for t in tail_tokens},
    }


def _address_verdict(delivered_at: Optional[str], billing: Optional[str]) -> str:
    """-> "match" | "mismatch" | "indeterminate"

    "indeterminate" is the important one. The previous implementation matched on any
    two shared tokens, so "5 Main St, Boston" and "5 Elm St, Denver" scored as the same
    address, and anything it could not read fell through to a 25-point card-member win.
    A string we cannot parse must award nothing to either side.
    """
    a, b = _parse_address(delivered_at), _parse_address(billing)

    if not a["number"] or not b["number"] or not a["street_tokens"] or not b["street_tokens"]:
        return "indeterminate"
    if a["number"] != b["number"]:
        return "mismatch"

    overlap = a["street_tokens"] & b["street_tokens"]
    union = a["street_tokens"] | b["street_tokens"]
    if len(overlap) / len(union) < _STREET_SIMILARITY:
        return "mismatch"

    # Same number and street in two different towns is still two different places.
    if a["locality_tokens"] and b["locality_tokens"] and not (a["locality_tokens"] & b["locality_tokens"]):
        return "mismatch"
    return "match"


def _signee_is_card_member(signee: str, card_member_name: str) -> bool:
    """Compare on surnames, ignoring initials, so "M. Torres" matches "Miguel Torres"."""
    def surnames(value: str) -> set:
        return {t.strip(".,").lower() for t in (value or "").split() if len(t.strip(".,")) > 1}

    return bool(surnames(signee) & surnames(card_member_name))


def _iso_date(value: Optional[str]) -> Optional[date]:
    """Parse an ISO date out of parsed_facts. Returns None rather than raising — a
    date we cannot read must produce no signal, never a defaulted one."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except (TypeError, ValueError):
        return None


def _case_date(case) -> Optional[date]:
    created = getattr(case, "created_at", None)
    return created.date() if created is not None else None


def _amounts_equal(a: Optional[float], b: Optional[float]) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < 0.01


def _confidence(card_member_score: float, merchant_score: float) -> float:
    """Margin, scaled by how much evidence produced it."""
    total = card_member_score + merchant_score
    if total == 0:
        return 0.0
    margin = abs(card_member_score - merchant_score) / total
    mass = min(1.0, total / CONFIDENCE_SATURATION_POINTS)
    return round(margin * (0.5 + 0.5 * mass), 3)


def _dedupe(signals: List[Signal]) -> List[Signal]:
    """Collapse identical signals raised by more than one document.

    Two uploads of the same carrier scan previously scored twice, so a merchant could
    double their total by submitting a duplicate. Corroboration is still worth showing,
    so the count goes in the detail — it just stops being worth extra points.
    """
    seen: Dict[tuple, Signal] = {}
    counts: Dict[tuple, int] = {}
    sources: Dict[tuple, List[int]] = {}
    order: List[tuple] = []

    for signal in signals:
        key = (signal.signal_name, signal.detail)
        if key not in seen:
            seen[key] = signal
            counts[key] = 1
            sources[key] = list(signal.evidence_ids)
            order.append(key)
        else:
            counts[key] += 1
            # Every contributing document is retained. A corroborating filing was read
            # by the same rule, so it must not look unexamined downstream.
            sources[key].extend(i for i in signal.evidence_ids if i not in sources[key])

    result = []
    for key in order:
        signal = seen[key]
        detail = signal.detail
        if counts[key] > 1:
            detail = "{} (corroborated by {} documents)".format(detail, counts[key])
        result.append(Signal(signal.signal_name, detail, signal.weight, signal.favors, sources[key]))
    return result


def _evidence_of(evidence_list, evidence_type) -> List:
    return [e for e in evidence_list
            if e.evidence_type == evidence_type and e.parsed_facts]


def _facts_of(evidence_list, evidence_type) -> List[Dict]:
    return [e.parsed_facts for e in _evidence_of(evidence_list, evidence_type)]


# --- scoring ---------------------------------------------------------------

def score_case(case, evidence_list):
    """Transparent weighted scorecard. Every point is traceable to a named signal
    so the verdict can be explained, not just asserted."""
    signals: List[Signal] = []
    filed_on = _case_date(case)

    # A refund the merchant can show it already paid makes the underlying complaint
    # moot, so it suppresses signals that would otherwise pay the card member twice.
    refund_settled = any(
        f.get("refund_already_claimed") for f in
        _facts_of(evidence_list, "email") + _facts_of(evidence_list, "chat_log")
    ) or any(
        f.get("refund_issued") and _amounts_equal(f.get("refund_amount"), getattr(case, "amount", None))
        for f in _facts_of(evidence_list, "processor_ledger")
    )

    # A refund is "owed" when the merchant's own policy or correspondence says so.
    # Without that, the absence of a refund proves nothing that the claim did not
    # already assert.
    refund_appears_owed = any(
        f.get("refund_allowed") is True for f in _facts_of(evidence_list, "policy_text")
    ) or any(
        f.get("merchant_admitted_issue") or f.get("refund_already_claimed")
        for f in _facts_of(evidence_list, "email") + _facts_of(evidence_list, "chat_log")
    )

    # --- carrier / delivery ------------------------------------------------
    for e in evidence_list:
        if e.evidence_type != "tracking_data" or not e.parsed_facts:
            continue
        facts = e.parsed_facts
        status = facts.get("status")
        delivered_at = facts.get("delivered_at")
        signed_by = facts.get("signed_by")

        if status == "delivered" and delivered_at:
            verdict = _address_verdict(delivered_at, case.card_member_address)
            if verdict == "match":
                _emit(signals, "address_match",
                      f"Delivered to {delivered_at}, matches card member's address on file", e)
            elif verdict == "mismatch":
                _emit(signals, "address_mismatch",
                      f"Delivered to {delivered_at}, does not match address on file "
                      f"({case.card_member_address})", e)
            # indeterminate: the address could not be read on one side, so neither
            # party gains from it. The signature, if any, still stands on its own.
        elif status == "not_shipped":
            _emit(signals, "not_shipped", "Carrier tracking shows the item was never shipped", e)
        elif status == "returned":
            _emit(signals, "returned_to_sender",
                  "Carrier tracking shows the package was returned to sender", e)
        elif status == "in_transit":
            scanned = _iso_date(facts.get("last_scan_at"))
            if scanned and filed_on and (filed_on - scanned).days > STALE_TRANSIT_DAYS:
                _emit(signals, "stale_in_transit",
                      f"Last carrier scan {scanned.isoformat()}, {(filed_on - scanned).days} days "
                      "before the dispute was filed, with no delivery recorded since", e)

        # A generic signee ("Receiving Dept", "unknown recipient") is filtered out
        # upstream in llm._extract_signee and arrives here as None.
        if signed_by:
            if _signee_is_card_member(signed_by, case.card_member_name):
                _emit(signals, "delivery_confirmation_named",
                      f"Delivery signed for by {signed_by}, matching the card member on file", e)
            else:
                _emit(signals, "delivery_confirmation_thirdparty",
                      f"Delivery signed for by {signed_by}, who is not the card member", e)

    # --- merchant policy ---------------------------------------------------
    for e in _evidence_of(evidence_list, "policy_text"):
        facts = e.parsed_facts
        if case.claim_type == "refund_not_processed":
            if facts.get("refund_allowed") is False:
                _emit(signals, "policy_no_refund",
                      "Merchant's stated policy does not allow refunds for this case", e)
            elif facts.get("refund_allowed") is True:
                _emit(signals, "policy_allows_refund",
                      "Merchant's own policy allows a refund, and none was processed", e)
            # refund_allowed is None when the policy did not say — no signal either way.

        # Return-window arithmetic needs a policy window and a dated receipt. Missing
        # either means no signal; a window we cannot compute favours nobody.
        window = facts.get("return_window_days")
        if case.claim_type == "not_as_described" and window and filed_on:
            for receipt in _facts_of(evidence_list, "receipt"):
                ordered = _iso_date(receipt.get("order_date"))
                if not ordered:
                    continue
                elapsed = (filed_on - ordered).days
                if elapsed <= window:
                    _emit(signals, "within_return_window",
                          f"Disputed {elapsed} days after the order, inside the merchant's "
                          f"{window}-day return window", e)
                else:
                    _emit(signals, "outside_return_window",
                          f"Disputed {elapsed} days after the order, outside the merchant's "
                          f"{window}-day return window", e)

    # --- correspondence ----------------------------------------------------
    for e in evidence_list:
        if e.evidence_type not in ("email", "chat_log") or not e.parsed_facts:
            continue
        facts = e.parsed_facts
        if facts.get("refund_already_claimed") and case.claim_type in (
                "duplicate_charge", "refund_not_processed"):
            _emit(signals, "refund_already_claimed",
                  "Merchant correspondence states the refund has already been issued", e)
        # An admission that has already been remedied is not grounds for a chargeback,
        # so a confirmed refund suppresses it rather than paying out on top.
        elif facts.get("merchant_admitted_issue") and not refund_settled:
            _emit(signals, "merchant_admission", "Merchant correspondence acknowledges the issue", e)

    # --- processor ledger --------------------------------------------------
    for e in _evidence_of(evidence_list, "processor_ledger"):
        facts = e.parsed_facts
        settlements = facts.get("settlement_count") or 0
        auths = facts.get("auth_count") or 0
        amounts = [float(a) for a in (facts.get("settlement_amounts") or [])]
        gap = facts.get("minutes_between_settlements")
        refund_issued = bool(facts.get("refund_issued"))
        refund_covers = refund_issued and _amounts_equal(
            facts.get("refund_amount"), getattr(case, "amount", None))

        if case.claim_type == "duplicate_charge":
            if refund_covers:
                _emit(signals, "refund_already_issued",
                      "Processor ledger shows a refund matching the disputed amount was "
                      "already posted", e)
            elif settlements >= 2 and len(set(amounts)) == 1:
                _emit(signals, "duplicate_settlement_confirmed",
                      f"Processor ledger shows {settlements} settlements of "
                      f"${amounts[0]:.2f} with no offsetting refund", e)
            elif auths >= 2 and settlements == 1:
                _emit(signals, "single_settlement_only",
                      f"Processor ledger shows {auths} authorisations but only one "
                      "settlement — the duplicate was never captured", e)
            if gap is not None and gap > DUPLICATE_GAP_MINUTES:
                _emit(signals, "settlements_far_apart",
                      f"Settlements are {gap} minutes apart, consistent with two separate orders", e)

        elif case.claim_type == "refund_not_processed":
            if refund_issued:
                _emit(signals, "refund_posted_in_ledger",
                      "Processor ledger shows a refund was posted for this transaction", e)
            elif refund_appears_owed:
                # Only evidence once a refund is shown to be due. On a
                # refund-not-processed claim "no refund was posted" is the complaint
                # restated, and scoring it unconditionally handed the card member
                # points for filing the dispute at all.
                _emit(signals, "no_refund_in_ledger",
                      "Processor ledger shows no refund was posted, though the merchant's "
                      "own policy or correspondence indicates one was due", e)

    # --- condition of goods ------------------------------------------------
    if case.claim_type == "not_as_described":
        for e in evidence_list:
            if e.evidence_type != "photo" or not e.parsed_facts:
                continue
            shows_damage = e.parsed_facts.get("shows_damage")
            if shows_damage is True:
                _emit(signals, "photo_shows_damage",
                      "Photographic evidence shows the goods were damaged", e)
            elif shows_damage is False and e.submitted_by == "merchant":
                _emit(signals, "photo_shows_no_damage",
                      "Merchant photograph shows the goods intact and undamaged", e)

    # --- procedural --------------------------------------------------------
    #
    # The adverse inference turns on whether a party put anything PROBATIVE on the
    # record, not on whether they filed a document. Testing mere presence rewarded
    # filing something meaningless: a merchant who sent "we'll look into this" dodged
    # the inference entirely while the card member still carried theirs. A filing that
    # produced no signal is, for this purpose, the same as no filing.
    card_member_evidence = [e for e in evidence_list if e.submitted_by == "card_member"]
    merchant_evidence = [e for e in evidence_list if e.submitted_by == "merchant"]

    weighed = {i for s in signals for i in s.evidence_ids}

    def _engaged(items):
        """Did this party actually answer the case?

        Two ways to qualify. Either a filing produced a signal, or it states a
        reasoned denial — "our records show the consignment passed inspection" is a
        position even though the scorecard awards it nothing. What does NOT qualify
        is a filing that neither supports a finding nor contests one, because that is
        silence with a covering note, and treating it as engagement is precisely the
        loophole this rule exists to close.
        """
        for e in items:
            if getattr(e, "id", None) in weighed:
                return True
            facts = getattr(e, "parsed_facts", None) or {}
            if facts.get("merchant_denies_claim"):
                return True
        return False

    # Never on a wholly empty case: with nothing from anyone there is nothing to draw
    # an inference from, and that case resolves under the disclosed provisional-credit
    # rule instead.
    if evidence_list and not _engaged(merchant_evidence):
        _emit(signals, "no_merchant_evidence",
              "Merchant filed {} that the scorecard could read as supporting their "
              "position; see the evidence-gathering log for the sources queried".format(
                  "nothing" if not merchant_evidence else
                  "{} document(s), none of which".format(len(merchant_evidence))))

    # Narrowed to the one claim type where a card member can reasonably be expected to
    # produce positive proof. Nobody can prove a parcel did not arrive, and the system
    # now gathers on both parties' behalf, so silence is much weaker evidence than it was.
    if case.claim_type == "not_as_described":
        has_proof = any(e.evidence_type in ("photo", "receipt") for e in card_member_evidence)
        if not has_proof and not _engaged(card_member_evidence) and merchant_evidence:
            _emit(signals, "no_card_member_evidence",
                  "Card member produced neither a photograph nor a receipt, both of which "
                  "are obtainable for this claim type")

    signals = _dedupe(signals)

    card_member_score = sum(s.weight for s in signals if s.favors == "card_member")
    merchant_score = sum(s.weight for s in signals if s.favors == "merchant")
    total = card_member_score + merchant_score

    # Both remaining branches resolve in the card member's favour. That is deliberate
    # issuer provisional-credit practice, not an accident of comparison operators — so
    # each one emits a zero-weight signal that says so on the verdict itself.
    if total == 0:
        _emit(signals, "provisional_credit_no_evidence",
              "No conclusive evidence from either party. Issuer provisional-credit policy "
              "resolves undetermined cases in the card member's favour, pending merchant rebuttal.")
        return signals, "card_member", 0.0, 0.0, 0.0

    if card_member_score == merchant_score:
        _emit(signals, "tie_break_provisional_credit",
              "Evidence is evenly balanced at {:.0f} points each. Issuer provisional-credit "
              "policy resolves ties in the card member's favour.".format(card_member_score))
        winner = "card_member"
    else:
        winner = "card_member" if card_member_score > merchant_score else "merchant"

    return signals, winner, card_member_score, merchant_score, _confidence(card_member_score, merchant_score)


# --- counterfactual reasoning ----------------------------------------------
#
# Pure arithmetic over the scorecard, so it cannot hallucinate and it is auditable
# line by line. It answers the only question a losing party actually asks: what
# would have had to be different?

def minimal_flip_set(signals: List[Signal], winner: str) -> List[Signal]:
    """Smallest set of winning signals whose removal changes the outcome.

    Greedy by descending weight, which is optimal for cardinality. Returns [] when no
    removal flips it — that happens when the loser scored nothing, since a 0-0 case
    still resolves to the card member under provisional credit.
    """
    card_member = sum(s.weight for s in signals if s.favors == "card_member")
    merchant = sum(s.weight for s in signals if s.favors == "merchant")
    winning = sorted(
        [s for s in signals if s.favors == winner and s.weight > 0],
        key=lambda s: -s.weight,
    )

    chosen: List[Signal] = []
    removed = 0.0
    for signal in winning:
        chosen.append(signal)
        removed += signal.weight
        if winner == "card_member":
            # Ties go to the card member, so the merchant needs a strict lead.
            if card_member - removed < merchant:
                return chosen
        elif merchant - removed <= card_member:
            return chosen
    return []


def counterfactual_statement(signals: List[Signal], winner: str,
                             card_member_score: float, merchant_score: float) -> str:
    loser = "merchant" if winner == "card_member" else "card_member"
    label = {"card_member": "the card member", "merchant": "the merchant"}
    margin = abs(card_member_score - merchant_score)

    flip = minimal_flip_set(signals, winner)
    if not flip:
        return (
            "No single established fact carries this outcome — {} produced nothing that "
            "weighed in their favour, so there is nothing to remove that would change it."
        ).format(label[loser])

    removed = sum(s.weight for s in flip)
    if len(flip) == 1:
        basis = "if {} had not been established (−{:.0f} points)".format(flip[0].detail, flip[0].weight)
    else:
        joined = "; ".join(s.detail for s in flip)
        basis = "if these had not been established (−{:.0f} points in total): {}".format(removed, joined)

    # Ties resolve to the card member, so the merchant has to clear the margin outright.
    needed = margin if loser == "card_member" else margin + 1
    return (
        "This would have gone to {} {}. Equivalently, {} would have needed roughly "
        "{:.0f} more points of evidence in their favour."
    ).format(label[loser], basis, label[loser], needed)
