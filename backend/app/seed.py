"""Synthetic dispute cases for demoing the resolution pipeline.
Run with: python -m app.seed

Most cases carry no hand-written evidence: `auto_gather` runs the real connectors,
so the seeded corpus is produced by the same path a live case takes. TX1011, TX1013
and TX1015 keep manually submitted items — a merchant photo and a card member's own
account are not things any API returns — so both paths stay visible in the UI.
"""
from . import llm, models, reason_codes
from .database import Base, SessionLocal, engine
from .routers.cases import run_gather
from .scoring import counterfactual_statement, score_case

CASES = [
    dict(
        transaction_id="TX1001", card_member_name="Priya Sharma", card_member_address="45 Oak Street, Springfield",
        merchant_name="BrewCo Online", amount=299.00, claim_type="item_not_received",
        claim_text="I never received this espresso machine. The tracking shows it wasn't even shipped.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    dict(
        transaction_id="TX1002", card_member_name="Miguel Torres", card_member_address="12 Pine Ave, Rivertown",
        merchant_name="GadgetHub", amount=150.00, claim_type="item_not_received",
        claim_text="Card member claims non-receipt, but tracking shows delivery.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    dict(
        transaction_id="TX1003", card_member_name="Jordan Lee", card_member_address="78 Maple Drive, Lakeside",
        merchant_name="StyleWear Co", amount=89.50, claim_type="item_not_received",
        claim_text="I never got my order; the shipping address on the label doesn't even match mine.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    dict(
        transaction_id="TX1004", card_member_name="Sam Okafor", card_member_address="9 Cedar Lane, Brookfield",
        merchant_name="TechDeals Inc", amount=499.00, claim_type="refund_not_processed",
        claim_text="I returned this laptop stand three weeks ago and still haven't been refunded.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    dict(
        transaction_id="TX1005", card_member_name="Dana White", card_member_address="300 Elm St, Fairview",
        merchant_name="QuickMart", amount=60.00, claim_type="refund_not_processed",
        claim_text="I want a refund but the merchant says no refunds are given.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    dict(
        transaction_id="TX1006", card_member_name="Alex Kim", card_member_address="55 Willow Way, Northgate",
        merchant_name="FreshBox Grocery", amount=45.00, claim_type="not_as_described",
        claim_text="The produce box I received was moldy and nothing like the photos.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    dict(
        transaction_id="TX1007", card_member_name="Taylor Reyes", card_member_address="21 Chestnut Blvd, Oakdale",
        merchant_name="HomeGoods Direct", amount=220.00, claim_type="not_as_described",
        claim_text="This item wasn't what I ordered.",
        evidence=[], auto_gather=True, resolve=False,
    ),
    dict(
        transaction_id="TX1008", card_member_name="Morgan Patel", card_member_address="8 Birch Court, Millbrook",
        merchant_name="ElectroWorld", amount=999.00, claim_type="duplicate_charge",
        claim_text="I was charged twice for the same order.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    dict(
        transaction_id="TX1009", card_member_name="Chris Nguyen", card_member_address="14 Spruce St, Eastwood",
        merchant_name="LuxeFashion", amount=340.00, claim_type="item_not_received",
        claim_text="Merchant claims delivery but I never got anything, and the address doesn't match at all.",
        evidence=[], auto_gather=True, resolve=False,
    ),
    dict(
        transaction_id="TX1010", card_member_name="Riley Brooks", card_member_address="33 Aspen Ct, Hilltown",
        merchant_name="BookNook", amount=25.00, claim_type="item_not_received",
        claim_text="Tracking shows it's still in transit, but it's been a month.",
        evidence=[], auto_gather=True, resolve=False,
    ),
    # Manual path: both items were pasted in by the merchant during the original
    # correspondence, before any connector existed.
    dict(
        transaction_id="TX1011", card_member_name="Casey Nolan", card_member_address="61 Birchwood Dr, Meadowview",
        merchant_name="GourmetKitchen", amount=175.00, claim_type="refund_not_processed",
        claim_text="Merchant admitted the item was defective in chat but never refunded me.",
        evidence=[
            ("merchant", "chat_log", "We apologize for the defective unit and will process this for you."),
            ("merchant", "policy_text", "Refunds are provided within 14 days for defective items."),
        ],
        auto_gather=False, resolve=True,
    ),
    dict(
        transaction_id="TX1012", card_member_name="Harper Diaz", card_member_address="5 Magnolia Ave, Clearwater",
        merchant_name="SportsGear Plus", amount=210.00, claim_type="item_not_received",
        claim_text="Package was returned to sender apparently, but I was home all day.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    # Manual path: a photograph is not something any connector returns.
    dict(
        transaction_id="TX1013", card_member_name="Skyler Vance", card_member_address="88 Redwood Ter, Ashford",
        merchant_name="GlowBeauty", amount=65.00, claim_type="not_as_described",
        claim_text="Item arrived damaged and merchant provided a photo showing packaging was fine.",
        evidence=[("merchant", "photo", "Photo shows the shipping box fully intact with no visible damage.")],
        auto_gather=False, resolve=True,
    ),
    dict(
        transaction_id="TX1014", card_member_name="Jamie Fox", card_member_address="17 Poplar Pl, Greendale",
        merchant_name="PetSupplyCo", amount=54.00, claim_type="duplicate_charge",
        claim_text="Charged twice, and merchant already refunded one charge via email confirmation.",
        evidence=[], auto_gather=True, resolve=True,
    ),
    # Mixed path: the carrier record is auto-gathered, the card member's account of
    # what was in the box can only come from the card member.
    dict(
        transaction_id="TX1015", card_member_name="Avery Stone", card_member_address="3 Hemlock Row, Bayview",
        merchant_name="ArtSupplyHub", amount=132.00, claim_type="item_not_received",
        claim_text="Item shows delivered and signed, but the box was empty when I opened it.",
        evidence=[("card_member", "chat_log", "I did receive a package but it was empty when I opened it.")],
        auto_gather=True, resolve=False,
    ),
]


# ---------------------------------------------------------------------------
# Portfolio depth.
#
# The fifteen cases above are hand-written because each one demonstrates a specific
# behaviour and carries a hand-authored connector fixture. These are different: they
# exist so the dashboard shows a book of business rather than a sample, and their
# evidence comes from the connectors' deterministic synthesis. Generated from fixed
# pools so a reseed always produces the same portfolio.
# ---------------------------------------------------------------------------

_NAMES = [
    "Amara Osei", "Ben Halloran", "Carmen Ruiz", "Devin Park", "Elena Fischer",
    "Farid Haddad", "Grace Whitfield", "Hugo Almeida", "Ines Moreau", "Jonah Reed",
    "Keiko Tanaka", "Liam Doherty", "Maya Ellison", "Noor Rahman", "Oscar Lindqvist",
    "Petra Novak", "Quentin Blake", "Rosa Delgado", "Samir Chowdhury", "Tessa Bright",
    "Ugo Bianchi", "Vera Sokolova", "Wesley Grant", "Xiomara Cruz", "Yusuf Demir",
    "Zara Mensah", "Adam Kowalski", "Bianca Ferraro", "Caleb Nwosu", "Delphine Roy",
]

_STREETS = [
    "12 Ashgrove Lane, Kingsbury", "7 Bramble Court, Westhaven", "154 Canal Street, Portmead",
    "39 Dovecote Road, Ashfield", "6 Elmwood Rise, Northbrook", "221 Fenwick Avenue, Stonegate",
    "18 Garland Way, Millbrook", "94 Harrow Close, Eastvale", "3 Ivybridge Terrace, Larkfield",
    "67 Juniper Drive, Redhill", "25 Kestrel Place, Wyndham", "110 Linden Grove, Fairwater",
    "8 Maplehurst Road, Colton", "47 Newbury Street, Havenport", "132 Orchard Row, Selby",
]

_MERCHANTS = [
    "NorthPeak Outfitters", "Lumen Home", "Verdant Grocers", "Circuit & Co",
    "Atlas Luggage", "Petal & Stem", "Ironwood Tools", "Bluewater Swim",
    "Copper Kitchen", "Drift Audio", "Everline Apparel", "Foundry Ceramics",
]

_CLAIM_TEXT = {
    "item_not_received": [
        "Order never turned up and the tracking has not moved in weeks.",
        "Marked as delivered but nothing arrived at my address.",
        "Paid for this a month ago and it has still not shipped.",
    ],
    "not_as_described": [
        "What arrived is not the item shown on the listing.",
        "Item arrived damaged and unusable.",
        "The size and material are nothing like the description.",
    ],
    "duplicate_charge": [
        "I placed one order and was billed twice for it.",
        "Two identical charges on the same day for a single purchase.",
    ],
    "refund_not_processed": [
        "Returned the item weeks ago and no refund has appeared.",
        "The merchant agreed to refund me and then never did.",
        "Cancelled before dispatch but was still charged.",
    ],
}

_CLAIM_CYCLE = [
    "item_not_received", "not_as_described", "refund_not_processed",
    "duplicate_charge", "item_not_received", "refund_not_processed",
]


def _generated_cases(count=30, start=2001):
    """Deterministic portfolio filler. No connector fixtures: `run_gather` falls
    through to synthesis, which is keyed off the transaction id and so is stable."""
    out = []
    for i in range(count):
        claim = _CLAIM_CYCLE[i % len(_CLAIM_CYCLE)]
        texts = _CLAIM_TEXT[claim]
        amount = round(28 + (i * 137) % 940 + (i % 4) * 0.5, 2)
        # A spread of outcomes so the pipeline chart is not all one bar.
        resolve = i % 5 != 3
        out.append(dict(
            transaction_id="TX{}".format(start + i),
            card_member_name=_NAMES[i % len(_NAMES)],
            card_member_address=_STREETS[i % len(_STREETS)],
            merchant_name=_MERCHANTS[i % len(_MERCHANTS)],
            amount=amount,
            claim_type=claim,
            claim_text=texts[i % len(texts)],
            evidence=[],
            auto_gather=True,
            resolve=resolve,
        ))
    return out


CASES = CASES + _generated_cases()


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(models.DisputeCase).count() > 0:
        print("Cases already exist — skipping seed. Delete disputes.db to reseed.")
        db.close()
        return

    for spec in CASES:
        case = models.DisputeCase(
            transaction_id=spec["transaction_id"],
            card_member_name=spec["card_member_name"],
            card_member_address=spec["card_member_address"],
            merchant_name=spec["merchant_name"],
            amount=spec["amount"],
            claim_type=spec["claim_type"],
            claim_text=spec["claim_text"],
            status=models.CaseStatus.filed,
        )
        db.add(case)
        db.flush()

        for submitted_by, evidence_type, raw_content in spec["evidence"]:
            parsed_facts = llm.parse_evidence(evidence_type, raw_content)
            db.add(models.Evidence(
                case_id=case.id, submitted_by=submitted_by, evidence_type=evidence_type,
                raw_content=raw_content, parsed_facts=parsed_facts,
            ))
        db.flush()

        gathered = 0
        if spec["auto_gather"]:
            _, gathered = run_gather(db, case)
        elif spec["evidence"]:
            case.status = models.CaseStatus.evidence_gathering
        db.flush()

        if spec["resolve"]:
            db.refresh(case)
            signals, winner, cm_score, m_score, confidence = score_case(case, case.evidence)
            for s in signals:
                db.add(models.ScoreSignal(
                    case_id=case.id, signal_name=s.signal_name, detail=s.detail,
                    weight=s.weight, favors=s.favors, evidence_ids=s.evidence_ids,
                ))
            code, code_label = reason_codes.derive_reason_code(case, signals)
            explanation = llm.generate_explanation(case, signals, winner, confidence, code_label, case.evidence)
            db.add(models.Verdict(
                case_id=case.id, winner=winner, card_member_score=cm_score,
                merchant_score=m_score, confidence=confidence, explanation=explanation,
                reason_code=code, reason_code_label=code_label,
                counterfactual=counterfactual_statement(signals, winner, cm_score, m_score),
            ))
            case.status = models.CaseStatus.resolved

        db.commit()
        print("Seeded {} ({}, {} manual + {} auto-gathered)".format(
            case.transaction_id,
            "resolved" if spec["resolve"] else case.status.value,
            len(spec["evidence"]), gathered,
        ))

    db.close()


if __name__ == "__main__":
    seed()
