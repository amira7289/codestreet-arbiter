/**
 * Inline SVG charts. No charting library, no runtime dependency.
 *
 * House rules, applied uniformly:
 *  - thin marks, 4px rounded data-ends anchored to the baseline, 2px surface gaps
 *  - one axis, never two scales on one plot
 *  - a legend whenever there are two or more series; selective direct labels only
 *  - text wears ink tokens, never the series colour — a colour swatch beside a
 *    label carries identity, so the chart never depends on colour alone
 *  - every plot has a hover layer and a table view behind a toggle
 */
import { useId, useState } from "react";
import { INK, SURFACE, titleCase } from "../theme";

const GAP = 2;

function Figure({ title, subtitle, legend, table, children }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className="chart">
      <figcaption className="chart__head">
        <div>
          <h3 className="chart__title">{title}</h3>
          {subtitle && <p className="chart__subtitle">{subtitle}</p>}
        </div>
        {table && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setShowTable((v) => !v)}
            aria-expanded={showTable}
          >
            {showTable ? "Chart" : "Table"}
          </button>
        )}
      </figcaption>

      {showTable && table ? (
        <div className="chart__table-wrap">
          <table className="table table--compact">
            <thead>
              <tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i}>{r.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          {children}
          {legend && legend.length > 1 && (
            <ul className="legend">
              {legend.map((l) => (
                <li key={l.label}>
                  <span className="legend__swatch" style={{ background: l.color }} aria-hidden="true" />
                  {l.label}
                  {l.value != null && <span className="legend__value">{l.value}</span>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </figure>
  );
}

/** Donut. Identity across a small set of parts of one whole, with the total as the
 *  hero number in the hole — the number people actually came for. */
export function DonutChart({ title, subtitle, data, centerLabel, centerValue }) {
  const [hover, setHover] = useState(null);
  const id = useId();
  const size = 190;
  const stroke = 26;
  const r = (size - stroke) / 2 - 2;
  const c = 2 * Math.PI * r;
  const total = data.reduce((s, d) => s + d.value, 0) || 1;

  let offset = 0;
  const arcs = data.map((d) => {
    const frac = d.value / total;
    // A 2px surface gap between neighbouring segments so they read as separate marks.
    const len = Math.max(0, frac * c - GAP);
    const arc = { ...d, len, offset, frac };
    offset += frac * c;
    return arc;
  });

  return (
    <Figure
      title={title}
      subtitle={subtitle}
      legend={data.map((d) => ({ label: d.label, color: d.color, value: d.value }))}
      table={{
        columns: ["Segment", "Count", "Share"],
        rows: data.map((d) => [d.label, d.value, `${((d.value / total) * 100).toFixed(0)}%`]),
      }}
    >
      <div className="donut">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
             aria-label={`${title}: ${data.map((d) => `${d.label} ${d.value}`).join(", ")}`}>
          <g transform={`translate(${size / 2} ${size / 2}) rotate(-90)`}>
            <circle r={r} fill="none" stroke={SURFACE.sunken} strokeWidth={stroke} />
            {arcs.map((a) => (
              <circle
                key={a.label}
                r={r}
                fill="none"
                stroke={a.color}
                strokeWidth={hover === a.label ? stroke + 4 : stroke}
                strokeDasharray={`${a.len} ${c - a.len}`}
                strokeDashoffset={-a.offset}
                strokeLinecap="butt"
                onMouseEnter={() => setHover(a.label)}
                onMouseLeave={() => setHover(null)}
                style={{ transition: "stroke-width 120ms ease" }}
              />
            ))}
          </g>
          <text x="50%" y="47%" textAnchor="middle" className="donut__value">{centerValue}</text>
          <text x="50%" y="60%" textAnchor="middle" className="donut__label">{centerLabel}</text>
        </svg>
        <div className="donut__readout" aria-live="polite">
          {hover
            ? (() => {
                const a = arcs.find((x) => x.label === hover);
                return <><strong>{a.label}</strong> · {a.value} ({(a.frac * 100).toFixed(0)}%)</>;
              })()
            : <span className="muted">Hover a segment for detail</span>}
        </div>
      </div>
      <span hidden id={id} />
    </Figure>
  );
}

/** Horizontal bars. Magnitude comparison across named categories — horizontal so the
 *  category labels read left-to-right at full length instead of being rotated. */
export function BarChart({ title, subtitle, data, format = (v) => v, max, footnote }) {
  const [hover, setHover] = useState(null);
  const ceiling = max ?? (Math.max(...data.map((d) => d.value), 0) || 1);

  return (
    <Figure
      title={title}
      subtitle={subtitle}
      table={{
        columns: ["Category", "Value"],
        rows: data.map((d) => [d.label, format(d.value)]),
      }}
    >
      <ul className="bars">
        {data.map((d) => (
          <li
            key={d.label}
            className={`bars__row${hover === d.label ? " is-hover" : ""}`}
            onMouseEnter={() => setHover(d.label)}
            onMouseLeave={() => setHover(null)}
          >
            <span className="bars__label">{d.label}</span>
            <span className="bars__track">
              <span
                className="bars__fill"
                style={{
                  width: `${Math.max(1.5, (d.value / ceiling) * 100)}%`,
                  background: d.color,
                }}
              />
            </span>
            <span className="bars__value">{format(d.value)}</span>
          </li>
        ))}
      </ul>
      {footnote && <p className="chart__footnote">{footnote}</p>}
    </Figure>
  );
}

/** Two measures per category on one shared scale. Used for "what the system decided"
 *  against "what a human labelled" — the comparison only means anything if both sit
 *  on the same axis, so they do. */
export function PairedBars({ title, subtitle, categories, seriesA, seriesB, format = (v) => v }) {
  const all = categories.flatMap((c) => [c.a, c.b]);
  const ceiling = Math.max(...all, 0) || 1;

  return (
    <Figure
      title={title}
      subtitle={subtitle}
      legend={[
        { label: seriesA.label, color: seriesA.color },
        { label: seriesB.label, color: seriesB.color },
      ]}
      table={{
        columns: ["Category", seriesA.label, seriesB.label],
        rows: categories.map((c) => [c.label, format(c.a), format(c.b)]),
      }}
    >
      <ul className="paired">
        {categories.map((c) => (
          <li key={c.label} className="paired__row">
            <span className="paired__label">{c.label}</span>
            <span className="paired__tracks">
              {/* Value sits outside the track: printed inside, it collides with the
                  fill as soon as a bar approaches full width and becomes unreadable. */}
              <span className="paired__line">
                <span className="paired__track">
                  <span className="paired__fill" style={{ width: `${(c.a / ceiling) * 100}%`, background: seriesA.color }} />
                </span>
                <span className="paired__tick">{format(c.a)}</span>
              </span>
              <span className="paired__line">
                <span className="paired__track">
                  <span className="paired__fill" style={{ width: `${(c.b / ceiling) * 100}%`, background: seriesB.color }} />
                </span>
                <span className="paired__tick">{format(c.b)}</span>
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Figure>
  );
}

/** Pipeline. A count per stage, ordered, with the drop between stages made visible.
 *  Not a funnel chart — the widths are honest bar lengths on one scale. */
export function Pipeline({ title, subtitle, stages }) {
  const ceiling = Math.max(...stages.map((s) => s.value), 0) || 1;
  return (
    <Figure
      title={title}
      subtitle={subtitle}
      table={{ columns: ["Stage", "Cases"], rows: stages.map((s) => [s.label, s.value]) }}
    >
      <ol className="pipeline">
        {stages.map((s, i) => (
          <li key={s.label} className="pipeline__stage">
            <div className="pipeline__meta">
              <span className="pipeline__label">{s.label}</span>
              <span className="pipeline__count">{s.value}</span>
            </div>
            <div className="pipeline__track">
              <div
                className="pipeline__fill"
                style={{ width: `${Math.max(2, (s.value / ceiling) * 100)}%`, background: s.color }}
              />
            </div>
            {i < stages.length - 1 && <div className="pipeline__connector" aria-hidden="true" />}
          </li>
        ))}
      </ol>
    </Figure>
  );
}

/** A single number that needs no plot. The form heuristic says a headline value with
 *  one supporting fact is a tile, not a chart. */
export function StatTile({ label, value, sub, tone = "default", accent }) {
  return (
    <div className={`stat stat--${tone}`}>
      {accent && <span className="stat__accent" style={{ background: accent }} aria-hidden="true" />}
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
      {sub && <span className="stat__sub">{sub}</span>}
    </div>
  );
}

/** Confidence bar used inside a case row: a thin magnitude mark, not a chart. */
export function MiniMeter({ value, color }) {
  return (
    <span className="meter" title={`${(value * 100).toFixed(0)}%`}>
      <span className="meter__fill" style={{ width: `${Math.max(2, value * 100)}%`, background: color }} />
    </span>
  );
}

export function claimLabel(claim) {
  return titleCase(claim);
}

export const chartInk = INK;
