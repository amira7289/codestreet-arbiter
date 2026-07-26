# Implementation Plan — Frictionless Dispute & Chargeback Resolution

Phase-wise build plan taking the current prototype to a complete, defensible submission.

**Total effort:** ~20 hours across 7 phases
**Mode:** solo, strictly sequential — every phase ends with a working, demoable app
**Runtime:** offline only (`ANTHROPIC_API_KEY` unset, mock parsers)
**Fairness stance:** pro-card-member tie-breaks are *kept* as deliberate issuer provisional-credit policy, but made explicit and disclosed rather than silent

---

## Locked decisions

| Decision | Choice | Consequence for this plan |
|---|---|---|
| Scope | Full build, Phases 0–6 | Every graded task covered at depth |
| Team | Solo | No parallel tracks; each phase is independently demoable |
| LLM mode | Offline mock only | **Mock parser quality is the critical path.** The mock regexes are currently the weakest component in the system, so they are fixed first (Phase 0). Real-API hardening is deferred to Phase 6 as a cheap guard. |
| Fairness | Keep + disclose | Tie-breaks become **named, visible signals** with UI rendering and a deck slide, not a silent `>=`. Target is *"all directional bias is attributable to a disclosed rule"* — **not** `bias_gap ≈ 0`. |

### Non-negotiable architectural constraint

**The LLM extracts typed facts and narrates the verdict. A deterministic weighted scorecard decides the outcome.** The decision never moves into the model. Every point in a verdict must trace to a named signal with a fixed weight. This is what makes the system explainable, auditable, and reproducible — and it is the core differentiator versus every merchant-side tool on the market.

---

## Measured baseline (before any work)

Established by replaying the real scorer over the real seed corpus. Record these; every later phase moves one of them.

| Metric | Value |
|---|---|
| Accuracy | 12/13 arbitrable cases = **92%** (flattering — see below) |
| Verdicts favouring card member | **73%** (11/15) vs **60%** on human labels |
| Cases decided purely by hardcoded tie-breaks | **3/15 (20%)** — TX1004, TX1007, TX1010 |
| Signal inventory | 6 card-member signals / 125 pts vs 4 merchant / 75 pts |
| Claim types with substantive logic | 2 of 4 |
| Automated tests | 0 |

The 92% is not robust: 3 of 15 cases are decided by tie-breaks rather than evidence, and 2 of the 4 scoring heuristics invert on a single keyword. The absence of a test suite is what conceals this.

---

## Defect register

All confirmed by execution against real seed data. Each is assigned to the phase that fixes it.

| # | Defect | Location | Phase |
|---|---|---|---|
| D1 | `"Not signed by anyone."` → `signed_by="Anyone"` → +20 merchant. Real seeds `"Unknown Recipient"` / `"Receiving Dept"` also score. | `llm.py:86` | 0 |
| D2 | `refund_allowed = "no refund" not in lower` — 4 of 5 realistic no-refund policies read as *refunds allowed* | `llm.py:97` | 0 |
| D3 | `merchant_admitted_issue = "sorry" in lower` — politeness = 20-pt legal admission; misses real admissions | `llm.py:101` | 0 |
| D4 | No `photo` branch in `_mock_parse_evidence` — `shows_damage` is never produced offline | `llm.py:101` | 0 |
| D5 | `receipt` parser is a hardcoded stub returning nulls | `llm.py:100` | 0 |
| D6 | `_address_matches` ≥2-token overlap — different building/city → +25 merchant. One-directional, merchant-favouring. | `scoring.py:14-21` | 1 |
| D7 | Exact tie → card member at 0% confidence, undisclosed anywhere | `scoring.py:111` | 1 |
| D8 | Confidence not evidence-mass aware — a single 15-pt procedural signal renders as 100% | `scoring.py:112` | 1 |
| D9 | Duplicate evidence double-counts signals (same scan twice → 90 pts) | `scoring.py:29` | 1 |
| D10 | Zero-evidence returns hardcoded `0.5` confidence — a constant, not a measurement | `scoring.py:109` | 1 |
| D11 | `not_as_described` / `duplicate_charge` decided by procedural bookkeeping at 100% confidence | `scoring.py` | 3 |
| D12 | `shows_damage`, `return_window_days`, `order_date`, `shipping_address` never read by scorer | `scoring.py` | 3 |
| D13 | Evidence accepted after resolution, never re-scored; Resolve button hidden → stale verdict is permanent | `cases.py:33-48`, `CaseDetail.jsx:95` | 4 |
| D14 | Party toggle is cosmetic — `visibleEvidence = caseData.evidence` regardless of view | `CaseDetail.jsx:48` | 4 |
| D15 | `key={s.signal_name}` collides once two signals share a name | `VerdictCard.jsx:49` | 4 |
| D16 | `CaseStatus.scored` declared and styled but never assigned | `models.py:13` | 4 |
| D17 | Explanation cites only winning signals — never acknowledges the losing side | `cases.py:65-66` | 5 |
| D18 | Anthropic calls outside try/except → HTTP 500 on any API error | `llm.py:63,119` | 6 |
| D19 | `_extract_json` returns `{}` on non-JSON → evidence silently dropped, no warning | `llm.py:23-25`, `scoring.py:30` | 6 |
| D20 | No input validation — negative amounts, empty strings, duplicate transaction IDs all accepted | `schemas.py:9-16` | 6 |
| D21 | `order_by(created_at.desc())` with second-granularity timestamps → list reshuffles between refreshes | `cases.py:22` | 6 |
| D22 | CORS pinned to `localhost:5173`; Vite falls forward to 5174 → total frontend failure | `main.py:14` | 6 |
| D23 | TX1015 (empty box) ships **resolved, merchant, 100% confidence**, contradicting `README.md:67` | `disputes.db` | 3 |

