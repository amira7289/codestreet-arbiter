import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import StatusBadge from "../components/StatusBadge";
import { MiniMeter } from "../components/charts";
import { PARTY, PARTY_LABEL, money, pct, titleCase } from "../theme";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "open", label: "Open" },
  { key: "resolved", label: "Resolved" },
];

export default function CaseList() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");

  function load() {
    setLoading(true);
    setError(null);
    api
      .listCases()
      .then((rows) => { setCases(rows); setError(null); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return cases.filter((c) => {
      if (filter === "open" && c.status === "resolved") return false;
      if (filter === "resolved" && c.status !== "resolved") return false;
      if (!q) return true;
      return [c.transaction_id, c.card_member_name, c.merchant_name, c.claim_type]
        .join(" ").toLowerCase().includes(q);
    });
  }, [cases, filter, query]);

  if (loading) return <p className="muted">Loading cases…</p>;

  // This is the landing surface for the queue. Without a catch, a backend that is not
  // up yet renders bare column headers — an empty list reads as "no disputes", not as
  // "the API is down".
  if (error) {
    return (
      <div className="notice notice--crit">
        <div className="notice__title">Could not reach the API</div>
        {error}. Start the backend with <code>uvicorn app.main:app --port 8000</code> from the{" "}
        <code>backend</code> directory, then <button className="btn btn--sm" onClick={load}>retry</button>.
      </div>
    );
  }

  return (
    <div className="stack stack--lg">
      <div className="page__head">
        <div>
          <div className="page__eyebrow">Queue</div>
          <h1>Cases</h1>
          <p className="page__lede">
            {cases.length} disputes in the portfolio. Open one to see both parties' evidence
            side by side and the scorecard behind its verdict.
          </p>
        </div>
        <div className="toolbar">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`btn btn--sm${filter === f.key ? " btn--primary" : ""}`}
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
            >
              {f.label}
            </button>
          ))}
          <div style={{ width: 220 }}>
            <input
              type="search"
              placeholder="Search transaction, party, claim"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search cases"
            />
          </div>
        </div>
      </div>

      <section className="card">
        <div className="table__wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Transaction</th>
                <th>Card member</th>
                <th>Merchant</th>
                <th>Claim type</th>
                <th style={{ textAlign: "right" }}>Amount</th>
                <th>Status</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td><Link to={`/cases/${c.id}`} className="mono">{c.transaction_id}</Link></td>
                  <td>{c.card_member_name}</td>
                  <td className="dim">{c.merchant_name}</td>
                  <td className="dim">{titleCase(c.claim_type)}</td>
                  <td className="num" style={{ textAlign: "right", fontWeight: 600 }}>{money(c.amount)}</td>
                  <td><StatusBadge status={c.status} /></td>
                  <td>
                    {c.verdict ? (
                      <span className="row" style={{ gap: 8 }}>
                        <span className="pill" style={{
                          background: `${PARTY[c.verdict.winner]}14`,
                          color: PARTY[c.verdict.winner],
                        }}>
                          <span className="pill__dot" />
                          {PARTY_LABEL[c.verdict.winner]}
                        </span>
                        <MiniMeter value={c.verdict.confidence} color={PARTY[c.verdict.winner]} />
                        <span className="muted num" style={{ fontSize: "0.75rem" }}>
                          {pct(c.verdict.confidence)}
                        </span>
                      </span>
                    ) : (
                      <span className="muted">Pending</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && (
          <div className="empty">
            <div className="empty__title">No cases match</div>
            Adjust the filter or clear the search.
          </div>
        )}
      </section>
    </div>
  );
}
