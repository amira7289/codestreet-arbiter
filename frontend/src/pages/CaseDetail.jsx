import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import StatusBadge from "../components/StatusBadge";
import { PARTY as PARTY_COLOR, PARTY_LABEL, money, titleCase } from "../theme";
import VerdictCard from "../components/VerdictCard";
import EvidenceForm from "../components/EvidenceForm";
import GatherTimeline from "../components/GatherTimeline";
import Negotiation from "../components/Negotiation";

// Fast enough to read as live on a video, slow enough that a background gather run
// gets to commit between polls.
const POLL_MS = 1500;
// Resolved cases still change — the other party can file evidence that withdraws the
// ruling — but not fast enough to justify the same cadence.
const RESOLVED_POLL_MS = 5000;

const OTHER_PARTY = { card_member: "merchant", merchant: "card_member" };

function EvidenceItem({ item, viewer, signals }) {
  const own = item.submitted_by === viewer;
  // Which scorecard signals this specific document produced. Shown because the
  // question a losing party actually has is "what did my evidence count for", and
  // the answer is otherwise buried in a combined list at the bottom of the page.
  const produced = (signals ?? []).filter((s) => (s.evidence_ids ?? []).includes(item.id));

  return (
    <li className="card" style={{ padding: 12, fontSize: "0.8125rem" }}>
      <div className="row row--between" style={{ fontSize: "0.72rem", marginBottom: 6, gap: 8 }}>
        <span className="section-label">{titleCase(item.evidence_type)}</span>
        <span style={{
          color: own ? PARTY_COLOR[viewer] : "var(--ink-3)",
          fontWeight: own ? 700 : 600,
          whiteSpace: "nowrap",
        }}>
          {own ? "Your submission" : `Filed by the ${PARTY_LABEL[item.submitted_by].toLowerCase()}`}
        </span>
      </div>

      {item.auto_gathered && (
        <div style={{ fontSize: "0.72rem", color: "var(--good)", marginBottom: 6 }}>
          Auto-gathered from {titleCase(item.source)}
        </div>
      )}

      {/* Plain English first. The typed extraction is what the scorer reads, but a
          card member should not have to parse JSON to see what was found. */}
      {item.readable_facts?.length > 0 ? (
        <ul className="stack stack--sm" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {item.readable_facts.map((line, i) => (
            <li key={i} className="row" style={{ gap: 8, alignItems: "flex-start" }}>
              <span aria-hidden="true" style={{
                width: 5, height: 5, borderRadius: "50%", background: "var(--ink-3)",
                marginTop: 7, flex: "none",
              }} />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="muted">No facts could be read from this document.</div>
      )}

      {produced.length > 0 && (
        <div className="stack stack--sm" style={{ marginTop: 10 }}>
          {produced.map((s) => (
            <div key={s.id} className="row" style={{
              gap: 8, fontSize: "0.75rem",
              borderLeft: `3px solid ${s.favors ? PARTY_COLOR[s.favors] : "var(--ink-3)"}`,
              paddingLeft: 8,
            }}>
              <span className="muted">Counted as</span>
              <strong>{titleCase(s.signal_name)}</strong>
              <span className="num" style={{ color: s.favors ? PARTY_COLOR[s.favors] : "var(--ink-2)" }}>
                +{s.weight} {s.favors ? PARTY_LABEL[s.favors] : ""}
              </span>
            </div>
          ))}
        </div>
      )}

      <details style={{ marginTop: 10 }}>
        <summary className="muted" style={{ cursor: "pointer", fontSize: "0.75rem" }}>
          Source document and extracted data
        </summary>
        <p className="dim" style={{ marginTop: 8 }}>{item.raw_content}</p>
        {item.parsed_facts && (
          <pre style={{
            background: "var(--surface-sunken)", padding: 8, borderRadius: 6,
            marginTop: 8, fontSize: "0.72rem", overflowX: "auto",
          }}>
            {JSON.stringify(item.parsed_facts, null, 2)}
          </pre>
        )}
      </details>
    </li>
  );
}

/** One party's live view of the case: their own filings, everything the other side
 *  filed, and their own submission form. Both panels are rendered at once — the
 *  toggle this replaces changed only a heading, so neither side could ever see what
 *  they were actually up against. */
function PartyPanel({ party, caseData, onSubmit }) {
  const signals = caseData.signals ?? [];
  const counterparty = OTHER_PARTY[party];
  const own = caseData.evidence.filter((e) => e.submitted_by === party);
  const theirs = caseData.evidence.filter((e) => e.submitted_by === counterparty);
  const name = party === "card_member" ? caseData.card_member_name : caseData.merchant_name;

  return (
    <section
      className="card"
      style={{ borderTop: `3px solid ${PARTY_COLOR[party]}`, padding: 16, background: "var(--surface-sunken)" }}
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
          <EvidenceItem key={e.id} item={e} viewer={party} signals={signals} />
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
          <EvidenceItem key={e.id} item={e} viewer={party} signals={signals} />
        ))}
      </ul>
      {theirs.length === 0 && (
        <p style={{ color: "#6b7280", fontSize: "0.85rem", margin: "6px 0 0" }}>Nothing filed yet.</p>
      )}

      <div style={{ marginTop: 16, borderTop: "1px solid #e5e7eb", paddingTop: 12 }}>
        <div className="section-label">Add evidence</div>
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
  const [forecast, setForecast] = useState(null);
  const [negotiating, setNegotiating] = useState(false);
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
        // The forecast is what makes the negotiation informed, so it tracks the
        // evidence set rather than being fetched once on mount.
        if (next.status !== "settled") {
          api.getForecast(id).then(setForecast).catch(() => setForecast(null));
        } else {
          setForecast(null);
        }
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
    return <p className="muted">Loading case…</p>;
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

  async function handleOffer(payload) {
    setNegotiating(true);
    try {
      await api.proposeOffer(id, payload);
      await reload();
    } finally {
      setNegotiating(false);
    }
  }

  async function handleRespond(offerId, action) {
    setNegotiating(true);
    setError(null);
    try {
      await api.respondToOffer(id, offerId, action);
      await reload();
    } catch (e) {
      setError(e.message);
    } finally {
      setNegotiating(false);
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
    <div className="stack stack--lg">
      <div>
        <Link to="/cases" className="page__eyebrow" style={{ display: "inline-block", marginBottom: 6 }}>
          &larr; Case queue
        </Link>
        <div className="row row--between">
          <div className="row" style={{ gap: 12 }}>
            <h1 className="mono">{caseData.transaction_id}</h1>
            <StatusBadge status={caseData.status} />
          </div>
          <div className="row" style={{ gap: 6 }}>
            <span className="section-label">Disputed</span>
            <span className="num" style={{ fontSize: "1.25rem", fontWeight: 650 }}>
              {money(caseData.amount)}
            </span>
          </div>
        </div>
        <p className="dim" style={{ marginTop: 4 }}>
          {caseData.card_member_name} <span className="muted">vs</span> {caseData.merchant_name}
          <span className="muted"> · </span>{titleCase(caseData.claim_type)}
        </p>
        <blockquote className="notice notice--quiet" style={{ marginTop: 12, fontStyle: "italic" }}>
          &ldquo;{caseData.claim_text}&rdquo;
        </blockquote>
      </div>

      <div className="toolbar">
        <button className="btn btn--primary" onClick={handleGather} disabled={queueing || pendingSources > 0}>
          {queueing || pendingSources > 0 ? "Gathering evidence…" : "Auto-gather evidence"}
        </button>
        {caseData.status !== "resolved" && caseData.status !== "settled" && (
          <button className="btn" onClick={handleResolve} disabled={resolving}>
            {resolving ? "Resolving…" : "Resolve case"}
          </button>
        )}
        <span className="spacer" />
        {/* Shown on resolved cases too: they are polled more slowly, but they ARE
            polled, and a live indicator that disappears reads as "stopped updating". */}
        {stale ? (
          <span className="live live--off">
            <span className="live__dot" />Disconnected · showing last known state
          </span>
        ) : (
          <span className="live">
            <span className="live__dot" />Live · refreshing every{" "}
            {caseData.status === "resolved" ? "5s" : "1.5s"}
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

      <Negotiation
        caseData={caseData}
        forecast={forecast}
        onOffer={handleOffer}
        onRespond={handleRespond}
        busy={negotiating}
      />

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
