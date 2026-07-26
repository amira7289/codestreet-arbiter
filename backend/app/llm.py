import json
import os
import re
from datetime import date, datetime
from typing import Dict, List, Optional

_client = None


def _get_client():
    """Lazily construct an Anthropic client. Returns None if no API key is configured,
    which puts the app into offline/mock mode so it still runs for local demos."""
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    import anthropic

    _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0)) if match else {}


PARSE_PROMPTS = {
    "tracking_data": (
        "Extract structured facts from this shipping carrier update. "
        'Return ONLY JSON: {"status": "delivered|in_transit|not_shipped|returned", '
        '"delivered_at": "<address or null>", "signed_by": "<name or null>", '
        '"last_scan_at": "<ISO date or null>"}. '
        "signed_by must be null if the text says nobody signed, or if the signee is a "
        "generic role rather than a person (e.g. 'unknown recipient', 'receiving dept', 'driver')."
    ),
    "policy_text": (
        "Extract the return/refund policy terms from this merchant text. "
        'Return ONLY JSON: {"return_window_days": <int or null>, '
        '"refund_allowed": <true|false|null>}. '
        "Use null for refund_allowed when the text does not clearly state whether refunds are given."
    ),
    "receipt": (
        "Extract facts from this receipt/order confirmation. "
        'Return ONLY JSON: {"order_date": "<ISO date or null>", "shipping_address": "<address or null>"}'
    ),
    "email": (
        "Extract facts from this email correspondence between card member and merchant. "
        'Return ONLY JSON: {"merchant_admitted_issue": <true|false>, '
        '"merchant_denies_claim": <true|false>, "refund_already_claimed": <true|false>, '
        '"summary": "<one line>"}. '
        "merchant_admitted_issue means the merchant accepted fault for a specific problem. "
        "Generic politeness ('sorry to hear that', 'sorry for the trouble') is NOT an admission."
    ),
    "chat_log": (
        "Extract facts from this support chat log. "
        'Return ONLY JSON: {"merchant_admitted_issue": <true|false>, '
        '"merchant_denies_claim": <true|false>, "refund_already_claimed": <true|false>, '
        '"summary": "<one line>"}. '
        "merchant_admitted_issue means the merchant accepted fault for a specific problem. "
        "Generic politeness ('sorry to hear that', 'sorry for the trouble') is NOT an admission."
    ),
    "photo": (
        "Extract facts from this photo description/caption. "
        'Return ONLY JSON: {"shows_damage": <true|false>, "summary": "<one line>"}'
    ),
    "processor_ledger": (
        "Extract the authorisation and settlement facts from this card processor ledger line. "
        'Return ONLY JSON: {"auth_count": <int>, "settlement_count": <int>, '
        '"settlement_amounts": [<float>], "minutes_between_settlements": <int or null>, '
        '"refund_issued": <true|false>, "refund_amount": <float or null>}. '
        "minutes_between_settlements is null unless there are at least two settlements. "
        "refund_amount is null when no refund was posted."
    ),
}


def parse_evidence(evidence_type, raw_content):
    client = _get_client()
    prompt = PARSE_PROMPTS.get(evidence_type, PARSE_PROMPTS["email"])
    if client is None:
        return _mock_parse_evidence(evidence_type, raw_content)

    # The whole call, not just the parse. A 429, a dropped connection or a refusal
    # must degrade to the offline parser rather than 500 the evidence submission —
    # otherwise the app is more fragile with an API key set than without one.
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=300,
            messages=[{"role": "user", "content": f"{prompt}\n\nText:\n{raw_content}"}],
        )
        facts = _extract_json(message.content[0].text)
    except Exception:
        return _mock_parse_evidence(evidence_type, raw_content)

    # An empty dict means the model returned no JSON. Passing it through would drop
    # the evidence silently: the scorer treats empty parsed_facts as nothing to read.
    if not facts:
        return _mock_parse_evidence(evidence_type, raw_content)
    return facts


