import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function CaseList() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listCases().then(setCases).finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading cases...</p>;

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
