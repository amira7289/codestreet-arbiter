"""Fairness audit.

Two runnable artifacts rather than a claim in a slide:

1. A catalog asymmetry audit. Every signal that favours one party is paired with its
   opposite. Symmetric pairs must stay symmetric; asymmetric ones must appear in
   ASYMMETRY_ALLOWLIST with a stated reason and an exact delta, so an intentional
   imbalance is documented in code and an accidental one fails the build.

2. A party-swap test. Construct identical cases differing only in which side the
   evidence favours, and assert the magnitudes mirror.

The project's fairness position is NOT that the scorecard is unbiased. It is that
every point of directional bias is traceable to a rule stated out loud.
"""
import pytest

from app.scoring import SIGNAL_CATALOG, score_case

from .test_scoring import FakeCase, FakeEvidence, names, tracking

# (card_member_signal, merchant_signal)
OPPOSING_PAIRS = [
    ("address_mismatch", "address_match"),
    ("policy_allows_refund", "policy_no_refund"),
    ("within_return_window", "outside_return_window"),
    ("photo_shows_damage", "photo_shows_no_damage"),
    ("no_refund_in_ledger", "refund_posted_in_ledger"),
    ("duplicate_settlement_confirmed", "single_settlement_only"),
    ("no_merchant_evidence", "no_card_member_evidence"),
]

# pair -> (expected card_member weight − merchant weight, documented reason)
ASYMMETRY_ALLOWLIST = {
    ("photo_shows_damage", "photo_shows_no_damage"): (
        10,
        "Damage visible in a photograph is stronger evidence than its absence in one "
        "frame the merchant chose to take and chose to submit.",
    ),
    ("no_refund_in_ledger", "refund_posted_in_ledger"): (
        -5,
        "A posted refund is a positive fact in the settlement record. Its absence is "
        "consistent with a refund that was promised and never actioned, which is weaker.",
    ),
    ("duplicate_settlement_confirmed", "single_settlement_only"): (
        5,
        "Two captured settlements is direct proof of the disputed harm. One settlement "
        "against two authorisations merely shows the duplicate was never captured.",
    ),
    ("no_merchant_evidence", "no_card_member_evidence"): (
        5,
        "Merchants are institutions with records systems and can always evidence "
        "shipment, delivery or refund. Card members often cannot prove a negative, and "
        "the system now gathers on their behalf, so their silence says less.",
    ),
}

# Signals with no opposite, and why.
UNPAIRED = {
    "not_shipped": "no merchant-side counterpart: proof of shipment is address_match",
    "returned_to_sender": "no counterpart; goods physically went back",
    "stale_in_transit": "no counterpart; a fresh scan simply raises nothing",
    "delivery_confirmation_named": "graded against delivery_confirmation_thirdparty, not a party opposite",
    "delivery_confirmation_thirdparty": "the weaker grade of delivery_confirmation_named",
    "merchant_admission": "only a merchant can admit fault",
    "refund_already_claimed": "only a merchant can have already refunded",
    "refund_already_issued": "ledger proof of the same; only a merchant can have refunded",
    "settlements_far_apart": "an exculpatory reading of the ledger with no inverse",
    "provisional_credit_no_evidence": "disclosed policy, zero weight",
    "tie_break_provisional_credit": "disclosed policy, zero weight",
}

PROCEDURAL = {"no_merchant_evidence", "no_card_member_evidence"}

# Evidentiary signals that deliberately sit BELOW the procedural weights. Surfaced by
# the audit rather than hidden: both are downgraded or corroborating readings, not
# primary findings, so an adverse inference from silence legitimately outranks them.
WEAK_EVIDENTIARY = {
    "delivery_confirmation_thirdparty": (
        "the downgraded form of delivery_confirmation_named — somebody signed, but not "
        "the card member, which is barely evidence of receipt by the right person"),
    "settlements_far_apart": (
        "corroborating context for a duplicate-charge reading, not proof of anything "
        "on its own"),
}


def test_every_signal_is_paired_or_explicitly_unpaired():
    """No signal may quietly exist outside the audit."""
    paired = {name for pair in OPPOSING_PAIRS for name in pair}
    for name in SIGNAL_CATALOG:
        assert name in paired or name in UNPAIRED, (
            f"{name} is neither paired nor documented as unpaired — add it to "
            "OPPOSING_PAIRS or UNPAIRED with a reason")


@pytest.mark.parametrize("cm_name,merchant_name", OPPOSING_PAIRS)
def test_pair_asymmetry_is_zero_or_documented(cm_name, merchant_name):
    cm = SIGNAL_CATALOG[cm_name]
    merchant = SIGNAL_CATALOG[merchant_name]
    assert cm.favors == "card_member" and merchant.favors == "merchant"

    delta = cm.weight - merchant.weight
    allowed = ASYMMETRY_ALLOWLIST.get((cm_name, merchant_name))

    if allowed is None:
        assert delta == 0, (
            f"{cm_name} ({cm.weight}) vs {merchant_name} ({merchant.weight}) is asymmetric "
            "but undocumented. Either equalise the weights or add an entry to "
            "ASYMMETRY_ALLOWLIST stating why the imbalance is justified.")
    else:
        expected, reason = allowed
        assert delta == expected, (
            f"{cm_name} vs {merchant_name} delta changed from {expected} to {delta}. "
            f"The documented justification was: {reason} — restate it or restore the weights.")


