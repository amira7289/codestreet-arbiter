import { useState } from "react";

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

export default function EvidenceForm({ submittedBy, onSubmit }) {
  const [evidenceType, setEvidenceType] = useState(EVIDENCE_TYPES[0]);
  const [rawContent, setRawContent] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!rawContent.trim()) return;
    setBusy(true);
    try {
      await onSubmit({ submitted_by: submittedBy, evidence_type: evidenceType, raw_content: rawContent });
      setRawContent("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "grid", gap: 8, marginTop: 12 }}>
      <select value={evidenceType} onChange={(e) => setEvidenceType(e.target.value)}>
        {EVIDENCE_TYPES.map((t) => (
          <option key={t} value={t}>
            {t.replace(/_/g, " ")}
          </option>
        ))}
      </select>
      <textarea
        rows={3}
        placeholder="Paste or describe the evidence (e.g. tracking update, policy text, email)..."
        value={rawContent}
        onChange={(e) => setRawContent(e.target.value)}
      />
      <button type="submit" disabled={busy}>
        {busy ? "Submitting..." : "Submit Evidence"}
      </button>
    </form>
  );
}