---

## Phase 0 — Trustworthy inputs + measured baseline

**Advances:** tasks 1, 5 · **Effort: 3.5h** · **Depends on:** nothing

Because the demo runs offline, `_mock_parse_evidence` *is* the evidence-parsing algorithm being graded. Every downstream signal reads its output, so fixing extraction before scoring is the only sane order. This phase also stands up the measurement harness first, so every later phase can claim a quantified improvement rather than an asserted one.

### 0.1 — Rewrite the mock parsers (`backend/app/llm.py`)

Replace the keyword soup with structured extraction. Keep every function signature identical so nothing downstream changes.

```python
_GENERIC_SIGNEES = {"unknown", "unknown recipient", "receiving dept", "receiving department",
                    "front desk", "resident", "occupant", "n/a", "none", "neighbor", "driver"}
_NEGATION = re.compile(r"\b(not|never|no|unable to be|refused)\b[^.]{0,20}\bsigned\b")

def _extract_signee(text: str) -> Optional[str]:
    """None when negated, when the name is in _GENERIC_SIGNEES, or when unparseable.
    Must survive trailing dates, apostrophes and hyphens: 'signed by J. O'Brien on 2026-06-02.'"""
```

- **D1** — check `_NEGATION` before matching; drop the `$` anchor so trailing text doesn't kill real signatures; widen the character class to `[A-Za-z .'\-]`; return `None` for generic signees.
- **D2** — `refund_allowed` becomes three-state `True | False | None`. Match explicit deny patterns (`no refunds?`, `do not offer refunds?`, `refunds? are never`, `store credit only`, `final sale`, `no returns`) before allow patterns. `None` when neither matches — an unreadable policy must produce **no signal**, never a default.
- **D3** — `merchant_admitted_issue` matches admission patterns (`we acknowledge`, `our error`, `our mistake`, `was defective`, `we shipped the wrong`, `we failed to`, `will refund`, `have refunded`) and explicitly **excludes** bare politeness. Add `merchant_denies_claim` for `records show`, `we dispute`, `was delivered correctly`.
- **D4** — add the missing `photo` branch: `{"shows_damage": bool, "summary": str}`, true on `damag|broken|crack|torn|dent|shatter|mold|stain`, forced false by `no visible damage|intact|undamaged|as described`.
- **D5** — implement `receipt`: ISO and `DD Month YYYY` date extraction into `order_date`, `Ship(?:ped)? to (.+?)[.$]` into `shipping_address`.

Add a tolerant date helper used from here on:

```python
def _parse_date(s: Optional[str]) -> Optional[date]:
    """Returns None rather than raising. An unparseable date must yield NO signal."""
```

### 0.2 — Golden corpus (`backend/tests/goldens.json`)

The 15 cases from `seed.py` plus 10 adversarial ones, each labelled:

```json
{"id": "G016", "transaction_id": "TX2001",
 "card_member_address": "12 Pine Ave, Rivertown",
 "claim_type": "item_not_received",
 "claim_text": "Never arrived.",
 "evidence": [["merchant", "tracking_data", "Delivered to 99 Pine Ave, Rivertown. Signed by unknown recipient."]],
 "expected_winner": "card_member",
 "difficulty": "adversarial",
 "rationale": "same street name, different building; generic signee"}
