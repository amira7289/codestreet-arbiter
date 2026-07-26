# Frictionless Dispute & Chargeback Resolution

An automated, transparent arbiter for card-charge disputes — auto-gathers evidence from four data sources, weighs it with an explainable scorecard (not a black box), and returns a verdict both parties see, with the same explanation, in seconds instead of weeks.

Built for **CodeStreet** (AI / FinTech / Product Innovation / Data Analytics).

## Problem

Chargeback disputes are slow, opaque, and one-sided in practice. A card member disputes a charge; the merchant is given weeks to respond; a human analyst eventually reads through shipping records, policies, and correspondence to decide who's right. Neither party sees *why* until a verdict arrives.

**This is not fraud detection.** The transaction is genuine — the disagreement is about what happened next (was it delivered? was it as described? was the refund processed?). The system arbitrates between two legitimate but conflicting claims.

## Why this is different from what exists today

- **Merchant-side automation** (Chargeflow, Justt, ChargePay, ChatFin, Chargebacks911) auto-drafts *evidence responses* to help the merchant win — one-sided advocacy, not neutral arbitration.
- **Network-side infrastructure** (Visa Compelling Evidence 3.0 + Verifi, Mastercard Ethoca) shares data between merchant and issuer to prevent escalation — useful, but it's data plumbing, not an explainable verdict.
- **Where "explainability" already appears** in this market, it means dashboards showing risk-score drivers to *internal analysts*. Not a shared explanation handed to both disputing parties.
- **Nobody occupies the neutral, two-sided, transparent-reasoning space** — an issuer-run arbiter that shows both parties the same evidence-based explanation for the same verdict. That's what this project is.

## Core architectural commitment

**The LLM extracts typed facts and narrates the verdict. A deterministic weighted scorecard decides the outcome.**

The decision never sits in the model. Every point in every verdict traces to a named signal with a fixed weight, defined in one auditable table. This is what makes the system explainable, reproducible, and testable — and it's why the accuracy and fairness numbers below can be recomputed by anyone in under a second.

## Architecture

```
┌──────────────────────────┐      ┌─────────────────────┐      ┌──────────────┐
│  React UI                │─────▶│  FastAPI            │─────▶│  SQLite      │
│  · side-by-side panels   │◀─────│  · REST + async     │◀─────│  cases       │
│    (card member │ merch) │      │    background tasks │      │  evidence    │
│  · 1.5s / 5s polling     │      └─────────────────────┘      │  gather_logs │
│  · gather timeline       │              │      │             │  signals     │
│  · shared verdict card   │              │      │             │  verdicts    │
└──────────────────────────┘              ▼      ▼             └──────────────┘
                            ┌──────────────┐  ┌────────────────────┐
                            │ connectors   │  │ scoring            │
                            │ carrier_api  │  │ SIGNAL_CATALOG     │
                            │ processor_   │  │ deterministic      │
                            │   ledger     │  │ counterfactuals    │
                            │ policy_api   │  └────────────────────┘
                            │ merchant_crm │            │
                            └──────────────┘            ▼
                                    │        ┌────────────────────┐
                                    └───────▶│ Claude API         │
                                             │ fact extraction +  │
                                             │ narration only     │
                                             │ (offline fallback) │
                                             └────────────────────┘
```

## How it maps to the challenge tasks

### 1. Automatically collect and parse transaction evidence

`backend/app/connectors.py` simulates four data sources — carrier tracking, the Amex processor ledger, the merchant returns-policy API, and the merchant CRM — routed per claim type. Filing a dispute triggers a gather across every applicable source; **hits and misses are both logged**, because an adverse inference against a party is only fair when the record shows their systems were asked and returned nothing.

Each retrieved document goes through `backend/app/llm.py`, which turns free text into typed facts (delivery status, signee, settlement counts, refund amounts, policy windows, damage). Runs against the Claude API when `ANTHROPIC_API_KEY` is set; falls back to a deterministic parser otherwise, so the app is fully demoable offline. The offline parser is not a stub — it handles signature negation, generic signees, three-state refund policies, and admission-versus-politeness.

### 2. Fair-weighing model

`backend/app/scoring.py` — a transparent weighted scorecard, with every weight in one `SIGNAL_CATALOG` table so it can be printed, audited and tuned in one place. 25 signals across four claim types. A selection:

| Signal | Favours | Weight |
|---|---|---|
| `duplicate_settlement_confirmed` — two captured settlements, no offsetting refund | Card member | 35 |
| `not_shipped` — carrier never scanned the parcel | Card member | 30 |
| `refund_posted_in_ledger` / `refund_already_issued` | Merchant | 30 |
| `address_mismatch` / `address_match` | either | 25 |
| `photo_shows_damage` | Card member | 25 |
| `delivery_confirmation_named` — signed by the card member | Merchant | 20 |
| `delivery_confirmation_thirdparty` — signed by someone else | Merchant | 8 |
| `photo_shows_no_damage` | Merchant | 15 |
| `no_merchant_evidence` / `no_card_member_evidence` | either | 15 / 10 |

