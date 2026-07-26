# Frictionless Dispute & Chargeback Resolution
### Presentation deck — 13 slides

Speaker notes sit under each slide in italics. Timings assume a 7-minute pitch plus a 3-minute demo.

---

## Slide 1 — Title

# Frictionless Dispute & Chargeback Resolution

**A neutral arbiter that shows both sides the same reasoning.**

Weeks → seconds. 95% accurate on a labelled corpus. Every point traceable to a named rule.

*Team / CodeStreet 2026*

> *Lead with the one-line claim. Don't explain chargebacks yet — the room knows.*

---

## Slide 2 — The problem

A card member disputes a charge. Then:

- The merchant gets **weeks** to respond
- A human analyst reads shipping records, policies, correspondence
- A verdict arrives with **no explanation**
- Neither party ever sees *why*

**This is not fraud detection.** The transaction is genuine. The disagreement is about what happened next — was it delivered, was it as described, was the refund processed.

Two legitimate claims. Someone has to arbitrate.

> *The "not fraud" line matters. Half the field will have built a fraud classifier for a problem statement that explicitly isn't one.*

---

## Slide 3 — Why this space is empty

| What exists | What it does | Whose side |
|---|---|---|
| Chargeflow, Justt, ChargePay, ChatFin | Auto-drafts evidence responses to win disputes | **Merchant** |
| Visa CE 3.0 + Verifi, Mastercard Ethoca | Shares data to prevent escalation | Neither — it's plumbing |
| Risk dashboards | Explains scores to **internal analysts** | The institution |

Nobody occupies the neutral, two-sided, transparent seat.

**An issuer-run arbiter that hands both parties the same evidence-based explanation for the same verdict.**

> *This is the differentiation slide. The market has "explainability" — but it means dashboards for staff, not an explanation given to the person who lost.*

---

## Slide 4 — The one architectural commitment

> **The LLM extracts facts and narrates. A deterministic scorecard decides.**

```
messy evidence  ──LLM──▶  typed facts  ──scorecard──▶  verdict  ──LLM──▶  narration
                                            ▲
                                   the decision lives HERE
                                   25 weights, one table
```

The decision never sits in the model.

Consequences: every point traces to a named rule · verdicts are reproducible · the whole thing is testable · we can prove fairness properties instead of asserting them.

> *If you only remember one slide, this is it. It's also the answer to "how do you know the AI isn't hallucinating the verdict" — it can't, it doesn't make the verdict.*

---

## Slide 5 — Task 1: Auto-gather

Filing a dispute triggers a fan-out across **four routed sources**:

| Source | Supplies |
|---|---|
| Carrier API | delivery status, address, signee, last scan |
| **Amex processor ledger** | auth/settlement counts, amounts, refunds |
| Merchant policy API | return window, refund terms |
| Merchant CRM | correspondence |

**Misses are logged as carefully as hits.** An adverse inference against a party is only fair when the record shows their systems were asked and returned nothing.

29 of 33 evidence items in the seeded corpus are auto-gathered. Zero manual input required.

> *Demo hook: the gather timeline filling in row by row is the strongest 20 seconds of the video.*

---

## Slide 6 — Task 2: The scorecard

25 signals in one auditable table. A selection:

| Signal | Favours | Weight |
|---|---|---|
| `duplicate_settlement_confirmed` | Card member | 35 |
| `not_shipped` | Card member | 30 |
| `refund_already_issued` | Merchant | 30 |
| `address_match` / `address_mismatch` | either | 25 |
| `photo_shows_damage` | Card member | 25 |
| `delivery_confirmation_named` | Merchant | 20 |
| `delivery_confirmation_thirdparty` | Merchant | **8** |

Confidence is **evidence-mass aware**: `margin × (0.5 + 0.5 × min(1, total/60))`.
A 15–0 split off one procedural signal reports **62%**, not 100%.

> *Point at the 20 vs 8 split: a parcel signed for by the cardholder is not the same as one signed for by "Receiving Dept". That distinction alone fixed two cases.*

---

## Slide 7 — Fairness, stated out loud

**We do not claim the scorecard is unbiased.**

Ambiguous cases resolve to the card member — matching issuer provisional-credit practice. That default is deliberate, and it is **disclosed on the verdict itself** as a zero-weight signal, not hidden in a `>=` operator.

> The target is not `bias_gap == 0`.
> The target is that **every point of directional bias traces to a rule we state out loud.**

Measured: verdicts favour the card member **56%** of the time; the human labels do too. **Zero** errors favour the card member.

`test_fairness.py` fails the build on any weight asymmetry not documented with a written justification.

> *This is the slide that separates a hackathon project from a demo. Judges will push on fairness — the answer is "here's the audit, it runs in CI".*

---

## Slide 8 — Task 3: Both sides, live

Card member and merchant panels render **side by side**, both updating live.

