"""Simulated evidence connectors.

The challenge brief opens with "auto-gathers transaction evidence", so this module
stands in for the four systems an issuer would actually call: the carrier, the card
processor's settlement ledger, and the merchant's policy and CRM endpoints.

Two rules hold this layer honest:

* Connectors only *fetch*. They never score and never decide. They hand back raw
  text, which `llm.parse_evidence` turns into typed facts, which the deterministic
  scorecard then weighs. Nothing here may short-circuit that chain.
* A source that has nothing still reports. `status="miss"` is recorded rather than
  dropped, because an adverse inference against a party is only fair when you can
  show you asked them and got nothing back.
"""
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ConnectorResult:
    source: str             # carrier_api | processor_ledger | merchant_policy_api | merchant_crm
    status: str             # hit | miss | skipped | error
    evidence_type: Optional[str]
    submitted_by: Optional[str]
    raw_content: Optional[str]
    latency_ms: int
    summary: str


SOURCE_ROUTING = {
    "item_not_received":    ["carrier_api", "processor_ledger", "merchant_crm"],
    "not_as_described":     ["merchant_policy_api", "merchant_crm", "carrier_api"],
    "duplicate_charge":     ["processor_ledger", "merchant_crm"],
    "refund_not_processed": ["processor_ledger", "merchant_policy_api", "merchant_crm"],
}

# `Evidence.submitted_by` records provenance, and the model only offers two parties.
# The three merchant-side systems are unambiguous. The processor ledger is the
# issuer's own settlement record, pulled on the card member's behalf when they file —
# attributing it to the merchant instead would let the connector layer hand the
# merchant a `no_card_member_evidence` win on every auto-gathered case, which is the
# scorecard being moved by plumbing rather than by evidence.
_SOURCE_PARTY = {
    "carrier_api": "merchant",
    "processor_ledger": "card_member",
    "merchant_policy_api": "merchant",
    "merchant_crm": "merchant",
}

_MISS_SUMMARY = {
    "carrier_api": "Carrier returned no tracking record for this reference.",
    "processor_ledger": "No settlement records matched this transaction reference.",
    "merchant_policy_api": "Merchant has no published returns policy on file.",
    "merchant_crm": "No correspondence on file for this order.",
}

# Plausible round-trip times per system, used only to pick a deterministic value
# inside a believable band. Carriers are slow, ledgers are fast.
_LATENCY_BAND = {
    "carrier_api": (620, 1450),
    "processor_ledger": (180, 540),
    "merchant_policy_api": (140, 420),
    "merchant_crm": (260, 780),
}


def _latency_ms(source: str, transaction_id: str) -> int:
    """Deterministic per (source, transaction_id). `gather()` never sleeps — the
    latency is reported, not spent — so seeding, tests and the eval harness stay
    instant and reproducible. `random` would break reproducibility and Python's
    builtin `hash` is salted per process, hence sha256.
    """
    low, high = _LATENCY_BAND.get(source, (200, 600))
    digest = hashlib.sha256("{}:{}".format(source, transaction_id).encode("utf-8")).digest()
    return low + int.from_bytes(digest[:4], "big") % (high - low + 1)


# Fixtures keyed by transaction_id, then by source. A 3-tuple is a hit
# (evidence_type, raw_content, summary); None is a deliberate miss, spelled out
# rather than omitted so the modelled gaps are reviewable. Every seed case carries
# an entry for each of its routed sources.
#
# Two formatting contracts matter downstream:
#   * processor_ledger lines follow one fixed shape so the offline parser is exact.
#   * carrier and receipt text carry ISO-8601 dates, which `llm._parse_date` reads.
_Fixture = Optional[Tuple[str, str, str]]

