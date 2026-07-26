"""Scorer unit tests.

One test per behaviour the scorecard depends on, plus an explicit regression for
every defect found in review. Runs with no database, no server and no API key —
score_case is pure over duck-typed evidence.
"""
import pytest

from app.llm import _extract_signee, _mock_parse_evidence
from app.scoring import (
    SIGNAL_CATALOG,
    Signal,
    _address_verdict,
    _confidence,
    _dedupe,
    _signee_is_card_member,
    counterfactual_statement,
    minimal_flip_set,
    score_case,
)


class FakeEvidence:
    _next_id = 1

    def __init__(self, evidence_type, parsed_facts, submitted_by="merchant", auto_gathered=False):
        self.id = FakeEvidence._next_id
        FakeEvidence._next_id += 1
        self.evidence_type = evidence_type
        self.parsed_facts = parsed_facts
        self.submitted_by = submitted_by
        self.auto_gathered = auto_gathered


class FakeCase:
    def __init__(self, claim_type="item_not_received", address="45 Oak Street, Springfield",
                 name="Priya Sharma", amount=100.0, created_at=None):
        self.transaction_id = "TXTEST"
        self.claim_type = claim_type
        self.card_member_address = address
        self.card_member_name = name
        self.amount = amount
        self.claim_text = "test claim"
        self.created_at = created_at


def names(signals):
    return [s.signal_name for s in signals]


def tracking(**facts):
    base = {"status": None, "delivered_at": None, "signed_by": None, "last_scan_at": None}
    base.update(facts)
    return FakeEvidence("tracking_data", base)


# --- address matching (D6) -------------------------------------------------

def test_address_same_city_different_street_is_mismatch():
    assert _address_verdict("99 Pine Ave, Rivertown", "12 Pine Ave, Rivertown") == "mismatch"


def test_address_same_number_different_city_is_mismatch():
    assert _address_verdict("5 Elm St, Denver", "5 Main St, Boston") == "mismatch"


def test_address_identical_street_different_town_is_mismatch():
    assert _address_verdict("5 Main St, Boston", "5 Main St, Denver") == "mismatch"


def test_address_street_suffix_abbreviation_still_matches():
    assert _address_verdict("45 Oak St", "45 Oak Street, Springfield") == "match"


def test_unparseable_address_is_indeterminate_and_awards_nobody():
    """The address itself must score nothing for either side. The merchant still draws
    the adverse inference, because a filing the scorecard cannot read is not a filing
    that supports their position."""
    assert _address_verdict("Dunmore 41022", "23 Fernhill Ave, Dunmore") == "indeterminate"
    case = FakeCase(address="23 Fernhill Ave, Dunmore")
    signals, _, cm, m, _ = score_case(case, [tracking(status="delivered", delivered_at="Dunmore 41022")])
    assert "address_match" not in names(signals)
    assert "address_mismatch" not in names(signals)
    assert names(signals) == ["no_merchant_evidence"]


# --- delivery confirmation (D1) --------------------------------------------

def test_negated_signature_awards_nothing():
    assert _extract_signee("Attempted delivery. Not signed by anyone.") is None


def test_generic_signee_awards_nothing():
    for text in ("signed by unknown recipient.", "signed by Receiving Dept.", "signed by driver."):
        assert _extract_signee(text) is None, text


def test_real_signature_survives_trailing_text_and_punctuation():
    assert _extract_signee("signed by A. Stone on 2026-06-02.") == "A. Stone"
    assert _extract_signee("signed by J. O'Brien.") == "J. O'Brien"
    assert _extract_signee("signed by Jose Nunez-Diaz.") == "Jose Nunez-Diaz"


def test_named_signee_outweighs_third_party():
    assert _signee_is_card_member("M. Torres", "Miguel Torres")
    assert not _signee_is_card_member("R. Patel", "Owen Frost")
    assert (SIGNAL_CATALOG["delivery_confirmation_named"].weight
            > SIGNAL_CATALOG["delivery_confirmation_thirdparty"].weight)


# --- confidence (D8, D10) --------------------------------------------------

def test_single_signal_confidence_is_damped():
    assert _confidence(15, 0) == 0.625
    assert _confidence(45, 0) == 0.875


def test_zero_evidence_confidence_is_zero_not_a_constant():
    assert _confidence(0, 0) == 0.0


def test_no_case_reaches_full_confidence_on_one_small_signal():
    assert _confidence(15, 0) < 0.8


# --- tie-breaking and disclosure (D7) --------------------------------------

def test_tie_emits_disclosure_signal_and_goes_to_card_member():
    """A real 20-20 tie built through the scorer, not a hand-assembled list:
    one delivery signed by the card member at an unparseable address (20 merchant),
    one parcel stale in transit (20 card member)."""
    from datetime import datetime

    case = FakeCase(claim_type="item_not_received", name="Priya Sharma",
                    created_at=datetime(2026, 7, 1))
    evidence = [
        tracking(status="delivered", delivered_at="Dunmore 41022", signed_by="P. Sharma"),
        tracking(status="in_transit", last_scan_at="2026-05-20"),
    ]
    signals, winner, cm, m, conf = score_case(case, evidence)

    assert cm == m == 20.0, names(signals)
    assert winner == "card_member", "ties resolve to the card member by policy"
    assert "tie_break_provisional_credit" in names(signals), (
        "a tie must disclose the rule that decided it, not resolve silently")
    assert conf == 0.0