- Each side sees its own filings *and* everything the other side filed
- One shared verdict beneath a banner: **"Both parties see this identical explanation"**
- 1.5s polling while open; 5s once resolved — because the other party can still file evidence that withdraws the ruling
- New evidence on a resolved case **withdraws the verdict** and re-opens the case

*A verdict must never outlive the evidence set it was computed from.*

> *Open two browser tabs on stage. File evidence in one; the other updates. That's the "real-time, two-sided" task demonstrated rather than described.*

---

## Slide 9 — Task 4: Four layers of reasoning

1. **Signal breakdown** — every point, named, attributed to the document it came from
2. **Amex reason code** — C02 / C08 / C31 / C32 / P08, derived deterministically
3. **The counterfactual** — *"This would have gone to the card member if these had not been established (−45 points): …"*
4. **The narrative** — required to name the losing side's strongest point and why it was outweighed

The counterfactual is **arithmetic over the scorecard**, not generation. It cannot hallucinate.

Plus: a **"Recommended for human review"** banner when a party filed evidence no rule reads, or confidence is under 35%.

> *Layer 3 is the one to dwell on. It answers the only question a losing party actually asks — and because it's arithmetic, we can prove it's correct. It was brute-forced against 3,000 randomised scorecards, plus 4,000 in an earlier pass.*

---

## Slide 10 — Task 5: Measured, not asserted

```
pytest backend/tests -q       78 tests
python -m app.evaluate        full report
GET /metrics                  the same numbers, live
```

25-case labelled corpus: 15 seeded + **10 adversarial**, each built to break a specific heuristic.

| Metric | Value |
|---|---|
| **Accuracy** | **95%** (21/22 arbitrable) |
| Adversarial subset | **100%** (9/9) |
| Errors favouring card member | **0** |
| Confidently wrong (≥80%) | **0** |
| p95 latency (parse + score + explain) | **0.2 ms** |

Progress across phases: **82% → 91% → 95%**. Calibration separation **0.02 → 0.17**. Verdicts at 100% confidence off a single signal: **11 → 0**.

> *The before/after column is the point. We didn't assert improvement, we measured a baseline first and then moved it.*

---

## Slide 11 — Demo

1. Open a filed dispute — no evidence yet
2. Click **Auto-gather** → four sources report live, hits and misses, with latencies
3. Click **Resolve** → verdict, reason code, signal breakdown, counterfactual
4. Switch to the other party's panel → **identical explanation**
5. File contradicting evidence → **verdict withdrawn**, case re-opens
6. `GET /metrics` → the accuracy and fairness numbers, live

> *Rehearse step 5. It's counter-intuitive and it's the most convincing thing in the build: the system refuses to keep a ruling it can no longer justify.*

---

## Slide 12 — What we know is wrong

- **The 25 labels are our judgement**, not adjudicated ground truth. The measurement discipline is the contribution; the number is only as good as the corpus.
- **Connector latencies are synthetic** — a simulation of network cost, not a measurement of it.
- **One known failure**: a merchant who files a non-committal message dodges the adverse inference for silence while the card member still carries the no-evidence penalty. Filing something meaningless is currently rewarded.
- **No abstain verdict.** Genuinely undecidable cases still produce a winner, flagged for review rather than withheld.

> *Do not skip this slide. A system that reports its own uncertainty is the whole thesis — demonstrating it about our own work is the strongest possible version of the argument. It also pre-empts the questions.*

---

## Slide 13 — Next

**Near term**
- Abstain as a first-class verdict for genuinely undecidable cases
- Adverse inference weighted by whether a filing was *probative*, not merely present
- Larger labelled corpus; tune weights against it rather than by hand

**The real unlock**
Every resolved dispute is a labelled example. The scorecard stays deterministic — but its weights can be fitted to outcomes, and the counterfactual tells you exactly which signal to collect next.

**Explainability isn't a constraint on accuracy here. It's the training signal.**

> *Close on that line.*

---

## Appendix — questions to expect

**"Why not just train a classifier?"**
Because the deliverable is a verdict two parties have to accept. A classifier gives a number nobody can argue with — literally. The scorecard gives a receipt. And with 25 labels, a classifier would overfit instantly; the honest move at this data volume is a transparent model with measured behaviour.

**"How do you know the LLM isn't deciding?"**
It structurally cannot. `score_case` takes typed facts and returns the verdict; the model is never called between those two points. Delete the API key and the verdicts are byte-identical — that's how the whole test suite runs.

**"What if the LLM extracts a fact wrong?"**
Then the scorecard is wrong, visibly, on a named signal pointing at a named document. That's the failure mode we chose: wrong and inspectable beats wrong and opaque. The offline parser returns `None` rather than guessing whenever it can't establish a fact.

**"56% of verdicts favour the card member — isn't that bias?"**
The labels are 56% too. And of the errors, zero favour the card member. The one directional rule we do have is provisional credit, and it's printed on the verdict.

**"Is this production-ready?"**
No. Single process, simulated connectors, 25 labels. What is production-ready is the shape: the deterministic core, the audit, and the measurement harness.
