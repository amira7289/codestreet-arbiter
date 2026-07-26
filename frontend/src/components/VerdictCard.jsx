const PARTY_COLOR = { card_member: "#1d4ed8", merchant: "#b45309" };
const PARTY_LABEL = { card_member: "Card Member", merchant: "Merchant" };

export default function VerdictCard({ verdict, signals }) {
  if (!verdict) return null;

  const total = verdict.card_member_score + verdict.merchant_score;
  const cmPct = total > 0 ? (verdict.card_member_score / total) * 100 : 50;

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 20, marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>
          Ruling: <span style={{ color: PARTY_COLOR[verdict.winner] }}>{PARTY_LABEL[verdict.winner]}</span>
        </h3>
        <span style={{ fontSize: "0.85rem", color: "#6b7280" }}>
          Confidence {(verdict.confidence * 100).toFixed(0)}%
        </span>
      </div>

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

      <p style={{ marginTop: 16, lineHeight: 1.5 }}>{verdict.explanation}</p>

      {signals?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "#6b7280", marginBottom: 6 }}>
            SCORECARD SIGNALS
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
            {signals.map((s) => (
              <li
                key={s.signal_name}
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
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