def test_zero_evidence_emits_provisional_credit_disclosure():
    signals, winner, cm, m, conf = score_case(FakeCase(), [])
    assert names(signals) == ["provisional_credit_no_evidence"]
    assert winner == "card_member"
    assert conf == 0.0


def test_disclosure_signals_are_zero_weight_and_favour_nobody():
    for name in ("provisional_credit_no_evidence", "tie_break_provisional_credit"):
        spec = SIGNAL_CATALOG[name]
        assert spec.weight == 0 and spec.favors is None


# --- deduplication (D9) ----------------------------------------------------

def test_duplicate_evidence_scores_once_and_notes_corroboration():
    deduped = _dedupe([
        Signal("address_match", "same detail", 25, "merchant"),
        Signal("address_match", "same detail", 25, "merchant"),
    ])
    assert len(deduped) == 1
    assert "corroborated by 2" in deduped[0].detail
    assert deduped[0].weight == 25


# --- claim-type coverage (D11, D12) ----------------------------------------

def test_duplicate_charge_confirmed_from_ledger():
    case = FakeCase(claim_type="duplicate_charge", amount=999.0)
    ledger = FakeEvidence("processor_ledger", {
        "auth_count": 2, "settlement_count": 2, "settlement_amounts": [999.0, 999.0],
        "minutes_between_settlements": 3, "refund_issued": False, "refund_amount": None,
    }, submitted_by="card_member")
    signals, winner, _, _, _ = score_case(case, [ledger])
    assert "duplicate_settlement_confirmed" in names(signals)
    assert winner == "card_member"


def test_refund_already_issued_beats_apology_email():
    """TX1014: the merchant refunded the duplicate and said sorry. Upholding the
    dispute would refund the card member twice."""
    case = FakeCase(claim_type="duplicate_charge", amount=54.0)
    evidence = [
        FakeEvidence("email", _mock_parse_evidence(
            "email", "We've confirmed and refunded the duplicate charge as requested. Sorry for the trouble!")),
        FakeEvidence("processor_ledger", {
            "auth_count": 2, "settlement_count": 2, "settlement_amounts": [54.0, 54.0],
            "minutes_between_settlements": 2, "refund_issued": True, "refund_amount": 54.0,
        }, submitted_by="card_member"),
    ]
    signals, winner, cm, m, _ = score_case(case, evidence)
    assert winner == "merchant", names(signals)
    assert "refund_already_issued" in names(signals)
    assert "merchant_admission" not in names(signals), "a remedied admission must not also pay out"


def test_photo_damage_scores_for_card_member():
    case = FakeCase(claim_type="not_as_described")
    photo = FakeEvidence("photo", {"shows_damage": True}, submitted_by="card_member")
    signals, winner, _, _, _ = score_case(case, [photo])
    assert "photo_shows_damage" in names(signals)
    assert winner == "card_member"


def test_damage_evidence_outweighs_its_absence():
    """Deliberate asymmetry: damage in a photo is stronger than its absence in one
    frame the merchant chose to take."""
    assert (SIGNAL_CATALOG["photo_shows_damage"].weight
            > SIGNAL_CATALOG["photo_shows_no_damage"].weight)


def test_stale_in_transit_gives_a_verdict_instead_of_silence():
    from datetime import date, datetime

    case = FakeCase(created_at=datetime(2026, 7, 1))
    signals, winner, _, _, _ = score_case(
        case, [tracking(status="in_transit", last_scan_at="2026-05-20")])
    assert "stale_in_transit" in names(signals)
    assert winner == "card_member"


def test_fresh_in_transit_raises_no_signal():
    from datetime import datetime

    case = FakeCase(created_at=datetime(2026, 7, 1))
    signals, _, cm, m, _ = score_case(
        case, [tracking(status="in_transit", last_scan_at="2026-06-28")])
    assert "stale_in_transit" not in names(signals)


# --- offline parser regressions (D2, D3, D4, D5) ---------------------------

@pytest.mark.parametrize("text,expected", [
    ("We do not offer refunds.", False),
    ("Refunds are never issued.", False),
    ("No returns, no exchanges, no exceptions.", False),
    ("Store credit only; monetary refunds are not available.", False),
    ("All sales are final. No refunds or exchanges under any circumstances.", False),
    ("There is no refund policy ambiguity: customers are ALWAYS refunded in full.", True),
    ("Our return policy allows returns within 30 days for a full refund.", True),
    ("Please contact support.", None),
])
def test_refund_allowed_is_three_state(text, expected):
    assert _mock_parse_evidence("policy_text", text)["refund_allowed"] is expected