# ---------------------------------------------------------------------------
# Offline extraction
#
# With no API key set this is the evidence-parsing algorithm, not a stopgap —
# every scorecard signal reads its output. Facts it cannot establish must come
# back as None so the scorer can award nothing, rather than guessing a default
# that silently hands one party points.
# ---------------------------------------------------------------------------

# Roles, not people. A parcel signed for by "Receiving Dept" tells us a building
# took it, not that the card member did — so it must not count as confirmation.
_GENERIC_SIGNEES = {
    "unknown", "unknown recipient", "recipient", "receiving dept", "receiving department",
    "front desk", "reception", "resident", "occupant", "neighbor", "neighbour",
    "driver", "courier", "agent", "n/a", "none", "no one", "anyone", "someone",
}

# Words that end a name: "signed by A. Stone on 2026-06-02" -> "A. Stone"
_NAME_STOPWORDS = {
    "on", "at", "in", "the", "and", "per", "via", "with", "for", "to",
    "after", "before", "upon", "who", "as", "from",
}

_NEGATED_SIGNATURE = re.compile(
    r"\b(?:not|never|no|nobody|unable|refused|declined|without)\b[^.]{0,25}?\bsigned\b",
    re.IGNORECASE,
)
_SIGNEE = re.compile(
    r"signed\s+(?:for\s+)?by\s+([A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*){0,3})",
    re.IGNORECASE,
)

_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), "%Y-%m-%d"),
    (re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4})\b"), "%d %B %Y"),
    (re.compile(r"\b([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})\b"), "%B %d, %Y"),
]


def _parse_date(text: Optional[str]) -> Optional[date]:
    """First parseable date in the text, or None. Never raises — a date we cannot
    read must produce no signal at all rather than a defaulted one."""
    if not text:
        return None
    for pattern, fmt in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(1), fmt).date()
        except ValueError:
            continue
    return None


def _extract_signee(text: str) -> Optional[str]:
    """Name of the person who signed, or None.

    None covers three distinct cases that all mean 'no delivery confirmation':
    the text negates the signature, the signee is a generic role, or no name
    is present. Previously any trailing words after 'signed by' scored, so
    "Not signed by anyone." awarded the merchant a delivery confirmation.
    """
    if _NEGATED_SIGNATURE.search(text):
        return None
    match = _SIGNEE.search(text)
    if not match:
        return None

    tokens: List[str] = []
    for token in match.group(1).split():
        if token.strip(".,").lower() in _NAME_STOPWORDS:
            break
        tokens.append(token)
    if not tokens:
        return None

    name = " ".join(tokens).strip().rstrip(".,;:")
    if not name or name.lower() in _GENERIC_SIGNEES:
        return None
    return name


_TRACKING_STATUS = [
    ("returned", re.compile(r"return(?:ed)?\s+to\s+(?:sender|shipper)|refused\s+by\s+recipient", re.I)),
    ("not_shipped", re.compile(
        r"not\s+shipped|label\s+created|awaiting|pre-?transit|"
        r"has\s+not\s+(?:been\s+)?scanned|no\s+scans", re.I)),
    ("delivered", re.compile(r"\bdelivered\b|delivery\s+confirmed", re.I)),
]
_DELIVERED_AT = re.compile(r"\bto\s+(\d+[^.]*?)(?:,\s*signed|\.|$)", re.I)


def _parse_tracking(text: str) -> Dict:
    status = "in_transit"
    for name, pattern in _TRACKING_STATUS:
        if pattern.search(text):
            status = name
            break

    delivered_at = None
    if status == "delivered":
        match = _DELIVERED_AT.search(text)
        if match:
            delivered_at = match.group(1).strip().rstrip(",")

    scan_date = _parse_date(text)
    return {
        "status": status,
        "delivered_at": delivered_at,
        "signed_by": _extract_signee(text),
        "last_scan_at": scan_date.isoformat() if scan_date else None,
    }


