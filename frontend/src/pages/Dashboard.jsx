import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { BarChart, DonutChart, PairedBars, Pipeline, StatTile } from "../components/charts";
import StatusBadge from "../components/StatusBadge";
import {
  BRAND, CATEGORICAL, CLAIM_COLOR, PARTY, PARTY_LABEL, STATUS,
  money, pct, titleCase,
} from "../theme";

const STAGES = ["filed", "evidence_gathering", "negotiating", "scored", "resolved", "settled"];
const STAGE_COLOR = {
  filed: STATUS.neutral,
  evidence_gathering: STATUS.warning,
  negotiating: BRAND.blueDeep,
  scored: BRAND.blue,
  resolved: BRAND.blue,
  settled: STATUS.good,
};

export default function Dashboard() {
  const [cases, setCases] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);

  function load() {
    setError(null);
    Promise.all([api.listCases(), api.getMetrics()])
      .then(([c, m]) => { setCases(c); setMetrics(m); })
      .catch((e) => setError(e.message));
  }

  useEffect(load, []);

  const derived = useMemo(() => {
    if (!cases) return null;
    const byStatus = Object.fromEntries(STAGES.map((s) => [s, 0]));
    const byClaim = {};
    let disputedValue = 0;
    let resolvedValue = 0;

    for (const c of cases) {
      byStatus[c.status] = (byStatus[c.status] ?? 0) + 1;
      byClaim[c.claim_type] = (byClaim[c.claim_type] ?? 0) + 1;
      disputedValue += c.amount;
      if (c.status === "resolved" || c.status === "settled") resolvedValue += c.amount;
    }
    return {
      byStatus,
      byClaim,
      disputedValue,
      resolvedValue,
      closed: byStatus.resolved + byStatus.settled,
      settled: byStatus.settled,
      open: cases.length - byStatus.resolved - byStatus.settled,
    };
  }, [cases]);

  if (error) {
    return (
      <div className="notice notice--crit">
        <div className="notice__title">Could not reach the API</div>
        {error}. Start the backend with <code>uvicorn app.main:app --port 8000</code>, then{" "}
        <button className="btn btn--sm" onClick={load}>retry</button>.
      </div>
    );
  }
  if (!cases || !metrics || !derived) return <p className="muted">Loading dashboard…</p>;

  // Counted from the portfolio itself. metrics.fairness is measured over the labelled
  // corpus, which is a different population — mixing the two would put a corpus ratio
  // on a portfolio chart and quietly misreport both.
  const decided = cases.filter((c) => c.verdict);
  const settledCount = cases.filter((c) => c.status === "settled").length;
  const wonBy = (party) => decided.filter((c) => c.verdict.winner === party).length;
  const claimAccuracy = Object.entries(metrics.accuracy.per_claim_type)
    .map(([k, v]) => ({ label: titleCase(k), value: v, color: CLAIM_COLOR[k] ?? CATEGORICAL[4] }))
    .sort((a, b) => b.value - a.value);

  const recent = [...cases]
    .sort((a, b) => (a.status === "resolved") - (b.status === "resolved") || b.amount - a.amount)
    .slice(0, 6);

  return (
    <div className="stack stack--lg">
      <div className="page__head">
        <div>
          <div className="page__eyebrow">Overview</div>
          <h1>Dispute Portfolio</h1>
          <p className="page__lede">
            Every verdict on this page was decided by a deterministic scorecard, not by a
            model. The accuracy and fairness figures are recomputed from the labelled
            corpus on each load.
          </p>
        </div>
        <div className="toolbar">
          <button className="btn" onClick={load}>Refresh</button>
          <Link className="btn btn--primary" to="/cases">Open case queue</Link>
        </div>
      </div>

      <section className="grid grid--stats" aria-label="Key figures">
        <StatTile
          label="Open disputes"
          value={derived.open}
          sub={`${cases.length} total in portfolio`}
          accent={STATUS.warning}
        />
        <StatTile
          label="Disputed value"
          value={money(derived.disputedValue)}
          sub={`${money(derived.resolvedValue)} closed`}
          accent={BRAND.blue}
        />
        <StatTile
          label="Scorecard accuracy"
          value={pct(metrics.accuracy.overall, 1)}
          sub={`${metrics.accuracy.correct} of ${metrics.corpus.arbitrable} labelled cases`}
          tone="brand"
        />
        <StatTile
          label="Median decision time"
          value={`${metrics.latency_ms.p50.toFixed(2)} ms`}
          sub={`p95 ${metrics.latency_ms.p95.toFixed(2)} ms · parse, score, explain`}
          accent={STATUS.good}
        />
        <StatTile
          label="Confidently wrong"
          value={metrics.calibration.confidently_wrong}
          sub="verdicts above 80% that missed"
          accent={metrics.calibration.confidently_wrong === 0 ? STATUS.good : STATUS.critical}
        />
      </section>

      <section className="grid grid--main">
        <BarChart
          title="Accuracy by claim type"
          subtitle="Share of labelled cases the scorecard called correctly, measured on replay against the golden corpus."
          data={claimAccuracy}
          format={(v) => pct(v)}
          max={1}
          footnote="Abstention cases — those a careful reader could not decide on the evidence — are excluded rather than counted as failures."
        />
        <DonutChart
          title="Verdicts by party"
          subtitle="Adjudicated outcomes, plus the disputes the parties closed between themselves without a ruling."
          centerValue={cases.length}
          centerLabel="Disputes"
          data={[
            { label: PARTY_LABEL.card_member, value: wonBy("card_member"), color: PARTY.card_member },
            { label: PARTY_LABEL.merchant, value: wonBy("merchant"), color: PARTY.merchant },
            { label: "Settled by agreement", value: derived.settled, color: STATUS.good },
            { label: "Still open", value: derived.open, color: "#C3CAD1" },
          ]}
        />
      </section>

      <section className="grid grid--main">
        <PairedBars
          title="Fairness: decisions against human labels"
          subtitle="Measured on the labelled corpus, not this portfolio. If the scorecard leaned toward one party these bars would diverge; the claim is not that bias is zero, but that any bias traces to a rule printed on the verdict."
          categories={[
            {
              label: "Card member",
              a: metrics.fairness.verdict_share_card_member,
              b: metrics.fairness.label_share_card_member,
            },
            {
              label: "Merchant",
              a: 1 - metrics.fairness.verdict_share_card_member,
              b: 1 - metrics.fairness.label_share_card_member,
            },
          ]}
          seriesA={{ label: "Scorecard decided", color: BRAND.blue }}
          seriesB={{ label: "Human label", color: "#8A8D91" }}
          format={(v) => pct(v)}
        />
        <Pipeline
          title="Resolution pipeline"
          subtitle="Where the portfolio currently sits."
          stages={STAGES.map((s) => ({
            label: titleCase(s),
            value: derived.byStatus[s] ?? 0,
            color: STAGE_COLOR[s],
          }))}
        />
      </section>

      <section className="grid grid--2">
        <BarChart
          title="Volume by claim type"
          subtitle="What the portfolio is actually made of."
          data={Object.entries(derived.byClaim)
            .map(([k, v]) => ({ label: titleCase(k), value: v, color: CLAIM_COLOR[k] ?? CATEGORICAL[4] }))
            .sort((a, b) => b.value - a.value)}
        />
        <div className="chart">
          <div className="chart__head">
            <div>
              <h3 className="chart__title">Calibration</h3>
              <p className="chart__subtitle">
                Confidence should be high when the scorecard is right and low when it is
                wrong. The gap between these two is the number that matters.
              </p>
            </div>
          </div>
          <div className="grid grid--2">
            <StatTile
              label="Mean confidence, correct"
              value={pct(metrics.calibration.mean_confidence_correct)}
              accent={STATUS.good}
            />
            <StatTile
              label="Mean confidence, wrong"
              value={pct(metrics.calibration.mean_confidence_wrong)}
              accent={STATUS.warning}
            />
          </div>
          <div className="notice notice--quiet">
            <strong className="num">{metrics.calibration.separation.toFixed(3)}</strong> separation ·{" "}
            <strong className="num">{metrics.fairness.errors_favouring_card_member}</strong> errors favour the
            card member ·{" "}
            <strong className="num">{metrics.fairness.errors_favouring_merchant}</strong> favour the merchant
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">Highest-value disputes</h2>
          <Link to="/cases" className="btn btn--ghost btn--sm">View all {cases.length}</Link>
        </div>
        <div className="table__wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Transaction</th>
                <th>Card member</th>
                <th>Merchant</th>
                <th>Claim</th>
                <th style={{ textAlign: "right" }}>Amount</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((c) => (
                <tr key={c.id}>
                  <td><Link to={`/cases/${c.id}`} className="mono">{c.transaction_id}</Link></td>
                  <td>{c.card_member_name}</td>
                  <td className="dim">{c.merchant_name}</td>
                  <td className="dim">{titleCase(c.claim_type)}</td>
                  <td className="num" style={{ textAlign: "right", fontWeight: 600 }}>{money(c.amount)}</td>
                  <td><StatusBadge status={c.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
