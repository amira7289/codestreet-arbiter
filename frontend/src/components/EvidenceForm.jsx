import { useState } from "react";
import { PARTY, PARTY_LABEL, titleCase } from "../theme";

// Must stay in step with models.EvidenceType. processor_ledger was missing, so a party
// could not manually file the one evidence type carrying the heaviest weights in the
// catalog — the settlement record that decides duplicate-charge and refund disputes.
const EVIDENCE_TYPES = [
  "tracking_data",
  "processor_ledger",
  "policy_text",
  "receipt",
  "email",
  "chat_log",
  "photo",
];

// What each type should actually contain, shown in the field rather than left for the
// filer to guess. The parser reads specific shapes, so telling people what it expects
// is the difference between evidence that scores and evidence that reads as nothing.
const PLACEHOLDER = {
  tracking_data: "Delivered 2026-06-04 to 12 Pine Ave, Rivertown, signed by M. Torres.",
  processor_ledger: "AMEX PROCESSOR LEDGER — TX1002 | AUTH x2 | SETTLE x2 ($150.00, $150.00) | GAP 3 min | REFUND none",
  policy_text: "Items may be returned within 30 days of delivery for a full refund.",
  receipt: "Order placed 2026-06-01. Ship to 12 Pine Ave, Rivertown.",
  email: "We acknowledge the unit was defective and will arrange a replacement.",
  chat_log: "Support: we've checked the order and the item was dispatched on time.",
  photo: "Photo shows the vase shattered into several pieces inside the box.",
};

export default function EvidenceForm({ submittedBy, onSubmit }) {
  const [evidenceType, setEvidenceType] = useState(EVIDENCE_TYPES[0]);
  const [rawContent, setRawContent] = useState("");
  const [busy, setBusy] = useState(false);

  const empty = !rawContent.trim();

  async function handleSubmit(e) {
    e.preventDefault();
    if (empty || busy) return;
    setBusy(true);
    try {
      await onSubmit({ submitted_by: submittedBy, evidence_type: evidenceType, raw_content: rawContent });
      setRawContent("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="stack stack--sm" style={{ marginTop: 10 }}>
      <label className="field">
        <span className="field__label">Evidence type</span>
        <select value={evidenceType} onChange={(e) => setEvidenceType(e.target.value)}>
          {EVIDENCE_TYPES.map((t) => (
            <option key={t} value={t}>{titleCase(t)}</option>
          ))}
        </select>
      </label>

      <label className="field">
        <span className="field__label">Document</span>
        <textarea
          rows={3}
          placeholder={PLACEHOLDER[evidenceType]}
          value={rawContent}
          onChange={(e) => setRawContent(e.target.value)}
        />
      </label>

      <div className="row row--between" style={{ gap: 10 }}>
        <span className="muted" style={{ fontSize: "0.75rem" }}>
          {empty
            ? "Filed evidence is parsed immediately and re-scores the case."
            : `Filing as the ${PARTY_LABEL[submittedBy].toLowerCase()}.`}
        </span>
        <button
          type="submit"
          className="btn btn--party"
          disabled={busy || empty}
          style={{ "--btn-tint": PARTY[submittedBy] }}
        >
          {busy ? "Submitting…" : `Submit as ${PARTY_LABEL[submittedBy].toLowerCase()}`}
        </button>
      </div>
    </form>
  );
}