_FIXTURES: Dict[str, Dict[str, _Fixture]] = {
    "TX1001": {
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1001: label created 2026-06-01 at Springfield origin depot. "
            "Carrier has not scanned the package since. Status: not shipped.",
            "Label created 2026-06-01, no carrier scans since",
        ),
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1001 | AUTH x1 | SETTLE x1 ($299.00) | GAP n/a | REFUND none",
            "1 settlement of $299.00, no refund posted",
        ),
        "merchant_crm": None,
    },
    "TX1002": {
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1002: delivered 2026-06-04 to 12 Pine Ave, Rivertown, signed by M. Torres.",
            "Delivered 2026-06-04, signed by M. Torres",
        ),
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1002 | AUTH x1 | SETTLE x1 ($150.00) | GAP n/a | REFUND none",
            "1 settlement of $150.00, no refund posted",
        ),
        "merchant_crm": (
            "email",
            "Merchant CRM ticket #4471: our records show the parcel was delivered and "
            "signed for on 2026-06-04. We dispute this claim.",
            "1 merchant reply on file, disputing the claim",
        ),
    },
    "TX1003": {
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1003: delivered 2026-06-02 to 200 Birch Court, Millbrook, "
            "signed by unknown recipient.",
            "Delivered 2026-06-02 to 200 Birch Court, Millbrook",
        ),
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1003 | AUTH x1 | SETTLE x1 ($89.50) | GAP n/a | REFUND none",
            "1 settlement of $89.50, no refund posted",
        ),
        "merchant_crm": None,
    },
    "TX1004": {
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1004 | AUTH x1 | SETTLE x1 ($499.00) | GAP n/a | REFUND none",
            "1 settlement of $499.00, no refund posted",
        ),
        "merchant_policy_api": (
            "policy_text",
            "TechDeals Inc return policy v4.2: returns are accepted within 30 days of "
            "delivery for a full refund.",
            "30-day return window, refunds allowed",
        ),
        "merchant_crm": None,
    },
    "TX1005": {
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1005 | AUTH x1 | SETTLE x1 ($60.00) | GAP n/a | REFUND none",
            "1 settlement of $60.00, no refund posted",
        ),
        "merchant_policy_api": (
            "policy_text",
            "QuickMart terms of sale: all sales are final. No refunds or exchanges under "
            "any circumstances.",
            "Final sale, no refunds offered",
        ),
        "merchant_crm": (
            "chat_log",
            "Merchant CRM chat 2026-06-06 — we dispute this claim; the purchase was "
            "collected in store and is not eligible for return.",
            "1 merchant chat on file, disputing the claim",
        ),
    },
    "TX1006": {
        "merchant_policy_api": (
            "policy_text",
            "FreshBox Grocery freshness policy: perishable orders are refunded in full "
            "when reported within 3 days of delivery.",
            "3-day freshness window, refunds allowed",
        ),
        "merchant_crm": (
            "chat_log",
            "Merchant CRM chat 2026-06-12 — Customer support: we're sorry for the "
            "inconvenience, we'll look into this.",
            "1 merchant chat on file, no position stated",
        ),
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1006: delivered 2026-06-11, left at front door. "
            "No signature required for perishable orders.",
            "Delivered 2026-06-11, contactless drop",
        ),
    },
    "TX1007": {
        "merchant_policy_api": (
            "policy_text",
            "HomeGoods Direct returns policy: returns are accepted within 14 days of "
            "delivery in original packaging.",
            "14-day return window, refunds allowed",
        ),
        "merchant_crm": None,
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1007: delivered 2026-06-08 to 21 Chestnut Blvd, Oakdale. "
            "No signature captured (contactless delivery).",
            "Delivered 2026-06-08, no signature captured",
        ),
    },
    "TX1008": {
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1008 | AUTH x2 | SETTLE x2 ($999.00, $999.00) | "
            "GAP 3 min | REFUND none",
            "2 settlements of $999.00 found, 3 min apart",
        ),
        "merchant_crm": None,
    },
    "TX1009": {
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1009: delivered 2026-06-05 to 900 Industrial Pkwy, "
            "Warehouse District, signed by Receiving Dept.",
            "Delivered 2026-06-05 to 900 Industrial Pkwy",
        ),
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1009 | AUTH x1 | SETTLE x1 ($340.00) | GAP n/a | REFUND none",
            "1 settlement of $340.00, no refund posted",
        ),
        "merchant_crm": (
            "email",
            "Merchant CRM ticket #8812: our records show the consignment was released to "
            "the address supplied at checkout.",
            "1 merchant reply on file, disputing the claim",
        ),
    },
    "TX1010": {
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1010: package scanned at regional facility 2026-05-28, "
            "in transit to destination. No further scans recorded.",
            "Last scan 2026-05-28, still in transit",
        ),
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1010 | AUTH x1 | SETTLE x1 ($25.00) | GAP n/a | REFUND none",
            "1 settlement of $25.00, no refund posted",
        ),
        "merchant_crm": None,
    },
    "TX1011": {
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1011 | AUTH x1 | SETTLE x1 ($175.00) | GAP n/a | REFUND none",
            "1 settlement of $175.00, no refund posted",
        ),
        "merchant_policy_api": (
            "policy_text",
            "GourmetKitchen returns policy: refunds are provided within 14 days for "
            "defective items.",
            "14-day return window, refunds allowed",
        ),
        "merchant_crm": (
            "chat_log",
            "Merchant CRM chat 2026-06-07 — we apologize for the defective unit and will "
            "process this for you.",
            "1 merchant chat on file, acknowledging a defect",
        ),
    },
    "TX1012": {
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1012: delivery attempted 2026-06-03, no answer at address. "
            "Package returned to sender 2026-06-09.",
            "Delivery failed 2026-06-03, returned to sender",
        ),
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1012 | AUTH x1 | SETTLE x1 ($210.00) | GAP n/a | REFUND none",
            "1 settlement of $210.00, no refund posted",
        ),
        "merchant_crm": None,
    },
    "TX1013": {
        "merchant_policy_api": (
            "policy_text",
            "GlowBeauty returns policy: items may be returned within 30 days of delivery "
            "for a full refund if damaged in transit.",
            "30-day return window, refunds allowed",
        ),
        "merchant_crm": (
            "email",
            "Merchant CRM ticket #2290: our records show the item was dispatched in sealed "
            "packaging and arrived as described.",
            "1 merchant reply on file, disputing the claim",
        ),
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1013: delivered 2026-06-09 to 88 Redwood Ter, Ashford, "
            "signed by S. Vance.",
            "Delivered 2026-06-09, signed by S. Vance",
        ),
    },
    "TX1014": {
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1014 | AUTH x2 | SETTLE x2 ($54.00, $54.00) | "
            "GAP 2 min | REFUND $54.00",
            "2 settlements of $54.00 found, 2 min apart, $54.00 refunded",
        ),
        "merchant_crm": (
            "email",
            "Merchant CRM email thread: we've confirmed and refunded the duplicate charge "
            "as requested. Sorry for the trouble!",
            "1 merchant reply on file, refund confirmed",
        ),
    },
    "TX1015": {
        "carrier_api": (
            "tracking_data",
            "CARRIER TRACKING TX1015: delivered 2026-06-14 to 3 Hemlock Row, Bayview, "
            "signed by A. Stone.",
            "Delivered 2026-06-14, signed by A. Stone",
        ),
        "processor_ledger": (
            "processor_ledger",
            "AMEX PROCESSOR LEDGER — TX1015 | AUTH x1 | SETTLE x1 ($132.00) | GAP n/a | REFUND none",
            "1 settlement of $132.00, no refund posted",
        ),
        "merchant_crm": None,
    },
}