```

The 10 adversarial cases must include: same-city/different-street delivery, unknown-signee delivery, a merchant who already refunded (the TX1014 shape), a genuine damage photo, a "Sorry, we cannot help you" denial, and an empty-box delivery (the TX1015 shape).

### 0.3 — Evaluation harness (`backend/app/evaluate.py`)

Runnable as `python -m app.evaluate` — no DB, no server, no network.

```python
def load_goldens(path: str = "tests/goldens.json") -> List[dict]
def replay(golden: dict) -> ReplayResult      # duck-typed stubs → score_case
def accuracy_report(results) -> dict          # overall + per claim_type
def bias_report(results) -> dict              # recall per party + bias_gap + attributed_bias
def calibration_report(results) -> dict       # mean confidence when correct vs incorrect
def latency_report(results) -> dict           # p50/p95 ms, parse + score + explain
def main() -> None                            # markdown tables to stdout
```

`bias_gap = abs(recall_card_member − recall_merchant)`. Given the disclosed-policy stance, also report **`attributed_bias`** — the share of the gap explained by named provisional-credit signals. The headline claim is *"our bias is 100% attributable to a disclosed rule,"* not *"our bias is zero."*

**Files:** modify `backend/app/llm.py`, `backend/requirements.txt` (add `pytest`); create `backend/tests/goldens.json`, `backend/app/evaluate.py`

**Acceptance:**
- `_extract_signee("Not signed by anyone.")` → `None`; `_extract_signee("signed by J. O'Brien on 2026-06-02.")` → `"J. O'Brien"`
- `"We do not offer refunds."` → `refund_allowed = False`
- `"Sorry, we cannot help you."` → `merchant_admitted_issue = False`
- `python -m app.evaluate` prints accuracy, per-claim-type breakdown, `bias_gap` and p95 latency

**Demo state:** working, materially more accurate parsing. **Record the baseline numbers before Phase 1.**

**Risk:** Python 3.9 in `backend/venv` — `X | None` and `@dataclass(slots=True)` are 3.10+. Stay on `Optional[...]` / `List[...]`, matching existing style.

---

## Phase 1 — Scorer correctness + disclosed fairness

**Advances:** task 2 · **Effort: 2.5h** · **Depends on:** Phase 0

### 1.1 — Three-state address matching (D6)

```python
def _parse_address(s: str) -> dict:
    """-> {"number": Optional[str], "street_tokens": set, "locality_tokens": set}"""

def _address_verdict(delivered_at: str, billing: str) -> str:
    """-> "match" | "mismatch" | "indeterminate"
    match:         house numbers both present AND equal, AND street-token Jaccard >= 0.5
    mismatch:      both parseable, and the above fails
    indeterminate: either side has no parseable house number -> NO SIGNAL, no points
    """
```

`indeterminate` is the key addition. Today the `else` branch at `scoring.py:45` silently converts an unparseable address into a 25-point card-member win. Neither party should gain from a string the parser could not read.

### 1.2 — Graded delivery confirmation (D1 continued)

Replace the bare `if signed_by:` at `scoring.py:59` with three outcomes:

| Condition | Signal | Weight | Favours |
|---|---|---|---|
| Signee surname matches `case.card_member_name` | `delivery_confirmation_named` | 20 | merchant |
| Real but different name | `delivery_confirmation_thirdparty` | 8 | merchant |
| Generic signee (filtered in Phase 0) | *none* | — | — |

### 1.3 — Evidence-mass-aware confidence (D8, D10)

```python
CONFIDENCE_SATURATION_POINTS = 60.0

def _confidence(cm: float, m: float) -> float:
    total = cm + m
    if total == 0:
        return 0.0                      # was a hardcoded 0.5 — see 1.4
    margin = abs(cm - m) / total
    mass = min(1.0, total / CONFIDENCE_SATURATION_POINTS)
    return round(margin * (0.5 + 0.5 * mass), 3)
```

TX1008's 15–0 drops from 1.00 → 0.625. TX1002's 45–0 lands at 0.875. Nothing saturates at 100% off a single signal again.

### 1.4 — Make the fairness policy explicit (D7, D10)

Per the locked decision, the pro-card-member default **stays** — but stops being invisible. Add two zero-weight disclosure signals:

```python
Signal("provisional_credit_no_evidence",
       "No conclusive evidence from either party. Issuer provisional-credit policy "
       "resolves undetermined cases in the card member's favour, pending merchant rebuttal.",
       0, None)

Signal("tie_break_provisional_credit",
       "Evidence is evenly balanced at {cm} points each. Issuer provisional-credit policy "
       "resolves ties in the card member's favour.",
       0, None)