# Checked in order: an explicit denial beats an apparent permission, because
# "no refunds after 30 days" is a denial that also contains a window.
_REFUND_DENIED = [
    # "no refund policy ambiguity" is not a denial — require a real object after it.
    re.compile(r"\bno\s+refunds?\b(?!\s+(?:policy|ambiguity|question|doubt|issue))", re.I),
    re.compile(r"\bno\s+returns?\b(?!\s+(?:policy|ambiguity|question))", re.I),
    re.compile(r"\bno\s+exchanges?\b", re.I),
    re.compile(r"do(?:es)?\s+not\s+(?:offer|provide|issue|give|allow)\s+(?:any\s+)?refunds?", re.I),
    re.compile(r"refunds?\s+(?:are|is)\s+(?:never|not)\b", re.I),
    re.compile(r"\bfinal\s+sale\b|all\s+sales\s+are\s+final", re.I),
    re.compile(r"store\s+credit\s+only", re.I),
    re.compile(r"non-?refundable", re.I),
]
_REFUND_ALLOWED = [
    re.compile(r"\brefunds?\b[^.]{0,45}\b(?:within|allowed|provided|issued|available|granted|accepted)\b", re.I),
    re.compile(r"\b(?:full|partial)\s+refund\b", re.I),
    re.compile(r"allows?\s+returns?|returns?\s+(?:are\s+)?(?:accepted|allowed|permitted)", re.I),
    re.compile(r"\brefunded\s+in\s+full\b|always\s+refunded", re.I),
]
_RETURN_WINDOW = re.compile(r"(\d+)\s*[- ]?\s*day", re.I)


def _parse_policy(text: str) -> Dict:
    """refund_allowed is three-state. None means the policy did not say, and an
    unreadable policy must award nothing to either side."""
    refund_allowed: Optional[bool] = None
    if any(p.search(text) for p in _REFUND_DENIED):
        refund_allowed = False
    elif any(p.search(text) for p in _REFUND_ALLOWED):
        refund_allowed = True

    window = _RETURN_WINDOW.search(text)
    return {
        "return_window_days": int(window.group(1)) if window else None,
        "refund_allowed": refund_allowed,
    }


_SHIPPING_ADDRESS = re.compile(r"ship(?:ped|ping)?\s+to\s+([^.]+)", re.I)


def _parse_receipt(text: str) -> Dict:
    order_date = _parse_date(text)
    address = _SHIPPING_ADDRESS.search(text)
    return {
        "order_date": order_date.isoformat() if order_date else None,
        "shipping_address": address.group(1).strip().rstrip(",") if address else None,
    }


# A denial anywhere in the message overrides an apparent admission: "Sorry, we
# cannot help you — our records show it was delivered" is a refusal, not fault.
_MERCHANT_DENIES = [
    re.compile(r"\brecords\s+show\b|our\s+records\b", re.I),
    re.compile(r"\bwe\s+dispute\b|\bwe\s+deny\b|\bdispute\s+this\s+claim\b", re.I),
    re.compile(r"delivered\s+correctly|was\s+delivered\s+(?:as|correctly)", re.I),
    re.compile(r"cannot\s+help|unable\s+to\s+assist|no\s+evidence", re.I),
    re.compile(r"as\s+described|not\s+eligible", re.I),
]
_MERCHANT_ADMITS = [
    re.compile(r"\bwe\s+(?:acknowledge|admit|confirm|accept)\b", re.I),
    re.compile(r"\bour\s+(?:error|mistake|fault)\b|\bwe\s+(?:were|are)\s+wrong\b", re.I),
    re.compile(r"\bwe\s+(?:shipped|sent)\s+the\s+wrong\b", re.I),
    re.compile(r"\b(?:was|were)\s+(?:defective|damaged|faulty|missing|incorrect)\b", re.I),
    re.compile(r"\bdefective\s+(?:unit|item|product|order)\b", re.I),
    re.compile(r"\bwe\s+(?:failed|forgot|neglected)\b", re.I),
    re.compile(r"\bwill\s+(?:refund|replace|reship|process\s+(?:this|your))\b", re.I),
    re.compile(r"\bwe(?:'ve|\s+have)\s+(?:confirmed|refunded|processed)\b", re.I),
    re.compile(r"\bwe\s+apologi[sz]e\s+for\s+the\s+\w+", re.I),
]
_REFUND_CLAIMED = [
    re.compile(r"\b(?:have|has|already|been)\s+refunded\b", re.I),
    # Allow words between subject and verb: "We've confirmed and refunded the charge".
    # Bounded to one clause so a later sentence's "refunded" is not attributed here.
    re.compile(r"\bwe(?:'ve|\s+have)\b[^.]{0,30}?\brefunded\b", re.I),
    re.compile(r"refund\s+(?:was|has\s+been)\s+(?:issued|processed|completed|sent)", re.I),
]