def applicable_sources(claim_type) -> List[str]:
    """Sources worth querying for this claim type. Accepts the ClaimType enum or its
    value, since the ORM hands back the former and the seed spec the latter."""
    key = getattr(claim_type, "value", claim_type)
    return list(SOURCE_ROUTING.get(key, []))


# ---------------------------------------------------------------------------
# Synthesis for transactions with no hand-written fixture.
#
# Hand-authoring a fixture per case does not scale, and it left a real hole: a
# dispute filed live during a demo matched nothing and gathered nothing, so the
# headline feature did nothing on the one case an observer creates themselves.
#
# Everything below is derived from sha256(transaction_id), so a given transaction
# always produces the same evidence — reproducible for tests and stable across a
# reseed — while still varying across the portfolio.
# ---------------------------------------------------------------------------

def _roll(transaction_id: str, salt: str, ceiling: int) -> int:
    digest = hashlib.sha256("{}|{}".format(transaction_id, salt).encode("utf-8")).digest()
    return int.from_bytes(digest[4:8], "big") % ceiling


def _wrong_address(address: str, transaction_id: str) -> str:
    """Same street, different building — the shape that actually shows up in real
    misdeliveries, and the one a naive address matcher gets wrong."""
    parts = address.split(" ", 1)
    tail = parts[1] if len(parts) > 1 else address
    return "{} {}".format(100 + _roll(transaction_id, "addr", 800), tail)