```

Both render in the UI signal list (Phase 4) and are counted by `attributed_bias` in `evaluate.py`. The `item_not_received` no-evidence exemption at `scoring.py:96` keeps its existing code comment, promoted into a visible `detail` string.

### 1.5 — Deduplicate signals (D9)

Signals are emitted per evidence item with no dedup, so two uploads of the same tracking scan double the merchant's score to 90. Collapse by `(signal_name, detail)` before summing; when duplicates collapse, note the count in `detail` (`"corroborated by 2 documents"`) so corroboration is visible without being double-counted.

**Files:** modify `backend/app/scoring.py`

**Acceptance:**
- `_address_verdict("99 Pine Ave, Rivertown", "12 Pine Ave, Rivertown")` → `"mismatch"`
- `_address_verdict("Springfield 62704", "45 Oak Street, Springfield")` → `"indeterminate"`
- TX1003 and TX1009 no longer award the merchant a delivery confirmation; both rise well above 11% confidence
- No case reports 100% confidence off a single 15-point signal
- TX1004 emits `tie_break_provisional_credit` in its signal list
- Duplicate tracking evidence produces one signal, not two
- `python -m app.evaluate` shows accuracy up and `attributed_bias` accounting for the full gap

**Demo state:** working. This is the first phase whose improvement is visible on screen (confidence bars stop lying).

---

## Phase 2 — Auto-gather connectors

**Advances:** task 1 (the headline unbuilt claim), feeds task 3 · **Effort: 3h** · **Depends on:** Phase 0

"Auto-gathers transaction evidence" is the first line of the challenge brief and is currently not implemented at all — both parties paste text into a form. This phase is the single biggest demo-impact item in the plan.

### 2.1 — `backend/app/connectors.py`

Four simulated sources with claim-type routing and simulated latency.

```python
@dataclass
class ConnectorResult:
    source: str            # carrier_api | processor_ledger | merchant_policy_api | merchant_crm
    status: str            # hit | miss | skipped | error
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

def applicable_sources(claim_type: str) -> List[str]
def gather(case) -> List[ConnectorResult]
```

`processor_ledger` is the highest-value new source: it makes `duplicate_charge` and `refund_not_processed` decidable on *facts* rather than on who happened to upload something. Emit machine-friendly text so the offline parser is exact:

```
AMEX PROCESSOR LEDGER — TX1008 | AUTH x2 | SETTLE x2 ($999.00, $999.00) | GAP 3 min | REFUND none
```

Connectors must also emit ISO-8601 dates in carrier and receipt text, so Phase 3's return-window arithmetic has something parseable.

### 2.2 — Schema changes (`backend/app/models.py`)

- `EvidenceType` gains `processor_ledger`
- `Evidence` gains `source = Column(String, nullable=False, default="manual_upload")` and `auto_gathered = Column(Boolean, nullable=False, default=False)`
- New table:

```python
class GatherLog(Base):
    __tablename__ = "gather_logs"
    id, case_id (FK), source, status, latency_ms, summary, evidence_id (nullable FK), created_at
```

### 2.3 — Parser support (`backend/app/llm.py`)

Add `processor_ledger` to `PARSE_PROMPTS` and to `_mock_parse_evidence`:

```python
{"auth_count": int, "settlement_count": int, "settlement_amounts": [float],
 "minutes_between_settlements": Optional[int], "refund_issued": bool,
 "refund_amount": Optional[float]}
```

Mock regexes: `AUTH x(\d+)`, `SETTLE x(\d+)`, `\$([\d.]+)`, `GAP (\d+) min`, `REFUND (none|\$[\d.]+)`.

### 2.4 — API + seed

New route in `backend/app/routers/cases.py`:

```
POST /cases/{case_id}/gather  ->  GatherRunOut
```
```json
{"case_id": 8, "elapsed_ms": 2140, "evidence_created": 2,
 "entries": [
   {"source": "processor_ledger", "status": "hit", "latency_ms": 420,
    "evidence_id": 41, "evidence_type": "processor_ledger",
    "summary": "2 settlements of $999.00 found, 3 min apart"},
   {"source": "merchant_crm", "status": "miss", "latency_ms": 310,
    "evidence_id": null, "summary": "No correspondence on file"}]}