def _parse_correspondence(text: str) -> Dict:
    """Bare politeness is not an admission of fault. The previous rule treated any
    'sorry' or 'apolog' as a 20-point admission, which both invented admissions in
    denials and missed real ones phrased without an apology."""
    denies = any(p.search(text) for p in _MERCHANT_DENIES)
    admits = (not denies) and any(p.search(text) for p in _MERCHANT_ADMITS)
    return {
        "merchant_admitted_issue": admits,
        "merchant_denies_claim": denies,
        "refund_already_claimed": any(p.search(text) for p in _REFUND_CLAIMED),
        "summary": text.strip()[:120],
    }


# Absence of damage is asserted explicitly and beats a keyword match, so
# "box fully intact with no visible damage" does not read as damage.
_NO_DAMAGE = re.compile(
    r"no\s+(?:visible\s+|apparent\s+|signs?\s+of\s+)?damage|"
    r"\bintact\b|\bundamaged\b|good\s+condition|as\s+described",
    re.I,
)
_DAMAGE = re.compile(
    r"damag|broken|crack|torn|dent|shatter|mold|mould|stain|smash|leak|scratch|defect",
    re.I,
)


def _parse_photo(text: str) -> Dict:
    if _NO_DAMAGE.search(text):
        shows_damage = False
    else:
        shows_damage = bool(_DAMAGE.search(text))
    return {"shows_damage": shows_damage, "summary": text.strip()[:120]}


# Connectors emit one fixed ledger shape, so this reads it exactly rather than
# guessing:
#   AMEX PROCESSOR LEDGER — TX1008 | AUTH x2 | SETTLE x2 ($999.00, $999.00) | GAP 3 min | REFUND none
_LEDGER_AUTH = re.compile(r"AUTH\s*x\s*(\d+)", re.I)
_LEDGER_SETTLE = re.compile(r"SETTLE\s*x\s*(\d+)", re.I)
_LEDGER_SETTLE_AMOUNTS = re.compile(r"SETTLE\s*x\s*\d+\s*\(([^)]*)\)", re.I)
_LEDGER_GAP = re.compile(r"GAP\s+(\d+)\s*min", re.I)
_LEDGER_REFUND = re.compile(r"REFUND\s+(none|\$[\d,]+(?:\.\d+)?)", re.I)
_LEDGER_AMOUNT = re.compile(r"\$([\d,]+(?:\.\d+)?)")


def _money(raw: str) -> float:
    return float(raw.replace("$", "").replace(",", ""))


def _parse_processor_ledger(text: str) -> Dict:
    auth = _LEDGER_AUTH.search(text)
    settle = _LEDGER_SETTLE.search(text)
    amounts_block = _LEDGER_SETTLE_AMOUNTS.search(text)
    gap = _LEDGER_GAP.search(text)
    refund = _LEDGER_REFUND.search(text)

    amounts = [_money(a) for a in _LEDGER_AMOUNT.findall(amounts_block.group(1))] if amounts_block else []
    settlement_count = int(settle.group(1)) if settle else len(amounts)

    refund_amount = None
    if refund and refund.group(1).lower() != "none":
        refund_amount = _money(refund.group(1))

    return {
        "auth_count": int(auth.group(1)) if auth else 0,
        "settlement_count": settlement_count,
        "settlement_amounts": amounts,
        # A gap between settlements is meaningless with fewer than two of them.
        "minutes_between_settlements": int(gap.group(1)) if gap and settlement_count >= 2 else None,
        "refund_issued": refund_amount is not None,
        "refund_amount": refund_amount,
    }


