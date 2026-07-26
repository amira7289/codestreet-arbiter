import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function CaseList() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .listCases()
      .then((rows) => {
        setCases(rows);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  if (loading) return <p>Loading cases...</p>;

  // This is the landing page. With no catch, a backend that is not up yet rendered
  // bare column headers and nothing else — an empty list reads as "no disputes",
  // not as "the API is down".
  if (error) {
    return (
      <div>
        <h1>Dispute Cases</h1>
        <p style={{ color: "#b91c1c" }}>Could not reach the API: {error}</p>
        <p style={{ color: "#6b7280", fontSize: "0.85rem" }}>
          Start the backend with <code>uvicorn app.main:app --port 8000</code> from the{" "}
          <code>backend</code> directory, then retry.
        </p>
        <button onClick={load}>Retry</button>
      </div>
    );
  }

  return (
    <div>
      <h1>Dispute Cases</h1>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #e5e7eb" }}>
            <th style={{ padding: 8 }}>Transaction</th>
            <th style={{ padding: 8 }}>Card Member</th>
            <th style={{ padding: 8 }}>Merchant</th>
            <th style={{ padding: 8 }}>Amount</th>
            <th style={{ padding: 8 }}>Claim</th>
            <th style={{ padding: 8 }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
              <td style={{ padding: 8 }}>
                <Link to={`/cases/${c.id}`}>{c.transaction_id}</Link>
              </td>
              <td style={{ padding: 8 }}>{c.card_member_name}</td>
              <td style={{ padding: 8 }}>{c.merchant_name}</td>
              <td style={{ padding: 8 }}>${c.amount.toFixed(2)}</td>
              <td style={{ padding: 8 }}>{c.claim_type.replace(/_/g, " ")}</td>
              <td style={{ padding: 8 }}>
                <StatusBadge status={c.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