```

Every `hit` runs `llm.parse_evidence` and inserts `Evidence` with `auto_gathered=True`; **every** result including misses inserts a `GatherLog` row — recording what you asked and got nothing from is what makes an adverse inference fair later. Sets `case.status = evidence_gathering`.

`backend/app/schemas.py`: add `GatherEntryOut`, `GatherRunOut`; add `source` / `auto_gathered` to `EvidenceOut`; add `gather_log: List[GatherEntryOut] = []` to `CaseOut`.

`backend/app/seed.py`: change most cases' `evidence` lists to `[]` with `"auto_gather": True`, so the corpus is *produced by the connectors*. Keep 2–3 with manual evidence to show both paths coexisting.

**Files:** create `backend/app/connectors.py`; modify `models.py`, `llm.py`, `schemas.py`, `seed.py`, `routers/cases.py`

**Acceptance:** `POST /cases/8/gather` on a duplicate-charge case with zero prior evidence returns 2 hits and 1 miss and creates a `processor_ledger` Evidence row with `parsed_facts.settlement_count == 2` — with `ANTHROPIC_API_KEY` unset.

**Demo state:** working, and this is the moment the demo becomes compelling.

> ⚠️ **Schema migration.** `Base.metadata.create_all` does not ALTER existing tables. An existing `backend/disputes.db` will raise `OperationalError: no such column: evidence.source`. The file is gitignored, so: `rm backend/disputes.db && python -m app.seed`. Phase 5 adds columns too — **batch both migrations into one reseed** and never run it in the ten minutes before demoing.

---

## Phase 3 — Complete the scorecard

**Advances:** task 2 · **Effort: 3h** · **Depends on:** Phases 1, 2

### 3.1 — Declarative signal registry

Lift weights out of branch bodies into one table. This is what Phase 6 tunes and what goes on a deck slide.

```python
@dataclass(frozen=True)
class SignalSpec:
    weight: float
    favors: Optional[str]
    reason_code: Optional[str]      # consumed by Phase 5

SIGNAL_CATALOG: Dict[str, SignalSpec] = { ... }

def _emit(signals: list, name: str, detail: str) -> None:
    """Looks up weight and favors from the catalog — callers never hardcode either."""
