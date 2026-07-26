"""End-to-end API tests over the real routes.

Every test runs against a throwaway SQLite file wired in through
`app.dependency_overrides`, so the demo database is never touched.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        test_client._session_factory = Session
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(path)


def make_case(client, **overrides):
    payload = {
        "transaction_id": "TX9001",
        "card_member_name": "Priya Sharma",
        "card_member_address": "45 Oak Street, Springfield",
        "merchant_name": "BrewCo Online",
        "amount": 299.0,
        "claim_type": "item_not_received",
        "claim_text": "Never arrived.",
    }
    payload.update(overrides)
    response = client.post("/cases", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# --- lifecycle -------------------------------------------------------------

def test_create_gather_resolve_end_to_end(client):
    case = make_case(client, transaction_id="TX1001")

    gathered = client.post(f"/cases/{case['id']}/gather")
    assert gathered.status_code == 200
    assert gathered.json()["evidence_created"] > 0

    resolved = client.post(f"/cases/{case['id']}/resolve")
    assert resolved.status_code == 200
    verdict = resolved.json()
    assert verdict["winner"] in ("card_member", "merchant")
    assert verdict["reason_code"], "every verdict must carry a chargeback reason code"
    assert verdict["counterfactual"], "every verdict must explain what would have changed it"

    detail = client.get(f"/cases/{case['id']}").json()
    assert detail["status"] == "resolved"
    assert detail["verdict"]["explanation"]


def test_gather_is_idempotent(client):
    case = make_case(client, transaction_id="TX1001")
    first = client.post(f"/cases/{case['id']}/gather").json()
    second = client.post(f"/cases/{case['id']}/gather").json()

    assert first["evidence_created"] > 0
    assert second["evidence_created"] == 0
    assert all(e["status"] == "skipped" for e in second["entries"] if e["evidence_type"])


def test_gather_logs_misses_as_well_as_hits(client):
    case = make_case(client, transaction_id="TX1008", claim_type="duplicate_charge", amount=999.0)
    entries = client.post(f"/cases/{case['id']}/gather").json()["entries"]
    statuses = {e["status"] for e in entries}
    assert "hit" in statuses and "miss" in statuses, (
        "an adverse inference is only fair if the log shows the source was asked")


# --- D13 / S1: a verdict must never outlive its evidence set ---------------

def test_late_evidence_withdraws_the_verdict(client):
    case = make_case(client, transaction_id="TX1001")
    client.post(f"/cases/{case['id']}/gather")
    client.post(f"/cases/{case['id']}/resolve")

    client.post(f"/cases/{case['id']}/evidence", json={
        "submitted_by": "merchant",
        "evidence_type": "tracking_data",
        "raw_content": "Delivered to 45 Oak Street, Springfield, signed by P. Sharma.",
    })

    detail = client.get(f"/cases/{case['id']}").json()
    assert detail["verdict"] is None
    assert detail["signals"] == []
    assert detail["status"] == "evidence_gathering"


def test_re_resolving_accounts_for_the_new_evidence(client):
    case = make_case(client, transaction_id="TX1001")
    client.post(f"/cases/{case['id']}/gather")
    before = client.post(f"/cases/{case['id']}/resolve").json()

    client.post(f"/cases/{case['id']}/evidence", json={
        "submitted_by": "merchant",
        "evidence_type": "tracking_data",
        "raw_content": "Delivered to 45 Oak Street, Springfield, signed by P. Sharma.",
    })
    after = client.post(f"/cases/{case['id']}/resolve").json()
    assert after["merchant_score"] > before["merchant_score"]


def test_gather_that_finds_nothing_new_leaves_the_verdict_standing(client):
    """A re-gather with no new evidence must not un-resolve the case."""
    case = make_case(client, transaction_id="TX1001")
    client.post(f"/cases/{case['id']}/gather")
    client.post(f"/cases/{case['id']}/resolve")

    again = client.post(f"/cases/{case['id']}/gather").json()
    assert again["evidence_created"] == 0

    detail = client.get(f"/cases/{case['id']}").json()
    assert detail["verdict"] is not None, "nothing changed, so the ruling still holds"
    assert detail["status"] == "resolved", "a no-op gather must not re-open a settled case"


# --- validation and error handling (D20) -----------------------------------

@pytest.mark.parametrize("bad", [
    {"amount": -500.0},
    {"amount": 0},
    {"transaction_id": ""},
    {"card_member_name": ""},
    {"claim_text": ""},
    {"claim_type": "not_a_real_claim_type"},
])
def test_invalid_cases_are_rejected(client, bad):
    payload = {
        "transaction_id": "TX9002", "card_member_name": "A", "card_member_address": "1 St",
        "merchant_name": "M", "amount": 10.0, "claim_type": "duplicate_charge", "claim_text": "x",
    }
    payload.update(bad)
    assert client.post("/cases", json=payload).status_code == 422


@pytest.mark.parametrize("path", [
    "/cases/999999", "/cases/999999/gather-log",
])
def test_unknown_case_returns_404(client, path):
    assert client.get(path).status_code == 404


def test_unknown_case_404s_on_writes(client):
    assert client.post("/cases/999999/gather").status_code == 404
    assert client.post("/cases/999999/resolve").status_code == 404
    assert client.post("/cases/999999/evidence", json={
        "submitted_by": "merchant", "evidence_type": "email", "raw_content": "hi",
    }).status_code == 404


def test_health_and_docs_are_reachable(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/openapi.json").status_code == 200


# --- ordering (D21) --------------------------------------------------------

def test_case_list_order_is_stable(client):
    for i in range(5):
        make_case(client, transaction_id=f"TX90{i}")
    first = [c["id"] for c in client.get("/cases").json()]
    second = [c["id"] for c in client.get("/cases").json()]
    assert first == second, "second-granular timestamps need an id tiebreaker"


# --- signal provenance surfaces through the API ----------------------------

def test_signals_expose_the_document_they_came_from(client):
    case = make_case(client, transaction_id="TX1001")
    client.post(f"/cases/{case['id']}/gather")
    client.post(f"/cases/{case['id']}/resolve")

    detail = client.get(f"/cases/{case['id']}").json()
    known = {e["id"] for e in detail["evidence"]}
    for signal in detail["signals"]:
        for source_id in signal["evidence_ids"]:
            assert source_id in known, "signal points at a foreign document"