Confidence is **evidence-mass aware**: `margin × (0.5 + 0.5 × min(1, total/60))`. A 15–0 split off one procedural signal reports 62%, not 100%.

**On fairness, the claim is not that the scorecard is unbiased.** Ambiguous cases resolve to the card member, matching issuer provisional-credit practice. That default is deliberate — and it is *disclosed*, as zero-weight `provisional_credit_no_evidence` and `tie_break_provisional_credit` signals rendered on the verdict itself, rather than hidden in a comparison operator. The target is that every point of directional bias traces to a rule stated out loud.

### 3. Real-time interface for both parties

React app with **both party panels rendered side by side**, live. Each side sees its own filings, everything the other side filed, and the identical verdict beneath a shared banner. Evidence appears row by row as connectors report, via async background tasks and a 1.5s poll (5s once resolved — a resolved case can still be re-opened by the other party, and a tab showing a retracted verdict is the exact failure this project exists to prevent).

### 4. Transparent reasoning layer

Four layers, in increasing order of usefulness to a losing party:

1. **The signal breakdown** — every point, named and attributed to the document it came from.
2. **The Amex chargeback reason code** — C02, C08, C31, C32 or P08, derived deterministically from claim type and fired signals.
3. **The counterfactual** — *"This would have gone to the card member if these had not been established (−45 points): …"*. Computed by arithmetic over the scorecard (`minimal_flip_set`), so it cannot hallucinate. It answers the only question a losing party actually asks.
4. **The narrative explanation** — grounded in the scorecard, and required to acknowledge the strongest point on the losing side and why it was outweighed.

There is also a **"Recommended for human review"** banner, which fires when a party filed evidence that no rule in the scorecard reads, or when confidence is below 35%. A signature proves a box arrived, not what was in it; the system says so rather than ruling confidently on a case no human could decide.

### 5. Test and optimise

```
pytest backend/tests -q          90 tests
python -m app.evaluate           accuracy, fairness, calibration, latency
GET /metrics                     the same numbers, live
```

Measured on a 60-case labelled corpus (`backend/tests/goldens.json`), weighted toward contested and adversarial shapes on purpose — adding easy cases would lift the figure without making it more informative:

| Metric | Value |
|---|---|
| **Accuracy** | **98%** (53/54 arbitrable; 6 abstentions excluded) |
| By claim type | item_not_received 100%, duplicate_charge 100%, refund_not_processed 100%, not_as_described 90% |
| Adversarial subset | 100% (20/20) |
| Fairness | bias_gap 0.032 · recall 97% card member / 100% merchant |
| Errors favouring card member | 0 |
| Confidently wrong (≥80%) | 0 |
| p95 latency, parse + score + explain | 0.2 ms offline |

`backend/tests/test_fairness.py` runs two audits in CI: a **catalog asymmetry audit** that fails on any weight imbalance not documented with a written justification, and **party-swap tests** asserting identical evidence is worth the same regardless of who benefits.

Progress across phases, on the original corpus: 82% → 91% → 95%; then **98%** on a corpus more than twice the size; calibration separation 0.02 → 0.17; cases reporting 100% confidence off a single signal 11 → 0.

## Data model

```
DisputeCase   — transaction, parties, claim type/text, status
Evidence      — submitter, raw content, parsed_facts, source, auto_gathered
GatherLog     — every connector query: source, hit/miss/skipped/error, latency
ScoreSignal   — signal_name, detail, weight, favours, evidence_id
Verdict       — winner, scores, confidence, explanation, reason_code, counterfactual
```

`ScoreSignal.evidence_id` is what lets the UI distinguish *"your evidence was weighed and went against you"* from *"no rule reads what you filed"*.

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, SQLite, pytest
- **Frontend:** React 18, Vite, React Router — no CSS framework, no component library
- **AI:** Anthropic Claude API for fact extraction and narration, with a full offline fallback

No other external services. The app runs entirely from its own SQLite file.

## Getting started

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m app.seed                    # 15 cases, evidence produced by the connectors
uvicorn app.main:app --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                           # http://localhost:5173

# Verification
cd backend
pytest tests -q
python -m app.evaluate
```

Set `ANTHROPIC_API_KEY` for LLM-backed parsing and narration. **Everything works without it** — the demo runs offline by design.

The schema changes between phases and `create_all` cannot ALTER tables. If you see `no such column`, run `rm backend/disputes.db && python -m app.seed`.

## Known limitations

Stated plainly, because a system that reports its own uncertainty is the point.

- **The 60 labels are the author's judgement**, not adjudicated ground truth. The measurement discipline is the contribution; the number is only as good as the corpus.
- **Connector latencies are synthetic** — derived from a hash of the source and transaction id, not measured. They are a simulation of network cost, not evidence of it.
- **One known failure** (TX1006): a merchant who files a non-committal chat log avoids the adverse inference for silence while the card member still carries the no-evidence penalty. Filing a meaningless document is currently rewarded.
- **No abstain verdict.** Genuinely undecidable cases still produce a winner, flagged for human review rather than withheld.
- **Single-process concurrency.** Gather is serialised per case with an in-process lock; a multi-worker deployment would need a unique index instead.
