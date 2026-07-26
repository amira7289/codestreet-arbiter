const SOURCE_LABELS = {
  carrier_api: "Carrier API",
  processor_ledger: "Processor ledger",
  merchant_policy_api: "Merchant policy API",
  merchant_crm: "Merchant CRM",
};

const STATUS_COLOR = {
  hit: "#15803d",
  miss: "#6b7280",
  skipped: "#b45309",
  error: "#b91c1c",
};

function Pill({ status }) {
  const color = STATUS_COLOR[status] ?? "#6b7280";
  return (
    <span
      style={{
        background: `${color}1a`,
        color,
        border: `1px solid ${color}40`,
        borderRadius: "999px",
        padding: "1px 8px",
        fontSize: "0.7rem",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.03em",
        whiteSpace: "nowrap",
      }}
    >
      {status}
    </span>
  );
}

export default function GatherTimeline({ entries, pending, run }) {
  const rows = entries ?? [];
  if (rows.length === 0 && !pending) return null;

  // A miss is as much a result as a hit: an adverse inference against a party is only
  // fair when the record shows their systems were asked and returned nothing.
  //
  // The header describes the CURRENT run, not the whole log. Summing every historical
  // row reported "9 sources queried · 5.4s" after three gathers of a 3-source case,
  // which overstates both the breadth and the cost of a single run. With no run
  // started in this session — a page opened on an already-gathered case — the log is
  // labelled as history and no elapsed time is claimed for it.
  const current = run ? rows.slice(run.baseline) : null;
  const summary = current
    ? `${current.length} source${current.length === 1 ? "" : "s"} queried · ` +
      `${(current.reduce((sum, e) => sum + e.latency_ms, 0) / 1000).toFixed(1)}s`
    : `${rows.length} entr${rows.length === 1 ? "y" : "ies"} on file`;

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 16, marginTop: 16, background: "white" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "#6b7280", letterSpacing: "0.03em" }}>
          EVIDENCE GATHERING LOG
        </div>
        <div style={{ fontSize: "0.75rem", color: "#6b7280" }}>{summary}</div>
      </div>

      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
        {rows.map((e, i) => (
          <li
            key={`${e.source}-${i}`}
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 10,
              fontSize: "0.85rem",
              padding: "6px 0",
              borderTop: i === 0 ? "none" : "1px solid #f3f4f6",
            }}
          >
            <span style={{ fontWeight: 600, minWidth: 150 }}>
              {SOURCE_LABELS[e.source] ?? e.source.replace(/_/g, " ")}
            </span>
            <Pill status={e.status} />
            <span style={{ color: "#6b7280", flex: 1 }}>{e.summary}</span>
            <span style={{ color: "#6b7280", fontSize: "0.75rem", whiteSpace: "nowrap" }}>{e.latency_ms} ms</span>
          </li>
        ))}
      </ul>

      {pending > 0 && (
        <div style={{ marginTop: 8, fontSize: "0.8rem", color: "#b45309" }}>
          Querying {pending} more source{pending === 1 ? "" : "s"}&hellip;
        </div>
      )}
    </div>
  );
}
