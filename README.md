# Frictionless Dispute & Chargeback Resolution

An automated, transparent arbiter for card-charge disputes — auto-gathers evidence from both the card member and the merchant, weighs it with an explainable scorecard (not a black box), and returns a verdict both parties can see and understand in minutes instead of weeks.

Built for **CodeStreet** (AI / FinTech / Product Innovation / Data Analytics).

## Problem

Chargeback disputes are slow, opaque, and one-sided in practice. A card member disputes a charge; the merchant is given weeks to respond; a human analyst eventually reads through shipping records, policies, and correspondence to decide who's right. Neither party sees *why* until a verdict arrives.

**This is not fraud detection.** The transaction is genuine — the disagreement is about what happened next (was it delivered? was it as described? was the refund processed?). The system arbitrates between two legitimate but conflicting claims.

## Why this is different from what exists today

- **Merchant-side automation** (Chargeflow, Justt, Fini, ChatFin) auto-drafts *evidence responses* to help the merchant win — one-sided advocacy, not neutral arbitration.
- **Network-side infrastructure** (Visa Compelling Evidence 3.0 + Verifi, Mastercard Ethoca) shares data between merchant and issuer to prevent a dispute from escalating — useful, but it's data plumbing, not an explainable verdict.
- **Nobody occupies the neutral, two-sided, transparent-reasoning space** — an issuer-run arbiter that shows both parties the same evidence-based explanation for the same verdict. That's what this project is.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  React UI   │────▶│  FastAPI backend │────▶│    SQLite       │
│ (2 views:   │◀────│  (REST API)      │◀────│  (cases,        │
│ card member,│     └──────────────────┘     │  evidence,      │
│  merchant)  │            │                  │  signals,       │
└─────────────┘            ▼                  │  verdicts)      │
                    ┌──────────────────┐       └─────────────────┘
                    │  Claude API      │
                    │  (evidence parse │
                    │  + explanation,  │
                    │  offline mock    │
                    │  fallback)       │
                    └──────────────────┘
```

## How it maps to the challenge tasks

### 1. Automatically collect and parse transaction evidence
`backend/app/llm.py` — each evidence item (carrier tracking, merchant policy text, receipts, chat/email correspondence, photos) is sent through a structured-extraction prompt that returns typed JSON facts (delivery status, delivered-to address, signee, refund terms, whether the merchant admitted the issue, etc.), rather than leaving facts buried in free text. Runs against the Claude API when `ANTHROPIC_API_KEY` is set; falls back to a deterministic keyword-based parser otherwise, so the app is fully demoable offline.

### 2. Fair-weighing model
`backend/app/scoring.py` — a transparent weighted scorecard rather than a trained black-box classifier (faster to build, and every point is traceable to a named signal):

| Signal | Favors | Weight |
|---|---|---|
| Delivery address matches card member's address on file | Merchant | 25 |
| Delivery address does **not** match | Card member | 25 |
| Carrier shows item was never shipped | Card member | 30 |
| Carrier shows package returned to sender | Card member | 20 |
| Signed delivery confirmation exists | Merchant | 20 |
| Merchant's own policy allows a refund that wasn't given | Card member | 15 |
| Merchant's policy states no refunds | Merchant | 15 |
| Merchant correspondence admits the issue | Card member | 20 |
| Merchant submitted no evidence at all | Card member | 15 |
| Card member submitted no evidence (claim types where positive proof is reasonable to expect — excludes "item not received," since a card member can't prove a negative) | Merchant | 15 |

Verdict = higher-scoring side; confidence = `\|card_member_score − merchant_score\| / total`. No signals at all → explicitly flagged `insufficient_evidence`, provisional credit to the card member at 50% confidence (matches common issuer practice of provisional credit absent merchant proof).

### 3. Real-time interface for both parties
React app (`frontend/`) with a single case viewable from a **Card Member** or **Merchant** toggle — both see identical evidence, live status (`filed → evidence_gathering → resolved`), and the same verdict/explanation once resolved.

### 4. Transparent reasoning layer
The verdict's winning signals (only the winning ones — not the whole case) are handed to the LLM to render as a 2–3 sentence plain-English explanation, grounded in the actual scorecard so it can't drift into unsupported claims. The full signal breakdown is also shown directly in the UI (see `VerdictCard.jsx`).

### 5. Test and optimize
15 synthetic cases (`backend/app/seed.py`) spanning clear card-member wins, clear merchant wins, and genuinely ambiguous cases (left unresolved so the resolve step can be demoed live). Verified via direct API checks and a full browser walkthrough (evidence submission → resolution → verdict rendering).

## Data model

```
DisputeCase   — transaction, parties, claim type/text, status
Evidence      — who submitted it, raw content, parsed_facts (JSON)
ScoreSignal   — signal_name, detail, weight, which party it favors
Verdict       — winner, both scores, confidence, explanation
```

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, SQLite
- **Frontend:** React 18, Vite, React Router
- **AI:** Anthropic Claude API (with offline mock fallback)

## Getting started

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m app.seed          # seeds 15 synthetic cases
uvicorn app.main:app --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Set `ANTHROPIC_API_KEY` in the backend's environment to use real LLM-generated evidence parsing and explanations instead of the offline mock.

## Roadmap

- Tune scorecard weights against a larger/labeled case set
- Side-by-side "both parties see the identical explanation" demo view
- Additional evidence types (structured carrier webhook payloads, image analysis for damage claims)
- Deploy for the live finale demo
