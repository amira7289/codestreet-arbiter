import { STATUS_STYLE } from "../theme";

export default function StatusBadge({ status }) {
  const s = STATUS_STYLE[status] ?? { fg: "#53565A", bg: "#EEF1F4", label: status };
  return (
    <span className="pill" style={{ background: s.bg, color: s.fg }}>
      <span className="pill__dot" />
      {s.label}
    </span>
  );
}
