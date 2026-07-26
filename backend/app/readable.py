"""Plain-English renderings of extracted facts.

`{"shows_damage": false}` is the right shape for a scorer and the wrong shape for
a card member. The whole premise of this system is that both parties can read the
basis of the decision, and a JSON blob is not something a person disputing a charge
should have to parse.

The typed facts are still available underneath — this layer sits on top of them, it
does not replace them. Lives in the backend rather than the UI so it is covered by
the test suite and stays consistent wherever facts are shown.
"""
from typing import Dict, List, Optional

_STATUS_SENTENCE = {
    "delivered": "Carrier records the parcel as delivered.",
    "not_shipped": "Carrier has no record of the parcel ever being shipped.",
    "returned": "Parcel was returned to the sender.",
    "in_transit": "Parcel is still in transit.",
}


def _money(value) -> str:
    try:
        return "${:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return str(value)


def _tracking(f: Dict) -> List[str]:
    out = []
    status = f.get("status")
    if status in _STATUS_SENTENCE:
        out.append(_STATUS_SENTENCE[status])

    if f.get("delivered_at"):
        out.append(f"Delivery address on the carrier record is {f['delivered_at']}.")

    if f.get("signed_by"):
        out.append(f"Signed for by {f['signed_by']}.")
    elif status == "delivered":
        # Deliberately explicit. A missing signature is a finding, not an absence of
        # one — it is the difference between proof of receipt and proof of drop-off.
        out.append("No named signature was captured on delivery.")

    if f.get("last_scan_at"):
        out.append(f"Last carrier scan was {f['last_scan_at']}.")
    return out


def _policy(f: Dict) -> List[str]:
    out = []
    allowed = f.get("refund_allowed")
    if allowed is True:
        out.append("Merchant's published policy does allow a refund here.")
    elif allowed is False:
        out.append("Merchant's published policy rules out a refund.")
    else:
        out.append("Policy text does not say clearly whether a refund applies.")

    window = f.get("return_window_days")
    if window:
        out.append(f"Stated return window is {window} days.")
    return out


def _receipt(f: Dict) -> List[str]:
    out = []
    if f.get("order_date"):
        out.append(f"Order was placed on {f['order_date']}.")
    if f.get("shipping_address"):
        out.append(f"Shipping address on the receipt is {f['shipping_address']}.")
    if not out:
        out.append("No order date or shipping address could be read from this receipt.")
    return out


def _correspondence(f: Dict) -> List[str]:
    out = []
    if f.get("refund_already_claimed"):
        out.append("Merchant states the refund has already been issued.")
    if f.get("merchant_admitted_issue"):
        out.append("Merchant accepts fault for the problem described.")
    if f.get("merchant_denies_claim"):
        out.append("Merchant disputes the claim.")
    if not out:
        out.append("Correspondence neither accepts fault nor disputes the claim.")
    return out


def _photo(f: Dict) -> List[str]:
    shows = f.get("shows_damage")
    if shows is True:
        return ["Photograph shows damage to the goods."]
    if shows is False:
        return ["Photograph shows the goods intact, with no visible damage."]
    return ["Photograph could not be assessed for damage."]


def _ledger(f: Dict) -> List[str]:
    out = []
    auths = f.get("auth_count")
    settlements = f.get("settlement_count")
    amounts = f.get("settlement_amounts") or []

    if settlements:
        if settlements > 1 and len(set(amounts)) == 1 and amounts:
            out.append(
                f"Settlement record shows {settlements} charges of {_money(amounts[0])} "
                "for this transaction.")
        elif settlements > 1:
            out.append(f"Settlement record shows {settlements} separate charges.")
        else:
            amount = _money(amounts[0]) if amounts else "the disputed amount"
            out.append(f"Settlement record shows a single charge of {amount}.")

    if auths and settlements and auths > settlements:
        out.append(
            f"{auths} authorisations were requested but only {settlements} was captured, "
            "so the duplicate never reached the statement.")

    gap = f.get("minutes_between_settlements")
    if gap is not None and settlements and settlements > 1:
        out.append(f"The charges are {gap} minutes apart.")

    if f.get("refund_issued"):
        amount = f.get("refund_amount")
        out.append(
            f"A refund of {_money(amount)} has already been posted."
            if amount is not None else "A refund has already been posted.")
    else:
        out.append("No refund has been posted against this transaction.")
    return out


_RENDERERS = {
    "tracking_data": _tracking,
    "policy_text": _policy,
    "receipt": _receipt,
    "email": _correspondence,
    "chat_log": _correspondence,
    "photo": _photo,
    "processor_ledger": _ledger,
}


def describe(evidence_type: Optional[str], facts: Optional[Dict]) -> List[str]:
    """One readable sentence per fact the parser established. Empty when nothing
    was extracted — silence is more honest than a sentence asserting nothing."""
    if not facts:
        return []
    kind = getattr(evidence_type, "value", evidence_type)
    renderer = _RENDERERS.get(kind)
    if renderer is None:
        return []
    try:
        return [s for s in renderer(facts) if s]
    except Exception:
        # A malformed fact set must not take down the page that displays it.
        return []
