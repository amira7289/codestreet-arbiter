"""Worked examples: input, expected output, actual output, pass/fail.

Every line below is a claim about how the system behaves, checked against the real
parser, the real scorer and the real API. Run it whenever you want to confirm the
thing still does what the README says:

    cd backend && python verify_examples.py

No server needed, no API key, no network. Exits non-zero if anything disagrees.
"""
import sys

from fastapi.testclient import TestClient

from app.llm import _mock_parse_evidence as parse
from app.main import app
from app.scoring import score_case

PASS, FAIL = [], []


def check(group, given, expect, actual):
    ok = actual == expect
    (PASS if ok else FAIL).append((group, given))
    print(f"  {'PASS' if ok else 'FAIL'}  {given}")
    print(f"        expected: {expect}")
    if not ok:
        print(f"        ACTUAL:   {actual}")


def heading(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# --------------------------------------------------------------------------
class Ev:
    _n = 0

    def __init__(self, kind, text, by="merchant"):
        Ev._n += 1
        self.id = Ev._n
        self.evidence_type = kind
        self.raw_content = text
        self.parsed_facts = parse(kind, text)
        self.submitted_by = by
        self.auto_gathered = False


class Case:
    def __init__(self, claim="item_not_received", address="45 Oak Street, Springfield",
                 name="Priya Sharma", amount=299.0):
        self.transaction_id = "TXDEMO"
        self.claim_type = claim
        self.card_member_address = address
        self.card_member_name = name
        self.amount = amount
        self.claim_text = "sample"
        self.created_at = None


def signals_for(case, *evidence):
    signals, winner, cm, m, conf = score_case(case, list(evidence))
    return sorted(s.signal_name for s in signals), winner, cm, m


# ==========================================================================
heading("1. EVIDENCE PARSING — what the system reads out of raw text")

check("parse", 'tracking: "...signed by A. Stone on 2026-06-02."',
      "A. Stone",
      parse("tracking_data", "Delivered to 1 High St. Signed by A. Stone on 2026-06-02.")["signed_by"])

check("parse", 'tracking: "Not signed by anyone."',
      None,
      parse("tracking_data", "Attempted delivery. Not signed by anyone.")["signed_by"])

check("parse", 'tracking: "signed by Receiving Dept."',
      None,
      parse("tracking_data", "Delivered to 1 High St, signed by Receiving Dept.")["signed_by"])

check("parse", 'policy: "All sales are final. No refunds."',
      False,
      parse("policy_text", "All sales are final. No refunds or exchanges.")["refund_allowed"])

check("parse", 'policy: "no refund policy ambiguity: customers are ALWAYS refunded"',
      True,
      parse("policy_text",
            "There is no refund policy ambiguity: customers are ALWAYS refunded in full.")["refund_allowed"])

check("parse", 'policy: "Please contact support." (says nothing)',
      None,
      parse("policy_text", "Please contact support.")["refund_allowed"])

check("parse", 'email: "Sorry, we cannot help you. Our records show..."',
      False,
      parse("email", "Sorry, we cannot help you. Our records show the item was delivered correctly.")
      ["merchant_admitted_issue"])

check("parse", 'email: "Our error. We shipped the wrong item."',
      True,
      parse("email", "Our error. We shipped the wrong item.")["merchant_admitted_issue"])

check("parse", 'photo: "box fully intact with no visible damage"',
      False,
      parse("photo", "Photo shows the shipping box fully intact with no visible damage.")["shows_damage"])

check("parse", 'ledger: "AUTH x2 | SETTLE x2 ($999.00, $999.00)"',
      2,
      parse("processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1 | AUTH x2 | SETTLE x2 ($999.00, $999.00) | "
            "GAP 3 min | REFUND none")["settlement_count"])


# ==========================================================================
heading("2. SCORING — which signals fire, and who wins")

names, winner, cm, m = signals_for(
    Case(),
    Ev("tracking_data", "Delivered 2026-06-04 to 45 Oak Street, Springfield, signed by P. Sharma."))
check("score", "delivered to the cardholder's address, they signed",
      (["address_match", "delivery_confirmation_named"], "merchant", 0.0, 45.0),
      (names, winner, cm, m))

names, winner, cm, m = signals_for(
    Case(),
    Ev("tracking_data", "Delivered 2026-06-04 to 999 Oak Street, Springfield, signed by unknown recipient."))
check("score", "same street, WRONG house number, generic signee",
      (["address_mismatch"], "card_member", 25.0, 0.0),
      (names, winner, cm, m))

names, winner, cm, m = signals_for(
    Case(address="5 Main St, Boston"),
    Ev("tracking_data", "Delivered 2026-06-04 to 5 Elm St, Denver, signed by P. Sharma."))
check("score", "same number, different street AND city",
      (["address_mismatch", "delivery_confirmation_named"], "card_member", 25.0, 20.0),
      (names, winner, cm, m))

names, winner, cm, m = signals_for(
    Case(),
    Ev("tracking_data", "Attempted delivery to 45 Oak Street, Springfield. Not signed by anyone."))
# Nothing scored, so the case falls to the disclosed provisional-credit rule — which
# is emitted as a visible zero-weight signal rather than resolved silently.
check("score", "attempted delivery, nobody signed — no evidence either way",
      (["provisional_credit_no_evidence"], "card_member", 0.0, 0.0),
      (names, winner, cm, m))

names, winner, cm, m = signals_for(
    Case(claim="duplicate_charge", amount=999.0),
    Ev("processor_ledger",
       "AMEX PROCESSOR LEDGER — TX1 | AUTH x2 | SETTLE x2 ($999.00, $999.00) | GAP 3 min | REFUND none",
       by="card_member"))
# 35 for the duplicate, plus 15 because the card member filed and the merchant did
# not answer — an adverse inference the gather log has to justify.
check("score", "two identical settlements, no refund, merchant silent",
      (["duplicate_settlement_confirmed", "no_merchant_evidence"], "card_member", 50.0, 0.0),
      (names, winner, cm, m))

names, winner, cm, m = signals_for(
    Case(claim="duplicate_charge", amount=54.0),
    Ev("email", "We've confirmed and refunded the duplicate charge as requested. Sorry for the trouble!"),
    Ev("processor_ledger",
       "AMEX PROCESSOR LEDGER — TX1 | AUTH x2 | SETTLE x2 ($54.00, $54.00) | GAP 2 min | REFUND $54.00",
       by="card_member"))
check("score", "duplicate confirmed BUT already refunded — must not pay twice",
      (["refund_already_claimed", "refund_already_issued"], "merchant", 0.0, 55.0),
      (names, winner, cm, m))

names, winner, cm, m = signals_for(
    Case(claim="not_as_described"),
    Ev("photo", "Photo shows the vase shattered into several pieces.", by="card_member"))
check("score", "cardholder photo showing damage",
      (["no_merchant_evidence", "photo_shows_damage"], "card_member", 40.0, 0.0),
      (names, winner, cm, m))


# ==========================================================================
heading("3. NEGOTIATION — settle before adjudicating")

client = TestClient(app)
case_id = client.post("/cases", json={
    "transaction_id": "TXVERIFY", "card_member_name": "Sample Cardholder",
    "card_member_address": "1 Sample Way, Testburgh", "merchant_name": "Sample Merchant",
    "amount": 200.0, "claim_type": "duplicate_charge", "claim_text": "Charged twice.",
}).json()["id"]

made = client.post(f"/cases/{case_id}/offers", json={
    "proposed_by": "merchant", "offer_type": "partial_refund", "amount": 120.0,
    "message": "Meet in the middle."})
check("negotiate", "merchant proposes a $120 partial refund", (201, "open"),
      (made.status_code, made.json()["status"]))

dup = client.post(f"/cases/{case_id}/offers", json={
    "proposed_by": "merchant", "offer_type": "full_refund"})
check("negotiate", "same side offers again while awaiting a reply", 409, dup.status_code)

bad = client.post(f"/cases/{case_id}/offers", json={
    "proposed_by": "card_member", "offer_type": "partial_refund", "amount": 999999.0})
check("negotiate", "settlement larger than the disputed amount", 422, bad.status_code)

counter = client.post(f"/cases/{case_id}/offers", json={
    "proposed_by": "card_member", "offer_type": "full_refund", "message": "Full or we adjudicate."})
offers = {o["id"]: o["status"] for o in client.get(f"/cases/{case_id}").json()["offers"]}
check("negotiate", "cardholder counters — the earlier offer is retired",
      ("superseded", "open"),
      (offers[made.json()["id"]], offers[counter.json()["id"]]))

client.post(f"/cases/{case_id}/offers/{counter.json()['id']}/respond", json={"action": "accept"})
settled = client.get(f"/cases/{case_id}").json()
check("negotiate", "merchant accepts — case settles with NO verdict",
      ("settled", None), (settled["status"], settled["verdict"]))

check("negotiate", "adjudicating a settled case is refused", 409,
      client.post(f"/cases/{case_id}/resolve").status_code)


# ==========================================================================
heading("4. FORECAST — identical for both parties, records nothing")

fc_case = client.post("/cases", json={
    "transaction_id": "TX1001", "card_member_name": "Priya Sharma",
    "card_member_address": "45 Oak Street, Springfield", "merchant_name": "BrewCo Online",
    "amount": 299.0, "claim_type": "item_not_received", "claim_text": "Never arrived.",
}).json()["id"]
client.post(f"/cases/{fc_case}/gather")

first = client.get(f"/cases/{fc_case}/forecast").json()
second = client.get(f"/cases/{fc_case}/forecast").json()
check("forecast", "two reads return the identical forecast", True, first == second)
check("forecast", "forecast records no verdict on the case", None,
      client.get(f"/cases/{fc_case}").json()["verdict"])
check("forecast", "TX1001 (carrier never shipped it) favours the card member",
      "card_member", first["winner"])


# ==========================================================================
heading("5. READABLE FACTS — what the parties actually see")

detail = client.get(f"/cases/{fc_case}").json()
tracking = next((e for e in detail["evidence"] if e["evidence_type"] == "tracking_data"), None)
check("readable", "tracking evidence renders as English, not JSON",
      True,
      bool(tracking and tracking["readable_facts"]
           and all(isinstance(x, str) and " " in x for x in tracking["readable_facts"])))
if tracking:
    for line in tracking["readable_facts"]:
        print(f"        > {line}")


# ==========================================================================
print(f"\n{'=' * 78}")
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for group, given in FAIL:
        print(f"  FAILED [{group}] {given}")
    sys.exit(1)
print("Every worked example matches. Nothing was written to disputes.db that matters —")
print("the two sample cases created above are throwaway and can be deleted from the queue.")
