"""Synthetic dispute cases for demoing the resolution pipeline.
Run with: python -m app.seed
"""
from . import llm, models
from .database import Base, SessionLocal, engine
from .scoring import score_case

CASES = [
    dict(
        transaction_id="TX1001", card_member_name="Priya Sharma", card_member_address="45 Oak Street, Springfield",
        merchant_name="BrewCo Online", amount=299.00, claim_type="item_not_received",
        claim_text="I never received this espresso machine. The tracking shows it wasn't even shipped.",
        evidence=[("merchant", "tracking_data", "Label created 2026-06-01. Carrier has not scanned the package since. Status: not shipped.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1002", card_member_name="Miguel Torres", card_member_address="12 Pine Ave, Rivertown",
        merchant_name="GadgetHub", amount=150.00, claim_type="item_not_received",
        claim_text="Card member claims non-receipt, but tracking shows delivery.",
        evidence=[("merchant", "tracking_data", "Package delivered to 12 Pine Ave, Rivertown, signed by M. Torres.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1003", card_member_name="Jordan Lee", card_member_address="78 Maple Drive, Lakeside",
        merchant_name="StyleWear Co", amount=89.50, claim_type="item_not_received",
        claim_text="I never got my order; the shipping address on the label doesn't even match mine.",
        evidence=[("merchant", "tracking_data", "Package delivered to 200 Birch Court, Millbrook, signed by unknown recipient.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1004", card_member_name="Sam Okafor", card_member_address="9 Cedar Lane, Brookfield",
        merchant_name="TechDeals Inc", amount=499.00, claim_type="refund_not_processed",
        claim_text="I returned this laptop stand three weeks ago and still haven't been refunded.",
        evidence=[("merchant", "policy_text", "Our return policy allows returns within 30 days for a full refund.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1005", card_member_name="Dana White", card_member_address="300 Elm St, Fairview",
        merchant_name="QuickMart", amount=60.00, claim_type="refund_not_processed",
        claim_text="I want a refund but the merchant says no refunds are given.",
        evidence=[("merchant", "policy_text", "All sales are final. No refunds or exchanges under any circumstances.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1006", card_member_name="Alex Kim", card_member_address="55 Willow Way, Northgate",
        merchant_name="FreshBox Grocery", amount=45.00, claim_type="not_as_described",
        claim_text="The produce box I received was moldy and nothing like the photos.",
        evidence=[("merchant", "chat_log", "Customer support: We're sorry for the inconvenience, we'll look into this.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1007", card_member_name="Taylor Reyes", card_member_address="21 Chestnut Blvd, Oakdale",
        merchant_name="HomeGoods Direct", amount=220.00, claim_type="not_as_described",
        claim_text="This item wasn't what I ordered.", evidence=[], resolve=False,
    ),
    dict(
        transaction_id="TX1008", card_member_name="Morgan Patel", card_member_address="8 Birch Court, Millbrook",
        merchant_name="ElectroWorld", amount=999.00, claim_type="duplicate_charge",
        claim_text="I was charged twice for the same order.",
        evidence=[("card_member", "receipt", "Order confirmation email received once, dated 2026-06-10.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1009", card_member_name="Chris Nguyen", card_member_address="14 Spruce St, Eastwood",
        merchant_name="LuxeFashion", amount=340.00, claim_type="item_not_received",
        claim_text="Merchant claims delivery but I never got anything, and the address doesn't match at all.",
        evidence=[("merchant", "tracking_data", "Delivered to 900 Industrial Pkwy, Warehouse District, signed by Receiving Dept.")],
        resolve=False,
    ),
    dict(
        transaction_id="TX1010", card_member_name="Riley Brooks", card_member_address="33 Aspen Ct, Hilltown",
        merchant_name="BookNook", amount=25.00, claim_type="item_not_received",
        claim_text="Tracking shows it's still in transit, but it's been a month.",
        evidence=[("merchant", "tracking_data", "Package scanned at regional facility, in transit to destination.")],
        resolve=False,
    ),
    dict(
        transaction_id="TX1011", card_member_name="Casey Nolan", card_member_address="61 Birchwood Dr, Meadowview",
        merchant_name="GourmetKitchen", amount=175.00, claim_type="refund_not_processed",
        claim_text="Merchant admitted the item was defective in chat but never refunded me.",
        evidence=[
            ("merchant", "chat_log", "We apologize for the defective unit and will process this for you."),
            ("merchant", "policy_text", "Refunds are provided within 14 days for defective items."),
        ],
        resolve=True,
    ),
    dict(
        transaction_id="TX1012", card_member_name="Harper Diaz", card_member_address="5 Magnolia Ave, Clearwater",
        merchant_name="SportsGear Plus", amount=210.00, claim_type="item_not_received",
        claim_text="Package was returned to sender apparently, but I was home all day.",
        evidence=[("merchant", "tracking_data", "Package returned to sender after failed delivery attempt.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1013", card_member_name="Skyler Vance", card_member_address="88 Redwood Ter, Ashford",
        merchant_name="GlowBeauty", amount=65.00, claim_type="not_as_described",
        claim_text="Item arrived damaged and merchant provided a photo showing packaging was fine.",
        evidence=[("merchant", "photo", "Photo shows the shipping box fully intact with no visible damage.")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1014", card_member_name="Jamie Fox", card_member_address="17 Poplar Pl, Greendale",
        merchant_name="PetSupplyCo", amount=54.00, claim_type="duplicate_charge",
        claim_text="Charged twice, and merchant already refunded one charge via email confirmation.",
        evidence=[("merchant", "email", "We've confirmed and refunded the duplicate charge as requested. Sorry for the trouble!")],
        resolve=True,
    ),
    dict(
        transaction_id="TX1015", card_member_name="Avery Stone", card_member_address="3 Hemlock Row, Bayview",
        merchant_name="ArtSupplyHub", amount=132.00, claim_type="item_not_received",
        claim_text="Item shows delivered and signed, but the box was empty when I opened it.",
        evidence=[
            ("merchant", "tracking_data", "Delivered to 3 Hemlock Row, Bayview, signed by A. Stone."),
            ("card_member", "chat_log", "I did receive a package but it was empty when I opened it."),
        ],
        resolve=False,
    ),
]


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
        if spec["evidence"]:
            case.status = models.CaseStatus.evidence_gathering
        db.flush()

        if spec["resolve"]:
            db.refresh(case)
            signals, winner, cm_score, m_score, confidence = score_case(case, case.evidence)
            for s in signals:
                db.add(models.ScoreSignal(
                    case_id=case.id, signal_name=s.signal_name, detail=s.detail,
                    weight=s.weight, favors=s.favors,
                ))
            winning_signals = [s for s in signals if s.favors == winner]
            explanation = llm.generate_explanation(case, winning_signals, confidence)
            db.add(models.Verdict(
                case_id=case.id, winner=winner, card_member_score=cm_score,
                merchant_score=m_score, confidence=confidence, explanation=explanation,
            ))
            case.status = models.CaseStatus.resolved

        db.commit()
        print(f"Seeded {case.transaction_id} ({'resolved' if spec['resolve'] else case.status.value})")

    db.close()


if __name__ == "__main__":
    seed()