_MOCK_PARSERS = {
    "tracking_data": _parse_tracking,
    "policy_text": _parse_policy,
    "receipt": _parse_receipt,
    "email": _parse_correspondence,
    "chat_log": _parse_correspondence,
    "photo": _parse_photo,
    "processor_ledger": _parse_processor_ledger,
}


def _mock_parse_evidence(evidence_type, raw_content):
    """Deterministic fallback so the app is demoable without an API key.
    Keys returned here must match the shape promised by PARSE_PROMPTS for the
    same evidence type, so the scorer behaves identically on both paths."""
    parser = _MOCK_PARSERS.get(evidence_type, _parse_correspondence)
    return parser(raw_content or "")


def _split_signals(signals, winner):
    """Winning and losing signals, in that order. An arbiter that never mentions the
    losing side's best point does not read as neutral, whatever its reasoning was."""
    winning = [s for s in signals if s.favors == winner]
    losing = [s for s in signals if s.favors and s.favors != winner]
    return winning, sorted(losing, key=lambda s: -s.weight)


def _losing_side_was_read(signals, evidence, winner):
    """Did the losing party's own filings produce any signal at all, in either direction?

    "Nothing on the record" and "everything you filed was read and told against you"
    are completely different things to say to someone who just lost, and only the
    second is true when their documents fired rules for the other side.
    """
    if not evidence:
        return False
    loser = "merchant" if winner == "card_member" else "card_member"
    theirs = {e.id for e in evidence if getattr(e, "submitted_by", None) == loser}
    if not theirs:
        return False
    read = {i for s in signals for i in getattr(s, "evidence_ids", [])}
    return bool(theirs & read)


def generate_explanation(case, signals, winner, confidence, reason_code_label=None, evidence=None):
    client = _get_client()
    winning, losing = _split_signals(signals, winner)
    was_read = _losing_side_was_read(signals, evidence, winner)
    if client is None:
        return _mock_explanation(case, winning, losing, confidence, reason_code_label, was_read)

    signal_lines = "\n".join(
        [f"- [WINNING] {s.signal_name}: {s.detail} (weight {s.weight}, favors {s.favors})" for s in winning]
        + [f"- [LOSING] {s.signal_name}: {s.detail} (weight {s.weight}, favors {s.favors})" for s in losing]
    )
    prompt = (
        "You are a neutral dispute resolution arbiter. Write a 3-4 sentence plain-English "
        "explanation of the verdict, citing ONLY the signals below. Do not invent facts, and "
        "do not restate or alter the verdict itself — it has already been decided.\n"
        "Include exactly one sentence acknowledging the strongest point made by the losing "
        "side and why it was outweighed. If there are no LOSING signals, say plainly that the "
        "losing side put nothing on the record that the scorecard could weigh.\n\n"
        f"Claim: {case.claim_text}\n"
        f"Ruling: {winner}\n"
        + (f"Chargeback reason code: {reason_code_label}\n" if reason_code_label else "")
        + f"Signals:\n{signal_lines}\n"
        f"Confidence: {confidence:.0%}"
    )
    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        return _mock_explanation(case, winning, losing, confidence, reason_code_label)


def _mock_explanation(case, winning, losing, confidence, reason_code_label=None, losing_side_was_read=False):
    """Offline path. Same three-part shape as the live prompt — ruling, strongest
    opposing point, confidence — because this is what actually runs in the demo."""
    if winning:
        ruling = "Ruling based on: " + "; ".join(s.detail for s in winning[:3]) + "."
    else:
        ruling = "No evidence weighed in the successful party's favour; the ruling rests on policy alone."

    if losing:
        top = losing[0]
        counter = (
            " The strongest point on the other side was: {} (+{:.0f}), which was outweighed "
            "by the above."
        ).format(top.detail, top.weight)
    elif losing_side_was_read:
        counter = (
            " Nothing the other side filed weighed in their favour — their submissions "
            "were read, and the facts in them supported this ruling."
        )
    else:
        counter = " The other side put nothing on the record that the scorecard could weigh."

    code = f" Chargeback reason code: {reason_code_label}." if reason_code_label else ""
    return f"{ruling}{counter}{code} Confidence: {confidence:.0%}."
