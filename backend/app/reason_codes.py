"""Amex chargeback reason codes.

Verified against published Amex reason-code references (Kount, Chargeflow,
Chargebacks911, Chargeback Gurus) — C = Card Member dispute, P = processing error.
Only codes this system can actually derive are listed; an unverified code is worse
than no code, because the deck cites the official guide.
"""
from typing import Dict, Optional, Tuple

# code -> (official label, claim_type it is the default for)
REASON_CODES: Dict[str, Tuple[str, str]] = {
    "C02": ("Credit Not Processed", "refund_not_processed"),
    "C08": ("Goods/Services Not Received or Only Partially Received", "item_not_received"),
    "C31": ("Goods/Services Not As Described", "not_as_described"),
    "C32": ("Goods/Services Damaged or Defective", "not_as_described"),
    "P08": ("Duplicate Charge", "duplicate_charge"),
}

_DEFAULT_BY_CLAIM = {
    "refund_not_processed": "C02",
    "item_not_received": "C08",
    "not_as_described": "C31",
    "duplicate_charge": "P08",
}

# A fired signal can refine the default, but only the specific code it refines:
# physical damage turns the generic "not as described" C31 into C32. Keyed by the
# code being refined so a future rule emitting the same signal on, say, a
# refund_not_processed case cannot silently discard C02.
_REFINEMENTS = {
    ("C31", "photo_shows_damage"): "C32",
}


def derive_reason_code(case, signals) -> Tuple[Optional[str], Optional[str]]:
    """Deterministic: the claim type picks the default, a fired signal may refine it.
    Returns (code, label), or (None, None) for a claim type we have no verified code for."""
    code = _DEFAULT_BY_CLAIM.get(getattr(case.claim_type, "value", case.claim_type))
    if code is None:
        return None, None

    fired = {s.signal_name for s in signals}
    for (base, signal_name), refined in _REFINEMENTS.items():
        if code == base and signal_name in fired:
            code = refined
            break

    return code, REASON_CODES[code][0]