def _surname(name: str) -> str:
    bits = [b for b in (name or "").split() if len(b) > 1]
    return bits[-1] if bits else "Recipient"


def _initialled(name: str) -> str:
    bits = [b for b in (name or "").split() if b]
    return "{}. {}".format(bits[0][0], bits[-1]) if len(bits) > 1 else (bits[0] if bits else "Recipient")


def _synth_carrier(case) -> _Fixture:
    tx = case.transaction_id
    outcome = _roll(tx, "carrier", 100)
    day = 1 + _roll(tx, "day", 27)
    date = "2026-06-{:02d}".format(day)

    if outcome < 22:
        return ("tracking_data",
                "CARRIER TRACKING {}: label created {}. Carrier has not scanned the package since. "
                "Status: not shipped.".format(tx, date),
                "Label created {}, no carrier scans since".format(date))
    if outcome < 34:
        return ("tracking_data",
                "CARRIER TRACKING {}: delivery attempted {}, no answer at address. "
                "Package returned to sender.".format(tx, date),
                "Delivery failed {}, returned to sender".format(date))
    if outcome < 46:
        return ("tracking_data",
                "CARRIER TRACKING {}: package scanned at regional facility {}, in transit to "
                "destination. No further scans recorded.".format(tx, date),
                "Last scan {}, still in transit".format(date))
    if outcome < 62:
        return ("tracking_data",
                "CARRIER TRACKING {}: delivered {} to {}, signed by unknown recipient.".format(
                    tx, date, _wrong_address(case.card_member_address, tx)),
                "Delivered {} to a different address".format(date))
    if outcome < 74:
        return ("tracking_data",
                "CARRIER TRACKING {}: delivered {} to {}. No signature captured "
                "(contactless delivery).".format(tx, date, case.card_member_address),
                "Delivered {}, no signature captured".format(date))
    return ("tracking_data",
            "CARRIER TRACKING {}: delivered {} to {}, signed by {}.".format(
                tx, date, case.card_member_address, _initialled(case.card_member_name)),
            "Delivered {}, signed by {}".format(date, _initialled(case.card_member_name)))


def _synth_ledger(case) -> _Fixture:
    tx = case.transaction_id
    amount = float(case.amount)
    claim = getattr(case.claim_type, "value", case.claim_type)
    outcome = _roll(tx, "ledger", 100)

    if claim == "duplicate_charge":
        if outcome < 55:
            gap = 2 + _roll(tx, "gap", 8)
            return ("processor_ledger",
                    "AMEX PROCESSOR LEDGER — {} | AUTH x2 | SETTLE x2 (${:.2f}, ${:.2f}) | "
                    "GAP {} min | REFUND none".format(tx, amount, amount, gap),
                    "2 settlements of ${:.2f}, {} min apart".format(amount, gap))
        if outcome < 78:
            return ("processor_ledger",
                    "AMEX PROCESSOR LEDGER — {} | AUTH x2 | SETTLE x2 (${:.2f}, ${:.2f}) | "
                    "GAP 3 min | REFUND ${:.2f}".format(tx, amount, amount, amount),
                    "Duplicate found and already refunded")
        return ("processor_ledger",
                "AMEX PROCESSOR LEDGER — {} | AUTH x2 | SETTLE x1 (${:.2f}) | GAP n/a | "
                "REFUND none".format(tx, amount),
                "2 authorisations, only 1 captured")

    if claim == "refund_not_processed" and outcome < 30:
        return ("processor_ledger",
                "AMEX PROCESSOR LEDGER — {} | AUTH x1 | SETTLE x1 (${:.2f}) | GAP n/a | "
                "REFUND ${:.2f}".format(tx, amount, amount),
                "Refund of ${:.2f} already posted".format(amount))

    return ("processor_ledger",
            "AMEX PROCESSOR LEDGER — {} | AUTH x1 | SETTLE x1 (${:.2f}) | GAP n/a | "
            "REFUND none".format(tx, amount),
            "1 settlement of ${:.2f}, no refund posted".format(amount))


