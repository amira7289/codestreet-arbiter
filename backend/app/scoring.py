import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    signal_name: str
    detail: str
    weight: float
    favors: Optional[str]  # "card_member" | "merchant" | None


def _address_matches(delivered_at, billing_address):
    def tokens(s):
        return set(re.findall(r"[a-z0-9]+", s.lower()))

    a, b = tokens(delivered_at), tokens(billing_address)
    if not a or not b:
        return False
    return len(a & b) >= 2


def score_case(case, evidence_list):
    """Transparent weighted scorecard. Every point is traceable to a named signal
    so the verdict can be explained, not just asserted."""
    signals = []

    for e in evidence_list:
        if e.evidence_type != "tracking_data" or not e.parsed_facts:
            continue
        facts = e.parsed_facts
        status = facts.get("status")
        delivered_at = facts.get("delivered_at")
        signed_by = facts.get("signed_by")

        if status == "delivered" and delivered_at:
            if _address_matches(delivered_at, case.card_member_address):
                signals.append(Signal(
                    "address_match",
                    f"Delivered to {delivered_at}, matches card member's address on file",
                    25, "merchant",
                ))
            else:
                signals.append(Signal(
                    "address_mismatch",
                    f"Delivered to {delivered_at}, does not match address on file ({case.card_member_address})",
                    25, "card_member",
                ))
        elif status == "not_shipped":
            signals.append(Signal(
                "not_shipped", "Carrier tracking shows the item was never shipped", 30, "card_member",
            ))
        elif status == "returned":
            signals.append(Signal(
                "returned_to_sender", "Carrier tracking shows the package was returned to sender", 20, "card_member",
            ))

        if signed_by:
            signals.append(Signal(
                "delivery_confirmation", f"Delivery signed for by {signed_by}", 20, "merchant",
            ))

    for e in evidence_list:
        if e.evidence_type != "policy_text" or not e.parsed_facts:
            continue
        facts = e.parsed_facts
        if case.claim_type != "refund_not_processed":
            continue
        if facts.get("refund_allowed") is False:
            signals.append(Signal(
                "policy_no_refund", "Merchant's stated policy does not allow refunds for this case", 15, "merchant",
            ))
        elif facts.get("refund_allowed") is True:
            signals.append(Signal(
                "policy_allows_refund", "Merchant's own policy allows a refund, and none was processed", 15, "card_member",
            ))

    for e in evidence_list:
        if e.evidence_type not in ("email", "chat_log") or not e.parsed_facts:
            continue
        if e.parsed_facts.get("merchant_admitted_issue"):
            signals.append(Signal(
                "merchant_admission", "Merchant correspondence acknowledges the issue", 20, "card_member",
            ))

    card_member_evidence = [e for e in evidence_list if e.submitted_by == "card_member"]
    merchant_evidence = [e for e in evidence_list if e.submitted_by == "merchant"]
    if not merchant_evidence and card_member_evidence:
        signals.append(Signal(
            "no_merchant_evidence", "Merchant submitted no evidence to support their position", 15, "card_member",
        ))
    # "item not received" is a negative claim — a card member can't produce positive proof
    # that something didn't arrive, so we don't penalize them for having no counter-evidence.
    # Merchants are always expected to be able to prove shipment/delivery/refund.
    if not card_member_evidence and merchant_evidence and case.claim_type != "item_not_received":
        signals.append(Signal(
            "no_card_member_evidence", "Card member submitted no evidence to support their claim", 15, "merchant",
        ))

    card_member_score = sum(s.weight for s in signals if s.favors == "card_member")
    merchant_score = sum(s.weight for s in signals if s.favors == "merchant")
    total = card_member_score + merchant_score

    if total == 0:
        signals.append(Signal(
            "insufficient_evidence", "No conclusive evidence was available from either party", 0, None,
        ))
        return signals, "card_member", 0.0, 0.0, 0.5

    winner = "card_member" if card_member_score >= merchant_score else "merchant"
    confidence = abs(card_member_score - merchant_score) / total
    return signals, winner, card_member_score, merchant_score, confidence
