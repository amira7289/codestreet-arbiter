import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import StatusBadge from "../components/StatusBadge";
import VerdictCard from "../components/VerdictCard";
import EvidenceForm from "../components/EvidenceForm";

export default function CaseDetail() {
  const { id } = useParams();
  const [caseData, setCaseData] = useState(null);
  const [view, setView] = useState("card_member");
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState(null);

  function reload() {
    return api.getCase(id).then(setCaseData);
  }

  useEffect(() => {
    reload();
  }, [id]);

  if (!caseData) return <p>Loading case...</p>;

  async function handleEvidenceSubmit(payload) {
    setError(null);
    try {
      await api.submitEvidence(id, payload);
      await reload();
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleResolve() {
    setResolving(true);
    setError(null);
    try {
      await api.resolveCase(id);
      await reload();
    } catch (e) {
      setError(e.message);
    } finally {
      setResolving(false);
    }
  }

  const visibleEvidence = caseData.evidence;

  return (
    <div>
      <Link to="/">&larr; All cases</Link>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
        <h1 style={{ margin: 0 }}>{caseData.transaction_id}</h1>
        <StatusBadge status={caseData.status} />
      </div>
      <p style={{ color: "#6b7280" }}>
        {caseData.card_member_name} vs {caseData.merchant_name} &middot; ${caseData.amount.toFixed(2)} &middot;{" "}
        {caseData.claim_type.replace(/_/g, " ")}
      </p>
      <p style={{ fontStyle: "italic" }}>&ldquo;{caseData.claim_text}&rdquo;</p>

      <div style={{ display: "flex", gap: 8, margin: "16px 0" }}>
        <button
          onClick={() => setView("card_member")}
          style={{ fontWeight: view === "card_member" ? 700 : 400 }}
        >
          Card Member View
        </button>
        <button onClick={() => setView("merchant")} style={{ fontWeight: view === "merchant" ? 700 : 400 }}>
          Merchant View
        </button>
      </div>

      <h3>Evidence ({visibleEvidence.length})</h3>
      <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 8 }}>
        {visibleEvidence.map((e) => (
          <li key={e.id} style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 10, fontSize: "0.9rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#6b7280", fontSize: "0.75rem" }}>
              <span>
                {e.evidence_type.replace(/_/g, " ")} &middot; submitted by {e.submitted_by.replace("_", " ")}
              </span>
            </div>
            <div>{e.raw_content}</div>
            {e.parsed_facts && (
              <pre style={{ background: "#f9fafb", padding: 6, borderRadius: 6, marginTop: 6, fontSize: "0.75rem" }}>
                {JSON.stringify(e.parsed_facts, null, 2)}
              </pre>
            )}
          </li>
        ))}
        {visibleEvidence.length === 0 && <p style={{ color: "#6b7280" }}>No evidence submitted yet.</p>}
      </ul>

      {caseData.status !== "resolved" && (
        <>
          <h4>Submit evidence as {view === "card_member" ? "Card Member" : "Merchant"}</h4>
          <EvidenceForm submittedBy={view} onSubmit={handleEvidenceSubmit} />

          <button onClick={handleResolve} disabled={resolving} style={{ marginTop: 16 }}>
            {resolving ? "Resolving..." : "Resolve Case"}
          </button>
        </>
      )}

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <VerdictCard verdict={caseData.verdict} signals={caseData.signals} />
    </div>
  );
}