```

### 3.2 — `duplicate_charge` (D11 — currently zero substantive signals)

| Signal | Favours | Weight | Trigger |
|---|---|---|---|
| `duplicate_settlement_confirmed` | card_member | 35 | `settlement_count >= 2` and amounts equal |
| `single_settlement_only` | merchant | 30 | `auth_count >= 2` but `settlement_count == 1` (dropped pre-auth) |
| `refund_already_issued` | merchant | 30 | `refund_issued` and `refund_amount == case.amount` |
| `settlements_far_apart` | merchant | 10 | `minutes_between_settlements > 1440` (two real orders) |

`refund_already_issued` fixes TX1014, which today rules for the card member 20–15 because the merchant email contains *"Sorry"* — while that same email states the refund was already made. A double refund.

### 3.3 — `not_as_described` (D11, D12)

| Signal | Favours | Weight | Trigger |
|---|---|---|---|
| `photo_shows_damage` | card_member | 25 | `photo.shows_damage is True` |
| `photo_shows_no_damage` | merchant | 15 | `shows_damage is False` and `submitted_by == "merchant"` |
| `within_return_window` | card_member | 15 | `receipt.order_date` + `policy.return_window_days` vs `case.created_at` |
| `outside_return_window` | merchant | 15 | same, inverted |

The 25/15 asymmetry is deliberate: damage visible in a photo is stronger evidence than its absence in one merchant-chosen frame. **Say this out loud on the deck** — it is a fairness *decision*, and Phase 6's asymmetry audit will allow-list it explicitly so it is documented in code rather than hidden in a branch.

`within_return_window` is the first consumer of both `return_window_days` and the `receipt` type, closing D12.

### 3.4 — `refund_not_processed` and `item_not_received` additions

| Signal | Favours | Weight |
|---|---|---|
| `no_refund_in_ledger` | card_member | 25 |
| `refund_posted_in_ledger` | merchant | 30 |
| `stale_in_transit` | card_member | 20 |

Ledger evidence outweighs policy text on both sides — a ledger states what happened, a policy states what should have. `stale_in_transit` (`status == "in_transit"`, last scan > 14 days before `case.created_at`) gives TX1010 a real verdict instead of `insufficient_evidence`.

### 3.5 — Rebalance procedural signals

Once the system auto-gathers on both parties' behalf, penalising a card member for "submitting no evidence" is indefensible. Narrow `no_card_member_evidence` to fire only where positive proof is genuinely obtainable and absent (`not_as_described` with no photo *and* no receipt) and drop **15 → 10**. Keep `no_merchant_evidence` at 15, but rewrite its `detail` to name the sources queried: *"Merchant policy API and merchant CRM were queried and returned no records."* An adverse inference is fair only when you can show you asked.

### 3.6 — Reseed and fix D23

Re-run `python -m app.seed` so TX1015 returns to unresolved, matching `README.md:67`. Confirm the empty-box case is no longer a resolved 100%-confidence merchant win — a signature proves a box arrived, not its contents. Either it stays unresolved for live demonstration, or `stale_in_transit`-style logic routes it to provisional credit.

**Files:** modify `backend/app/scoring.py`, `backend/app/seed.py`

**Acceptance:** all four `ClaimType` members produce at least one non-procedural signal on their golden cases; TX1014 flips to merchant; TX1013 is decided by the photo, not by `no_card_member_evidence`; TX1010 is no longer `insufficient_evidence`; TX1015 is not a resolved merchant win; `evaluate.py` shows accuracy up and `bias_gap` down.

**Demo state:** working. Every claim type now has a real evidentiary basis.

**Risk:** date arithmetic depends on `_parse_date` from Phase 0. A date the parser cannot read must produce **no** signal — never a default.

---

## Phase 4 — Real-time two-party interface

**Advances:** task 3 · **Effort: 3h** · **Depends on:** Phase 2

### 4.1 — Async gather so the UI can watch sources land

```
POST /cases/{case_id}/gather?async_mode=true   -> 202 {"case_id": 8, "sources_queued": 3}
GET  /cases/{case_id}/gather-log               -> List[GatherEntryOut]
```

Use FastAPI `BackgroundTasks`. Inside the task open a **fresh `SessionLocal()`** — never the request-scoped session from `get_db` — and commit after each connector with a 0.3–0.8s pause between them. `database.py` already sets `check_same_thread: False`.

### 4.2 — Frontend

`frontend/src/api.js` — add `gatherEvidence(caseId)` and `getGatherLog(caseId)`.

`frontend/src/pages/CaseDetail.jsx`:
- Poll `reload()` every 1500ms while `status !== "resolved"`; clear on unmount and on resolve. Polling beats SSE here — no new dependency, no reconnect logic, and at 1.5s it reads as live on video.
- Add an **"Auto-gather evidence"** button. This is the strongest 20 seconds of the demo video.
- **D14** — make the party toggle mean something. Card-member view labels merchant items *"Submitted by the merchant"* and vice versa; both views show the identical verdict under a shared **"Both parties see this identical explanation"** banner. That banner is the project's entire thesis.
- **D13** — re-enable resolution after new evidence. `submit_evidence` currently accepts evidence on a resolved case and never re-scores, and the UI hides the Resolve button, making the stale verdict permanent. Either auto-invalidate the verdict and revert status to `evidence_gathering`, or surface a "Re-resolve with new evidence" action.
- **D15** — add `id: int` to `SignalOut` in `schemas.py` and key on it. Auto-gather makes repeated signal names likely.

`frontend/src/components/GatherTimeline.jsx` (new) — one row per `GatherLog` entry: source, hit/miss/skipped pill, latency in ms. This renders "auto-gathered in 2.1s, not 3 weeks" as something *visible* rather than asserted.

### 4.3 — Use the dead status (D16)

Wire `CaseStatus.scored`: gather → `evidence_gathering`, signals persisted → `scored`, explanation attached → `resolved`. `StatusBadge.jsx` already has the label and colour, so no frontend change is needed.

**Files:** modify `routers/cases.py`, `models.py`, `schemas.py`, `api.js`, `CaseDetail.jsx`, `VerdictCard.jsx`; create `GatherTimeline.jsx`

**Acceptance:** two browser tabs on the same case — clicking auto-gather in one shows sources appearing in the other within ~2s with no manual refresh; the badge visibly steps `Filed → Gathering Evidence → Scored → Resolved`; submitting evidence after resolution no longer leaves a contradicted verdict.

**Demo state:** this is the phase where the product *looks* finished.

**Risk:** background-thread SQLite writes can raise `database is locked`. Unlikely at demo scale; if it appears, add `"timeout": 15` to `connect_args` in `database.py:6`.

---

## Phase 5 — Reason codes + counterfactual transparency

**Advances:** task 4 · **Effort: 2.5h** · **Depends on:** Phase 3

### 5.1 — `backend/app/reason_codes.py`

```python
REASON_CODES = {
    "C08": ("Goods/Services Not Received or Only Partially Received", "item_not_received"),
    "C31": ("Goods/Services Not As Described",                        "not_as_described"),
    "C32": ("Goods/Services Damaged or Defective",                    "not_as_described"),
    "C02": ("Credit Not Processed",                                   "refund_not_processed"),
    "P08": ("Duplicate Charge",                                       "duplicate_charge"),
    "C05": ("Goods/Services Cancelled",                               "item_not_received"),
}

