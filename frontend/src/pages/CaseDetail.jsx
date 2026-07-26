import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import StatusBadge from "../components/StatusBadge";
import VerdictCard from "../components/VerdictCard";
import EvidenceForm from "../components/EvidenceForm";
import GatherTimeline from "../components/GatherTimeline";

// Fast enough to read as live on a video, slow enough that a background gather run
// gets to commit between polls.
const POLL_MS = 1500;
// Resolved cases still change — the other party can file evidence that withdraws the
// ruling — but not fast enough to justify the same cadence.
const RESOLVED_POLL_MS = 5000;

const PARTY_COLOR = { card_member: "#1d4ed8", merchant: "#b45309" };
const PARTY_LABEL = { card_member: "Card Member", merchant: "Merchant" };
const OTHER_PARTY = { card_member: "merchant", merchant: "card_member" };

function EvidenceItem({ item, viewer }) {
  const own = item.submitted_by === viewer;

  return (
    <li style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 10, fontSize: "0.85rem", background: "white" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: "0.72rem", marginBottom: 4 }}>
        <span style={{ color: "#6b7280" }}>{item.evidence_type.replace(/_/g, " ")}</span>
        <span
          style={{
            color: own ? PARTY_COLOR[viewer] : "#6b7280",
            fontWeight: own ? 700 : 600,
            whiteSpace: "nowrap",
          }}
        >
          {own ? "Your submission" : `Filed by the ${PARTY_LABEL[item.submitted_by].toLowerCase()}`}
        </span>
      </div>

      {item.auto_gathered && (
        <div style={{ fontSize: "0.72rem", color: "#15803d", marginBottom: 4 }}>
          Auto-gathered from {item.source.replace(/_/g, " ")}
        </div>
      )}

      <div>{item.raw_content}</div>

      {item.parsed_facts && (
        <pre style={{ background: "#f9fafb", padding: 6, borderRadius: 6, marginTop: 6, fontSize: "0.72rem", overflowX: "auto" }}>
          {JSON.stringify(item.parsed_facts, null, 2)}
        </pre>
      )}
    </li>
  );
}

/** One party's live view of the case: their own filings, everything the other side
 *  filed, and their own submission form. Both panels are rendered at once — the
 *  toggle this replaces changed only a heading, so neither side could ever see what
 *  they were actually up against. */
function PartyPanel({ party, caseData, onSubmit }) {
  const counterparty = OTHER_PARTY[party];
  const own = caseData.evidence.filter((e) => e.submitted_by === party);
  const theirs = caseData.evidence.filter((e) => e.submitted_by === counterparty);
  const name = party === "card_member" ? caseData.card_member_name : caseData.merchant_name;

  return (
    <section
      style={{
        border: `1px solid ${PARTY_COLOR[party]}40`,
        borderTop: `3px solid ${PARTY_COLOR[party]}`,
        borderRadius: 10,
        padding: 14,
        background: "#fcfcfd",
      }}
    >
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontWeight: 700, color: PARTY_COLOR[party] }}>{PARTY_LABEL[party]}</div>
        <div style={{ fontSize: "0.8rem", color: "#6b7280" }}>{name}</div>
      </div>

      <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#6b7280", letterSpacing: "0.03em" }}>
        SUBMITTED BY THE {PARTY_LABEL[party].toUpperCase()} ({own.length})
      </div>
      <ul style={{ listStyle: "none", padding: 0, margin: "6px 0 0", display: "grid", gap: 8 }}>
        {own.map((e) => (
          <EvidenceItem key={e.id} item={e} viewer={party} />
        ))}
      </ul>
      {own.length === 0 && (
        <p style={{ color: "#6b7280", fontSize: "0.85rem", margin: "6px 0 0" }}>Nothing filed yet.</p>
      )}

      <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#6b7280", letterSpacing: "0.03em", marginTop: 16 }}>
        FILED BY THE {PARTY_LABEL[counterparty].toUpperCase()} ({theirs.length})
      </div>
      <ul style={{ listStyle: "none", padding: 0, margin: "6px 0 0", display: "grid", gap: 8 }}>
        {theirs.map((e) => (
          <EvidenceItem key={e.id} item={e} viewer={party} />
        ))}
      </ul>
      {theirs.length === 0 && (
        <p style={{ color: "#6b7280", fontSize: "0.85rem", margin: "6px 0 0" }}>Nothing filed yet.</p>
      )}

      <div style={{ marginTop: 16, borderTop: "1px solid #e5e7eb", paddingTop: 12 }}>
        <div style={{ fontSize: "0.8rem", fontWeight: 600 }}>Submit as {PARTY_LABEL[party].toLowerCase()}</div>
        <EvidenceForm submittedBy={party} onSubmit={onSubmit} />
      </div>
    </section>
  );
}