@pytest.mark.parametrize("text,expected", [
    ("Sorry, we cannot help you. Our records show the item was delivered correctly.", False),
    ("We are sorry to hear that. However we dispute this claim entirely.", False),
    ("We're sorry for the inconvenience, we'll look into this.", False),
    ("We acknowledge the unit was defective and will refund you.", True),
    ("Our error. We shipped the wrong item.", True),
])
def test_apology_alone_is_not_an_admission(text, expected):
    assert _mock_parse_evidence("email", text)["merchant_admitted_issue"] is expected


def test_photo_parser_exists_offline_and_respects_negation():
    assert _mock_parse_evidence(
        "photo", "Photo shows the shipping box fully intact with no visible damage.")["shows_damage"] is False
    assert _mock_parse_evidence("photo", "The mug arrived shattered.")["shows_damage"] is True


def test_receipt_parser_extracts_date_and_address():
    facts = _mock_parse_evidence("receipt", "Order dated 2026-06-10. Ship to 8 Birch Court, Millbrook.")
    assert facts["order_date"] == "2026-06-10"
    assert facts["shipping_address"] == "8 Birch Court, Millbrook"


# --- signal provenance (used by the human-review banner) -------------------

def test_evidence_derived_signals_carry_their_source_document():
    case = FakeCase()
    ev = tracking(status="not_shipped")
    signals, _, _, _, _ = score_case(case, [ev])
    assert [s.evidence_ids for s in signals if s.signal_name == "not_shipped"] == [[ev.id]]


def test_procedural_signals_carry_no_document():
    case = FakeCase(claim_type="not_as_described")
    signals, _, _, _, _ = score_case(
        case, [FakeEvidence("photo", {"shows_damage": False}, submitted_by="merchant")])
    procedural = [s for s in signals if s.signal_name == "no_card_member_evidence"]
    assert procedural and all(s.evidence_ids == [] for s in procedural)


# --- counterfactual reasoning (Phase 5) ------------------------------------

def test_minimal_flip_set_actually_flips_and_is_minimal():
    signals = [
        Signal("a", "a", 25, "card_member"),
        Signal("b", "b", 20, "card_member"),
        Signal("c", "c", 30, "merchant"),
    ]
    flip = minimal_flip_set(signals, "card_member")
    remaining = sum(s.weight for s in signals if s.favors == "card_member" and s not in flip)
    assert remaining < 30, "removal must change the outcome"
    assert len(flip) == 1, "25 alone is enough; the greedy pick should not take both"


def test_minimal_flip_set_is_empty_when_no_flip_is_possible():
    assert minimal_flip_set([Signal("a", "a", 30, "card_member")], "card_member") == []


def test_counterfactual_never_names_the_winner_as_beneficiary():
    signals = [Signal("a", "delivery proven", 25, "merchant"),
               Signal("b", "address wrong", 10, "card_member")]
    text = counterfactual_statement(signals, "merchant", 10, 25)
    assert "would have gone to the card member" in text


def test_corroborating_documents_are_all_recorded_as_read():
    """A second document raising the same signal must not look unexamined — that made
    the UI claim "no rule reads this" next to "(corroborated by 2 documents)"."""
    case = FakeCase(address="12 Pine Ave, Rivertown")
    a = tracking(status="delivered", delivered_at="99 Pine Ave, Rivertown")
    b = tracking(status="delivered", delivered_at="99 Pine Ave, Rivertown")
    signals, _, _, _, _ = score_case(case, [a, b])
    mismatch = next(s for s in signals if s.signal_name == "address_mismatch")
    assert sorted(mismatch.evidence_ids) == sorted([a.id, b.id])
    assert "corroborated by 2" in mismatch.detail


def test_same_number_same_city_different_street_is_mismatch():
    """Exercises the street-similarity threshold in isolation. Both other guards —
    house number and locality — agree here, so only token overlap can catch it."""
    assert _address_verdict("5 Elm St, Boston", "5 Main St, Boston") == "mismatch"


def test_street_similarity_threshold_is_load_bearing():
    """Guards the constant itself: relaxing it must break something."""
    from app.scoring import _STREET_SIMILARITY

    assert 0 < _STREET_SIMILARITY <= 1.0
    assert _address_verdict("5 Oak Street, Boston", "5 Oak St, Boston") == "match"


def test_a_non_committal_filing_does_not_dodge_the_adverse_inference():
    """The gaming vector: a merchant used to escape the inference by filing anything
    at all. A note that neither supports a finding nor contests one is silence."""
    case = FakeCase(claim_type="not_as_described")
    waffle = FakeEvidence("chat_log", _mock_parse_evidence(
        "chat_log", "We're sorry for the inconvenience, we'll look into this."))
    signals, winner, cm, m, _ = score_case(case, [waffle])
    assert "no_merchant_evidence" in names(signals)
    assert winner == "card_member"


def test_a_reasoned_denial_does_dodge_it():
    """A denial is a position, not silence, even though the scorecard awards it nothing."""
    case = FakeCase(claim_type="not_as_described")
    denial = FakeEvidence("email", _mock_parse_evidence(
        "email", "Our records show the consignment passed inspection before dispatch."))
    signals, winner, _, _, _ = score_case(case, [denial])
    assert "no_merchant_evidence" not in names(signals)
    assert winner == "merchant"
