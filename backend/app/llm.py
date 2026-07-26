import json
import os
import re

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
        '"delivered_at": "<address or null>", "signed_by": "<name or null>"}'
    ),
    "policy_text": (
        "Extract the return/refund policy terms from this merchant text. "
        'Return ONLY JSON: {"return_window_days": <int or null>, "refund_allowed": <true|false>}'
    ),
    "receipt": (
        "Extract facts from this receipt/order confirmation. "
        'Return ONLY JSON: {"order_date": "<date or null>", "shipping_address": "<address or null>"}'
    ),
    "email": (
        "Extract facts from this email correspondence between card member and merchant. "
        'Return ONLY JSON: {"merchant_admitted_issue": <true|false>, "summary": "<one line>"}'
    ),
    "chat_log": (
        "Extract facts from this support chat log. "
        'Return ONLY JSON: {"merchant_admitted_issue": <true|false>, "summary": "<one line>"}'
    ),
    "photo": (
        "Extract facts from this photo description/caption. "
        'Return ONLY JSON: {"shows_damage": <true|false>, "summary": "<one line>"}'
    ),
}


def parse_evidence(evidence_type, raw_content):
    client = _get_client()
    prompt = PARSE_PROMPTS.get(evidence_type, PARSE_PROMPTS["email"])
    if client is None:
        return _mock_parse_evidence(evidence_type, raw_content)

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": f"{prompt}\n\nText:\n{raw_content}"}],
    )
    try:
        return _extract_json(message.content[0].text)
    except (ValueError, IndexError, AttributeError):
        return _mock_parse_evidence(evidence_type, raw_content)


def _mock_parse_evidence(evidence_type, raw_content):
    """Deterministic keyword-based fallback so the app is demoable without an API key."""
    lower = raw_content.lower()
    if evidence_type == "tracking_data":
        if "delivered" in lower:
            status = "delivered"
        elif "returned" in lower:
            status = "returned"
        elif "not shipped" in lower or "label created" in lower or "awaiting" in lower:
            status = "not_shipped"
        else:
            status = "in_transit"
        signed_match = re.search(r"signed by ([a-z .]+?)\.?$", lower)
        addr_match = re.search(r"to (\d+[a-z0-9 ,]+?)(?:,?\s+signed|\.|$)", lower)
        return {
            "status": status,
            "delivered_at": addr_match.group(1).strip().title() if addr_match else None,
            "signed_by": signed_match.group(1).strip().title() if signed_match else None,
        }
    if evidence_type == "policy_text":
        days_match = re.search(r"(\d+)\s*day", lower)
        return {
            "return_window_days": int(days_match.group(1)) if days_match else None,
            "refund_allowed": "no refund" not in lower,
        }
    if evidence_type == "receipt":
        return {"order_date": None, "shipping_address": None}
    return {"merchant_admitted_issue": "sorry" in lower or "apolog" in lower, "summary": raw_content[:80]}


def generate_explanation(case, winning_signals, confidence):
    client = _get_client()
    if client is None:
        return _mock_explanation(case, winning_signals, confidence)

    signal_lines = "\n".join(
        f"- {s.signal_name}: {s.detail} (weight {s.weight}, favors {s.favors})" for s in winning_signals
    )
    prompt = (
        "You are a neutral dispute resolution arbiter. Write a 2-3 sentence plain-English "
        "explanation of the verdict, citing ONLY the signals below. Do not invent facts.\n\n"
        f"Claim: {case.claim_text}\n"
        f"Winning signals:\n{signal_lines}\n"
        f"Confidence: {confidence:.0%}"
    )
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _mock_explanation(case, winning_signals, confidence):
    if not winning_signals:
        return f"Ruling based on limited evidence. Confidence: {confidence:.0%}."
    reasons = "; ".join(f"{s.signal_name} — {s.detail}" for s in winning_signals[:3])
    return f"Ruling based on: {reasons}. Confidence: {confidence:.0%}."