export default function CaseDetail() {
  const { id } = useParams();
  const [caseData, setCaseData] = useState(null);
  const [resolving, setResolving] = useState(false);
  const [gatherRun, setGatherRun] = useState(null);
  const [withdrawn, setWithdrawn] = useState(false);
  const [queueing, setQueueing] = useState(false);
  const [stale, setStale] = useState(null);
  const [error, setError] = useState(null);
  const gatherInFlight = useRef(false);

  // Whether the last load carried a verdict. A ruling that disappears between polls
  // means late evidence withdrew it, and that has to be said out loud — in this tab
  // and in the other party's.
  const hadVerdict = useRef(false);

  // Guards against overlapping polls. Without it a response slower than the interval
  // lets a second request start, and the two can land out of order — which drives
  // hadVerdict backwards and paints a withdrawal banner on a case nobody touched.
  const reloadInFlight = useRef(false);

  function reload() {
    if (reloadInFlight.current) return Promise.resolve(null);
    reloadInFlight.current = true;
    return api
      .getCase(id)
      .then((next) => {
        if (next.verdict) setWithdrawn(false);
        else if (hadVerdict.current) setWithdrawn(true);
        hadVerdict.current = Boolean(next.verdict);
        setCaseData(next);
        setError(null);
        setStale(null);
        return next;
      })
      .finally(() => {
        reloadInFlight.current = false;
      });
  }

  useEffect(() => {
    hadVerdict.current = false;
    setWithdrawn(false);
    setGatherRun(null);
    // Clear the previous case's data, or its title, evidence and verdict stay on
    // screen under the new case's id until the first fetch lands.
    setCaseData(null);
    setError(null);
    reload().catch((e) => setError(e.message));
  }, [id]);

  const status = caseData?.status;

  // A resolved case is still polled, just slower. The other party can file evidence
  // that withdraws the ruling at any time, and a tab showing a verdict the backend
  // has already retracted is the exact failure this project exists to prevent.
  useEffect(() => {
    const interval = status === "resolved" ? RESOLVED_POLL_MS : POLL_MS;
    const timer = setInterval(() => {
      // A poll that fails silently leaves the page showing data that may be minutes
      // stale while still claiming to be live. Say so instead.
      reload().catch((e) => setStale(e.message));
    }, interval);
    return () => clearInterval(timer);
  }, [id, status]);

  if (!caseData) {
    // A failed first load used to sit on "Loading case..." forever with the error
    // rendered further down the tree, where this early return never reached it.
    if (error) {
      return (
        <div>
          <Link to="/">&larr; All cases</Link>
          <p style={{ color: "#b91c1c", marginTop: 12 }}>Could not load this case: {error}</p>
          <p style={{ color: "#6b7280", fontSize: "0.85rem" }}>
            The API may not be running, or it may be reachable on a different host than the
            one this page was opened from.
          </p>
          <button onClick={() => reload().catch((e) => setError(e.message))}>Retry</button>
        </div>
      );
    }
    return <p>Loading case...</p>;
  }

  async function handleEvidenceSubmit(payload) {
    setError(null);
    try {
      await api.submitEvidence(id, payload);
      await reload();
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleGather() {
    // A ref, not state: state updates are batched, so three fast clicks all read the
    // same stale `false` and fire three concurrent gathers. `pendingSources` cannot
    // guard this either — it is only non-zero after the request returns.
    if (gatherInFlight.current) return;
    gatherInFlight.current = true;
    setQueueing(true);
    setError(null);
    try {
      const baseline = caseData.gather_log.length;
      const run = await api.gatherEvidence(id);
      setGatherRun({ baseline, queued: run.sources_queued });
      await reload();
    } catch (e) {
      setError(e.message);
    } finally {
      gatherInFlight.current = false;
      setQueueing(false);
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

  const pendingSources = gatherRun
    ? Math.max(0, gatherRun.baseline + gatherRun.queued - caseData.gather_log.length)
    : 0;

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

      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "16px 0" }}>
        <button onClick={handleGather} disabled={queueing || pendingSources > 0}>
          {queueing || pendingSources > 0 ? "Gathering evidence..." : "Auto-gather evidence"}
        </button>
        {caseData.status !== "resolved" && (
          <button onClick={handleResolve} disabled={resolving}>
            {resolving ? "Resolving..." : "Resolve Case"}
          </button>
        )}
        {/* Shown on resolved cases too: they are polled more slowly, but they ARE
            polled, and a live indicator that disappears reads as "stopped updating". */}
        {stale ? (
          <span style={{ fontSize: "0.75rem", color: "#b91c1c", fontWeight: 600 }}>
            Disconnected &middot; showing last known state ({stale})
          </span>
        ) : (
          <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>
            Live &middot; refreshing every {caseData.status === "resolved" ? "5s" : "1.5s"}
          </span>
        )}
      </div>

      {withdrawn && (
        <div
          style={{
            background: "#fef2f2",
            border: "1px solid #fca5a5",
            borderRadius: 8,
            padding: "10px 12px",
            marginBottom: 12,
          }}
        >
          <div style={{ fontWeight: 700, fontSize: "0.85rem", color: "#991b1b" }}>Verdict withdrawn</div>
          <div style={{ fontSize: "0.85rem", color: "#7f1d1d", marginTop: 4, lineHeight: 1.5 }}>
            Evidence was filed after this case was resolved, so the ruling and the scorecard behind it have been
            vacated and the case re-opened. Resolve again to score the full evidence set.
          </div>
        </div>
      )}

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <GatherTimeline entries={caseData.gather_log} pending={pendingSources} run={gatherRun} />

      <div className="split-view" style={{ marginTop: 16 }}>
        <PartyPanel party="card_member" caseData={caseData} onSubmit={handleEvidenceSubmit} />
        <PartyPanel party="merchant" caseData={caseData} onSubmit={handleEvidenceSubmit} />
      </div>

      <div style={{ marginTop: 24 }}>
        <div
          style={{
            background: "#eff6ff",
            border: "2px solid #1d4ed8",
            borderRadius: "12px 12px 0 0",
            borderBottom: "none",
            padding: "14px 18px",
          }}
        >
          <div style={{ fontWeight: 700, color: "#1d4ed8", fontSize: "1.05rem" }}>
            Both parties see this identical explanation.
          </div>
          <div style={{ fontSize: "0.85rem", color: "#1e40af", marginTop: 4, lineHeight: 1.5 }}>
            One ruling, one scorecard, one wording. There is no card member version of this and no merchant version
            of it — every point below traces to a named signal with a fixed weight, and both sides are reading the
            same page.
          </div>
        </div>

        <div style={{ border: "2px solid #1d4ed8", borderTop: "none", borderRadius: "0 0 12px 12px", padding: 4 }}>
          {caseData.verdict ? (
            <VerdictCard verdict={caseData.verdict} signals={caseData.signals} evidence={caseData.evidence} />
          ) : (
            <p style={{ color: "#6b7280", padding: "16px 18px", margin: 0 }}>
              No ruling yet. Resolve the case to produce one — it will appear here, identically, for both parties.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
