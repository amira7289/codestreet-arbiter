import { useState } from "react";
import { PARTY, PARTY_LABEL, money, pct, titleCase } from "../theme";

const OFFER_TYPES = [
  { key: "full_refund", label: "Full refund", needsAmount: false },
  { key: "partial_refund", label: "Partial refund", needsAmount: true },
  { key: "replacement", label: "Replacement", needsAmount: false },
  { key: "withdraw_dispute", label: "Withdraw dispute", needsAmount: false },
];

const OFFER_STATUS = {
  open: { label: "Awaiting response", cls: "notice--warn" },
  accepted: { label: "Accepted", cls: "notice--good" },
  declined: { label: "Declined", cls: "notice--crit" },
  superseded: { label: "Superseded", cls: "notice--quiet" },
};

function terms(offer) {
  if (offer.offer_type === "partial_refund") return `Partial refund of ${money(offer.amount)}`;
  return titleCase(offer.offer_type);
}

function OfferRow({ offer, caseAmount, onRespond, busy }) {
  const meta = OFFER_STATUS[offer.status] ?? OFFER_STATUS.superseded;
  const share = offer.offer_type === "partial_refund" ? offer.amount / caseAmount : null;

  return (
    <li className="card" style={{ padding: 14, borderLeft: `3px solid ${PARTY[offer.proposed_by]}` }}>
      <div className="row row--between" style={{ gap: 8 }}>
        <span style={{ fontWeight: 650, color: PARTY[offer.proposed_by] }}>
          {PARTY_LABEL[offer.proposed_by]} proposed
        </span>
        <span className={`pill ${meta.cls}`} style={{ border: "none" }}>{meta.label}</span>
      </div>

      <div className="row" style={{ gap: 10, marginTop: 6 }}>
        <strong>{terms(offer)}</strong>
        {share != null && <span className="muted num">{pct(share)} of the disputed amount</span>}
      </div>

      {offer.message && (
        <p className="dim" style={{ marginTop: 6, fontStyle: "italic" }}>&ldquo;{offer.message}&rdquo;</p>
      )}

      {offer.status === "open" && (
        <div className="toolbar" style={{ marginTop: 12 }}>
          <button className="btn btn--primary btn--sm" disabled={busy}
                  onClick={() => onRespond(offer.id, "accept")}>
            Accept as {PARTY_LABEL[offer.proposed_by === "merchant" ? "card_member" : "merchant"].toLowerCase()}
          </button>
          <button className="btn btn--sm" disabled={busy}
                  onClick={() => onRespond(offer.id, "decline")}>
            Decline
          </button>
        </div>
      )}
    </li>
  );
}

/** The negotiation stage. Adjudication is the fallback, not the first move: a
 *  settlement both sides accept ends the dispute outright, with no verdict to
 *  explain and nobody to convince. */
export default function Negotiation({ caseData, forecast, onOffer, onRespond, busy }) {
  const [party, setParty] = useState("merchant");
  const [type, setType] = useState("full_refund");
  const [amount, setAmount] = useState("");
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState(null);

  const settled = caseData.status === "settled";
  const offers = caseData.offers ?? [];
  const open = offers.find((o) => o.status === "open");
  const accepted = offers.find((o) => o.status === "accepted");
  const needsAmount = OFFER_TYPES.find((t) => t.key === type)?.needsAmount;

  async function submit(e) {
    e.preventDefault();
    setFormError(null);
    const value = needsAmount ? Number(amount) : null;
    if (needsAmount && (!value || value <= 0 || value > caseData.amount)) {
      setFormError(`Enter an amount between $0 and ${money(caseData.amount)}.`);
      return;
    }
    try {
      await onOffer({
        proposed_by: party,
        offer_type: type,
        amount: value,
        message: message.trim() || null,
      });
      setAmount("");
      setMessage("");
    } catch (err) {
      setFormError(err.message);
    }
  }

  return (
    <section className="card">
      <div className="card__head">
        <div>
          <h2 className="card__title">Settlement</h2>
          <p className="chart__subtitle" style={{ marginTop: 2 }}>
            Either side may propose terms. A dispute both parties agree on is closed
            without a ruling — the scorecard is only asked when they cannot agree.
          </p>
        </div>
      </div>

      <div className="card__body stack">
        {settled && accepted && (
          <div className="notice notice--good">
            <div className="notice__title">Settled by agreement</div>
            {terms(accepted)} — proposed by the {PARTY_LABEL[accepted.proposed_by].toLowerCase()} and
            accepted. No verdict was issued, and none is needed.
          </div>
        )}

        {!settled && forecast && (
          <div className="notice notice--info">
            <div className="notice__title">
              If neither side moves, the scorecard would find for the{" "}
              {PARTY_LABEL[forecast.winner].toLowerCase()} at {pct(forecast.confidence)} confidence
            </div>
            <p style={{ marginTop: 4 }}>
              Card member {forecast.card_member_score.toFixed(0)} · Merchant{" "}
              {forecast.merchant_score.toFixed(0)}. {forecast.counterfactual}
            </p>
            <p style={{ marginTop: 6, fontSize: "0.8125rem" }}>
              Both parties see this same forecast. A negotiation where only one side can
              estimate the outcome is not a negotiation.
            </p>
          </div>
        )}

        {offers.length > 0 && (
          <ul className="stack stack--sm" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {[...offers].reverse().map((o) => (
              <OfferRow key={o.id} offer={o} caseAmount={caseData.amount}
                        onRespond={onRespond} busy={busy} />
            ))}
          </ul>
        )}

        {!settled && (
          <form onSubmit={submit} className="stack stack--sm">
            <div className="section-label">
              {open ? `Counter the ${PARTY_LABEL[open.proposed_by].toLowerCase()}'s offer` : "Propose terms"}
            </div>
            {/* Amount only exists for a partial refund. The other three types imply
                their own figure — a full refund is the disputed sum, a replacement is
                goods rather than money, a withdrawal moves nothing — so the field is
                absent rather than present and dead. */}
            <div className={needsAmount ? "grid grid--3" : "grid grid--2"}>
              <label className="field">
                <span className="field__label">Proposing as</span>
                <select value={party} onChange={(e) => setParty(e.target.value)}>
                  <option value="merchant">Merchant</option>
                  <option value="card_member">Card Member</option>
                </select>
              </label>
              <label className="field">
                <span className="field__label">Terms</span>
                <select value={type} onChange={(e) => { setType(e.target.value); setAmount(""); }}>
                  {OFFER_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
              </label>
              {needsAmount && (
                <label className="field">
                  <span className="field__label">Amount (max {money(caseData.amount)})</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={amount}
                    placeholder="0.00"
                    autoFocus
                    onChange={(e) => setAmount(e.target.value)}
                  />
                </label>
              )}
            </div>
            <label className="field">
              <span className="field__label">Message (optional)</span>
              <textarea rows={2} value={message} placeholder="Context for the other party"
                        onChange={(e) => setMessage(e.target.value)} />
            </label>
            {formError && <div className="notice notice--crit">{formError}</div>}
            <div className="toolbar">
              <button className="btn btn--primary" type="submit" disabled={busy}>
                {open ? "Send counter-offer" : "Send offer"}
              </button>
              {open && (
                <span className="muted">
                  This replaces the {PARTY_LABEL[open.proposed_by].toLowerCase()}'s open offer.
                </span>
              )}
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
