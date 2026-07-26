
import { PARTY as PARTY_COLOR, PARTY_LABEL } from "../theme";

// Below this the margin is too thin relative to the evidence behind it for the
// scorecard to be treated as having settled anything.
const LOW_CONFIDENCE = 0.35;

// A zero-weight signal that favours nobody is a disclosed policy rule, not filler.
// It is how the issuer's provisional-credit stance is stated to both parties, so it
// is rendered as a first-class row rather than filtered out as 0-point noise.
const isDisclosure = (s) => s.weight === 0 && !s.favors;

/** Reasons the scorecard has for doubting its own ruling. Presentational only — the
 *  scorer is untouched; everything here is derived from what the case already returns. */
function humanReviewReason(verdict, signals, evidence) {
  const losing = verdict.winner === "card_member" ? "merchant" : "card_member";

  // Only what the party actually filed. Auto-gathered records are attributed to a
  // party for scoring purposes (connectors.py) but they are not that party's argument,
  // so counting them here would report someone as having filed evidence they never sent.
  const filed = (evidence ?? []).filter((e) => e.submitted_by === losing && !e.auto_gathered);

  // The empty-box shape: a party put something on file and NO rule in the scorecard
  // read it — not one signal, for them or against them. That is a gap in the rules
  // rather than a finding, and it is invisible in the score alone. Evidence that was
  // read and told against them is a different thing entirely and must not trigger this.
  // Every contributing document, not just the first. A corroborating filing collapses
  // into an existing signal, and counting only the first made it look unexamined.
  const read = new Set((signals ?? []).flatMap((s) => s.evidence_ids ?? []));
  const unread = filed.filter((e) => !read.has(e.id));

  if (filed.length > 0 && unread.length === filed.length) {
    const n = filed.length;
    return (
      `${PARTY_LABEL[losing]} filed ${n} item${n === 1 ? "" : "s"} of evidence that no rule in the ` +
      `scorecard reads, so ${n === 1 ? "it" : "they"} scored zero either way. That is a gap in the ` +
      `rules, not a finding against them — their account has not been weighed.`
    );
  }

  if (verdict.confidence < LOW_CONFIDENCE) {
    return (
      `Confidence is ${(verdict.confidence * 100).toFixed(0)}%. The two sides are close enough on ` +
      `the evidence on file that this ruling should not be treated as settled.`
    );
  }

  return null;
}

export default function VerdictCard({ verdict, signals, evidence }) {
  if (!verdict) return null;

  const total = verdict.card_member_score + verdict.merchant_score;
  const cmPct = total > 0 ? (verdict.card_member_score / total) * 100 : 50;
  const reviewReason = humanReviewReason(verdict, signals, evidence);

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 20, background: "white" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>
          Ruling: <span style={{ color: PARTY_COLOR[verdict.winner] }}>{PARTY_LABEL[verdict.winner]}</span>
        </h3>
        <span style={{ fontSize: "0.85rem", color: "#6b7280" }}>
          Confidence {(verdict.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {verdict.reason_code && (
        <div style={{ marginTop: 8, fontSize: "0.78rem", color: "#374151" }}>
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontWeight: 700,
              background: "#eef2ff",
              border: "1px solid #c7d2fe",
              borderRadius: 4,
              padding: "1px 6px",
              marginRight: 6,
            }}
          >
            {verdict.reason_code}
          </span>
          {verdict.reason_code_label}
        </div>
      )}

      <div
        style={{
          display: "flex",
          height: 10,
          borderRadius: 6,
          overflow: "hidden",
          margin: "12px 0",
          background: "#f3f4f6",
        }}
      >
        <div style={{ width: `${cmPct}%`, background: PARTY_COLOR.card_member }} />
        <div style={{ width: `${100 - cmPct}%`, background: PARTY_COLOR.merchant }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "#6b7280" }}>
        <span>Card member {verdict.card_member_score.toFixed(0)} pts</span>
        <span>Merchant {verdict.merchant_score.toFixed(0)} pts</span>
      </div>

      {reviewReason && (
        <div
          style={{
            marginTop: 16,
            background: "#fffbeb",
            border: "1px solid #fcd34d",
            borderRadius: 8,
            padding: "10px 12px",
          }}
        >
          <div style={{ fontWeight: 700, fontSize: "0.85rem", color: "#92400e" }}>
            Recommended for human review
          </div>
          <div style={{ fontSize: "0.85rem", color: "#78350f", marginTop: 4, lineHeight: 1.5 }}>{reviewReason}</div>
        </div>
      )}

      <p style={{ marginTop: 16, lineHeight: 1.5 }}>{verdict.explanation}</p>

      {signals?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "#6b7280", marginBottom: 6 }}>
            SCORECARD SIGNALS
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
            {signals.map((s) =>
              isDisclosure(s) ? (
                <li
                  key={s.id}
                  style={{
                    fontSize: "0.85rem",
                    borderLeft: "3px dashed #6b7280",
                    background: "#f9fafb",
                    borderRadius: "0 6px 6px 0",
                    padding: "6px 8px",
                  }}
                >
                  <div
                    style={{
                      fontSize: "0.7rem",
                      fontWeight: 700,
                      color: "#6b7280",
                      letterSpacing: "0.03em",
                      marginBottom: 2,
                    }}
                  >
                    DISCLOSED POLICY &middot; 0 PTS
                  </div>
                  <span>{s.detail}</span>
                </li>
              ) : (
                <li
                  key={s.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.85rem",
                    borderLeft: `3px solid ${s.favors ? PARTY_COLOR[s.favors] : "#9ca3af"}`,
                    paddingLeft: 8,
                  }}
                >
                  <span>{s.detail}</span>
                  <span style={{ color: "#6b7280", whiteSpace: "nowrap", marginLeft: 8 }}>
                    {s.weight > 0 ? `+${s.weight}` : "—"} {s.favors ? PARTY_LABEL[s.favors] : ""}
                  </span>
                </li>
              )
            )}
          </ul>
        </div>
      )}

      {verdict.counterfactual && (
        <div
          style={{
            marginTop: 14,
            background: "#f8fafc",
            border: "1px dashed #cbd5e1",
            borderRadius: 8,
            padding: "10px 12px",
          }}
        >
          <div style={{ fontSize: "0.7rem", fontWeight: 700, color: "#475569", letterSpacing: "0.03em" }}>
            WHAT WOULD HAVE CHANGED THIS
          </div>
          <div style={{ fontSize: "0.85rem", color: "#334155", marginTop: 4, lineHeight: 1.5 }}>
            {verdict.counterfactual}
          </div>
        </div>
      )}
    </div>
  );
}