def test_no_procedural_signal_outweighs_a_primary_evidentiary_one():
    """Silence must never beat a primary finding. Once the system auto-gathers on both
    parties' behalf, an adverse inference from a missing filing is near the bottom of
    the card — above only the downgraded and corroborating readings in WEAK_EVIDENTIARY."""
    primary = {n: s for n, s in SIGNAL_CATALOG.items()
               if s.favors and s.weight > 0 and n not in PROCEDURAL and n not in WEAK_EVIDENTIARY}
    heaviest_procedural = max(SIGNAL_CATALOG[n].weight for n in PROCEDURAL)
    lightest_primary = min(s.weight for s in primary.values())
    assert heaviest_procedural <= lightest_primary, (
        f"a procedural signal ({heaviest_procedural}) outweighs a primary evidentiary "
        f"one ({lightest_primary}) — silence is beating evidence")


def test_weak_evidentiary_exceptions_are_exactly_as_documented():
    """The set of evidentiary signals allowed to sit below procedural weight is closed.
    A new signal that slips under the procedural bar has to be justified here first."""
    heaviest_procedural = max(SIGNAL_CATALOG[n].weight for n in PROCEDURAL)
    actual = {n for n, s in SIGNAL_CATALOG.items()
              if s.favors and 0 < s.weight < heaviest_procedural and n not in PROCEDURAL}
    assert actual == set(WEAK_EVIDENTIARY), (
        f"signals below the procedural bar changed: {actual ^ set(WEAK_EVIDENTIARY)}. "
        "Document the reason in WEAK_EVIDENTIARY or raise the weight.")


def test_only_zero_weight_signals_encode_the_provisional_credit_policy():
    """The pro-card-member default must be disclosed, never smuggled into a weight."""
    for name in ("provisional_credit_no_evidence", "tie_break_provisional_credit"):
        spec = SIGNAL_CATALOG[name]
        assert spec.weight == 0, f"{name} must not move the score, only disclose the rule"
        assert spec.favors is None


def test_party_swap_address_signals_mirror():
    """Same document, mirrored outcome: the magnitude must not depend on who benefits."""
    matching = score_case(
        FakeCase(address="12 Pine Ave, Rivertown"),
        [tracking(status="delivered", delivered_at="12 Pine Ave, Rivertown")])
    differing = score_case(
        FakeCase(address="12 Pine Ave, Rivertown"),
        [tracking(status="delivered", delivered_at="99 Pine Ave, Rivertown")])

    assert matching[1] == "merchant" and differing[1] == "card_member"
    assert matching[3] == differing[2], "a match and a mismatch must be worth the same"


def test_party_swap_photo_reflects_only_the_documented_asymmetry():
    damage = score_case(
        FakeCase(claim_type="not_as_described"),
        [FakeEvidence("photo", {"shows_damage": True}, submitted_by="card_member")])
    intact = score_case(
        FakeCase(claim_type="not_as_described"),
        [FakeEvidence("photo", {"shows_damage": False}, submitted_by="merchant")])

    expected, _ = ASYMMETRY_ALLOWLIST[("photo_shows_damage", "photo_shows_no_damage")]
    # intact[3] also carries no_card_member_evidence, so compare the photo signals alone.
    damage_pts = SIGNAL_CATALOG["photo_shows_damage"].weight
    intact_pts = SIGNAL_CATALOG["photo_shows_no_damage"].weight
    assert damage_pts - intact_pts == expected
    assert "photo_shows_damage" in names(damage[0])
    assert "photo_shows_no_damage" in names(intact[0])


def test_a_party_that_files_nothing_is_never_penalised_on_a_negative_claim():
    """A card member cannot prove a parcel did not arrive, so item_not_received must
    never raise the no-evidence penalty against them."""
    signals, _, _, _, _ = score_case(
        FakeCase(claim_type="item_not_received"),
        [tracking(status="delivered", delivered_at="45 Oak Street, Springfield")])
    assert "no_card_member_evidence" not in names(signals)


def test_catalog_totals_are_reported_not_hidden():
    """Not an assertion about balance — a printout, so the imbalance is visible in CI
    output rather than discovered by a judge."""
    cm = sum(s.weight for s in SIGNAL_CATALOG.values() if s.favors == "card_member")
    merchant = sum(s.weight for s in SIGNAL_CATALOG.values() if s.favors == "merchant")
    print(f"\ncatalog totals — card member: {cm} pts, merchant: {merchant} pts, "
          f"delta: {cm - merchant:+.0f}")
    assert cm > 0 and merchant > 0
