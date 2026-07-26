const LABELS = {
  filed: "Filed",
  evidence_gathering: "Gathering Evidence",
  scored: "Scored",
  resolved: "Resolved",
};

const COLORS = {
  filed: "#6b7280",
  evidence_gathering: "#b45309",
  scored: "#1d4ed8",
  resolved: "#15803d",
};

export default function StatusBadge({ status }) {
  return (
    <span
      style={{
        background: `${COLORS[status]}1a`,
        color: COLORS[status],
        border: `1px solid ${COLORS[status]}40`,
        borderRadius: "999px",
        padding: "2px 10px",
        fontSize: "0.75rem",
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {LABELS[status] ?? status}
    </span>
  );
}