def _synth_policy(case) -> _Fixture:
    tx = case.transaction_id
    outcome = _roll(tx, "policy", 100)
    if outcome < 30:
        return ("policy_text",
                "{} returns policy: all sales are final. No refunds or exchanges.".format(case.merchant_name),
                "Final sale, no refunds")
    window = (14, 30, 60)[_roll(tx, "window", 3)]
    return ("policy_text",
            "{} returns policy: items may be returned within {} days of delivery for a "
            "full refund.".format(case.merchant_name, window),
            "{}-day return window, refunds allowed".format(window))


def _synth_crm(case) -> _Fixture:
    tx = case.transaction_id
    outcome = _roll(tx, "crm", 100)
    if outcome < 30:
        return None
    if outcome < 50:
        return ("email",
                "Merchant CRM ticket: our records show the order was fulfilled as described "
                "and dispatched to the address supplied at checkout.",
                "1 merchant reply on file, disputing the claim")
    if outcome < 68:
        return ("email",
                "Merchant CRM ticket: we acknowledge the item was defective and will arrange "
                "a resolution for {}.".format(_surname(case.card_member_name)),
                "1 merchant reply on file, acknowledging a defect")
    if outcome < 80:
        return ("chat_log",
                "Merchant CRM chat: we're sorry for the inconvenience, we'll look into this "
                "and come back to you.",
                "1 merchant chat on file, no position taken")
    return ("email",
            "Merchant CRM ticket: this charge was refunded in full on our side; please allow "
            "a few days for it to appear.",
            "1 merchant reply on file, refund claimed")


_SYNTHESISERS = {
    "carrier_api": _synth_carrier,
    "processor_ledger": _synth_ledger,
    "merchant_policy_api": _synth_policy,
    "merchant_crm": _synth_crm,
}


def _fixture_for(case, source: str) -> _Fixture:
    """Hand-written fixture when one exists, otherwise a deterministic synthetic one.
    Explicit `None` in _FIXTURES is a modelled miss and is honoured as such."""
    hand = _FIXTURES.get(case.transaction_id)
    if hand is not None and source in hand:
        return hand[source]
    synth = _SYNTHESISERS.get(source)
    return synth(case) if synth else None


def gather(case) -> List[ConnectorResult]:
    """Query every routed source for this case. Never sleeps, never raises, never
    scores. Sources with no hand-written fixture fall back to deterministic synthesis,
    so a dispute filed live during a demo gathers real evidence rather than nothing.
    """
    results: List[ConnectorResult] = []

    for source in applicable_sources(case.claim_type):
        latency = _latency_ms(source, case.transaction_id)
        fixture = _fixture_for(case, source)
        if fixture is None:
            results.append(ConnectorResult(
                source=source,
                status="miss",
                evidence_type=None,
                submitted_by=None,
                raw_content=None,
                latency_ms=latency,
                summary=_MISS_SUMMARY[source],
            ))
            continue

        evidence_type, raw_content, summary = fixture
        results.append(ConnectorResult(
            source=source,
            status="hit",
            evidence_type=evidence_type,
            submitted_by=_SOURCE_PARTY[source],
            raw_content=raw_content,
            latency_ms=latency,
            summary=summary,
        ))

    return results