def derive_reason_code(case, signals) -> Tuple[str, str]:
    """Deterministic: claim type gives the default; a fired signal can refine it
    (photo_shows_damage promotes C31 -> C32)."""
```

> ⚠️ **Verify every code string against the Amex Chargeback Reason Code guide linked in the challenge brief before building the deck.** It is one dict, so a correction is a two-minute edit — but shipping a wrong code on the slide that cites the guide is the worst possible unforced error.

`Verdict` gains `reason_code` and `reason_code_label` (both nullable `String`), mirrored into `VerdictOut`. **Batch this migration with Phase 2's reseed.**

### 5.2 — Counterfactual reasoning (`backend/app/scoring.py`)

```python
def minimal_flip_set(signals, winner) -> List[Signal]:
    """Smallest subset of winning signals whose removal changes the outcome."""

def counterfactual_statement(signals, winner, cm, m) -> str:
    """'This would have gone the other way if <X> had not been established (-25),
       or if the merchant had produced <Y> (+20).' Fully deterministic."""
```

**This is the highest transparency-per-hour item in the entire plan.** It is pure arithmetic over the scorecard, so it cannot hallucinate, it is auditable, and it answers the one question every losing party actually asks. Store as `Verdict.counterfactual` (new `Text` column) and render in `VerdictCard.jsx` beneath the signal list.

### 5.3 — Two-sided explanation (D17)

```python
def generate_explanation(case, signals, winner, confidence, reason_code_label) -> str
```

Pass **all** signals labelled `[WINNING]` / `[LOSING]` — `cases.py:65-66` currently filters to winners only, so the losing party's strongest point is never acknowledged. Add one prompt requirement: *"Include exactly one sentence acknowledging the strongest point made by the losing side and why it was outweighed."* An arbiter that never mentions the losing argument does not read as neutral.

Keep the hard constraint that the model may not restate or alter the verdict. Update `_mock_explanation` to the same three-part shape — **this is the path that actually runs in the demo**: ruling → strongest opposing point → confidence.

**Files:** create `backend/app/reason_codes.py`; modify `scoring.py`, `llm.py`, `models.py`, `schemas.py`, `routers/cases.py`, `VerdictCard.jsx`

**Acceptance:** every resolved verdict carries a reason code and label; the **offline** explanation names both a winning and a losing signal; TX1003's counterfactual reads approximately *"This would have gone to the merchant if the delivery had been signed for by a named recipient matching the cardholder (+20)."*

**Demo state:** working, and this is the phase that wins the "transparent reasoning" task outright.

---

## Phase 6 — Tests, evaluation, hardening, submission

**Advances:** task 5 + submission · **Effort: 2.5h** · **Depends on:** all

### 6.1 — `backend/tests/test_scoring.py`

One test per catalog signal, plus an explicit regression for every defect fixed:

- `test_address_same_city_different_street_is_mismatch` — `"99 Pine Ave, Rivertown"` vs `"12 Pine Ave, Rivertown"`
- `test_unparseable_address_is_indeterminate`
- `test_negated_signature_awards_nothing` — `"Not signed by anyone."`
- `test_generic_signee_awards_nothing` — `"Receiving Dept"`
- `test_no_refund_policy_is_not_refund_allowed`
- `test_apology_alone_is_not_admission`
- `test_single_signal_confidence_is_damped`
- `test_tie_emits_disclosure_signal`
- `test_duplicate_evidence_scores_once`
- `test_refund_already_issued_beats_apology_email` — TX1014

### 6.2 — `backend/tests/test_api.py`

`TestClient` end-to-end over `create → gather → resolve`, with `app.dependency_overrides[get_db]` pointed at a throwaway SQLite file so `disputes.db` is never touched. Include a regression for D13 (evidence after resolution).

### 6.3 — `backend/tests/test_fairness.py`

Two runnable fairness artifacts — these *are* the fairness deliverable:

1. **Catalog asymmetry audit.** Iterate `SIGNAL_CATALOG`, pair each card-member signal with its merchant counterpart, emit the weight-delta table, and fail on any *unjustified* asymmetry. Maintain an explicit allow-list (`photo_shows_damage` 25 vs `photo_shows_no_damage` 15; the provisional-credit rules) so every intentional asymmetry is documented in code.
2. **Party-swap test.** Construct synthetic cases identical except for `submitted_by` and assert score magnitudes mirror — except where an allow-listed policy applies. This is what catches unintended drift while permitting the disclosed one.

### 6.4 — Hardening (D18–D22)

Cheap, and each removes a live-demo failure mode:

- **D18** — wrap both `client.messages.create` calls in try/except so they fall back to the mock. Low priority offline, but ~10 minutes of insurance if a key ever lands in the environment.
- **D19** — `_extract_json` returning `{}` must fall back to the mock parser, not silently drop the evidence. Log a warning.
- **D20** — `Field(gt=0)` on `amount`, `min_length=1` on strings, unique constraint on `transaction_id`.
- **D21** — add `DisputeCase.id.desc()` as a tiebreaker so the list stops reshuffling between refreshes.
- **D22** — allow both `5173` and `5174` in `main.py:14`, or read from an env var. Vite falls forward when the port is taken, and the failure mode is an opaque `TypeError: Failed to fetch`.

### 6.5 — Metrics endpoint

`GET /metrics` in `main.py` returning the latest evaluation summary — accuracy, `bias_gap`, `attributed_bias`, p95 latency — so the UI can render a "Pipeline health" card. One screenshot, and task 5 stops being unevidenced.

### 6.6 — Submission artifacts

- Rewrite the `README.md` scorecard table (lines 45–58) from the real `SIGNAL_CATALOG`
- Correct `README.md:67` — it currently claims verification "via direct API checks and a full browser walkthrough," which is not a test suite
- Move delivered roadmap items into the body
- Add the reseed instruction (`rm backend/disputes.db && python -m app.seed`) to Getting Started
- **Demo video** on the auto-gather path: file case → auto-gather → sources land in the timeline → resolve → verdict with reason code, counterfactual, and both-party banner
- **Deck slides**: the signal catalog, the before/after metrics table, the disclosed-fairness slide (the provisional-credit policy stated as a deliberate choice), and the competitive-positioning slide

**Acceptance:** `pytest backend/tests -q` green with `ANTHROPIC_API_KEY` unset; `python -m app.evaluate` reports accuracy ≥ 90% on the golden set, `attributed_bias` accounting for the full directional gap, and p95 end-to-end latency under 3s offline.

---

## Sequencing

| Phase | Title | Hours | Cumulative | Demo-safe after? |
|---|---|---|---|---|
| 0 | Trustworthy inputs + measured baseline | 3.5 | 3.5 | ✅ |
| 1 | Scorer correctness + disclosed fairness | 2.5 | 6.0 | ✅ |
| 2 | Auto-gather connectors | 3.0 | 9.0 | ✅ (after reseed) |
| 3 | Complete the scorecard | 3.0 | 12.0 | ✅ |
| 4 | Real-time two-party interface | 3.0 | 15.0 | ✅ |
| 5 | Reason codes + counterfactual transparency | 2.5 | 17.5 | ✅ (after reseed) |
| 6 | Tests, evaluation, hardening, submission | 2.5 | 20.0 | ✅ |

**If time runs out**, the highest-value stopping points are after **Phase 2** (headline auto-gather claim is real, and inputs are trustworthy) or after **Phase 4** (product looks finished). Stopping mid-phase is the only genuinely bad outcome.

## Cross-cutting risks

| Risk | Mitigation |
|---|---|
| Python 3.9 in `backend/venv` | No `X \| None`, no `slots=True`. Use `Optional[...]` / `List[...]`, matching existing style. |
| Two schema-breaking phases (2 and 5) | Batch both column sets into a single `rm backend/disputes.db && python -m app.seed`. Never within 10 minutes of a demo. |
| Mock parser is the whole AI story offline | Phase 0 is non-negotiable and must come first. Every downstream signal reads its output. |
| Scorecard weights are hand-tuned | Acknowledge on the deck. `goldens.json` + `evaluate.py` make tuning *measurable*, which is the honest claim. Do not claim a trained model. |
| Accuracy figure is self-labelled | State it plainly: 25 cases labelled by the author. The measurement discipline is the contribution, not the number. |

## Task coverage

| Challenge task | Phases | Evidence at submission |
|---|---|---|
| 1. Auto-collect and parse evidence | 0, 2 | `connectors.py`, 4 sources, gather timeline with latencies |
| 2. Fair-weighing model | 1, 3 | `SIGNAL_CATALOG`, 4 claim types, disclosed provisional-credit policy |
| 3. Real-time two-party interface | 4 | 1.5s polling, party toggle, shared-explanation banner |
| 4. Transparent reasoning | 5 | Signal breakdown, Amex reason code, deterministic counterfactual, two-sided explanation |
| 5. Test and optimise | 0, 6 | pytest suite, `evaluate.py`, accuracy + calibration + fairness reports, `/metrics` |
