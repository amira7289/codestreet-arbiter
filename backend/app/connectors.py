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


def gather(case) -> List[ConnectorResult]:
    """Query every routed source for this case. Never sleeps, never raises, never
    scores. A transaction with no fixture misses on every source, which is the right
    answer for a case filed during the demo: the systems genuinely hold nothing on it.
    """
    fixtures = _FIXTURES.get(case.transaction_id, {})
    results: List[ConnectorResult] = []

    for source in applicable_sources(case.claim_type):
        latency = _latency_ms(source, case.transaction_id)
        fixture = fixtures.get(source)
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
