import { CircleAlert } from "lucide-react";
import type { CanonicalHistoricalEvidence, CashPolicyEvidence, CashPolicyStateEvidence } from "../lib/historicalEvidence";

const pct = (value?: number | null, digits = 1) => typeof value === "number" && Number.isFinite(value)
  ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
  : "-";

function label(value?: string | null) {
  if (!value) return "UNAVAILABLE";
  if (value === "HOLD_CASH") return "HOLD CASH";
  if (value === "RECOVERING_FROM_OVERSOLD") return "RECOVERING FROM OVERSOLD";
  return value.replaceAll("_", " ");
}

function StateTable({ title, data }: { title: string; data: CashPolicyStateEvidence }) {
  const horizons = ["5", "10", "15", "30", "60", "90"];
  return <div className="aggregate-history-card">
    <div className="aggregate-history-title">{title}<small>{data.n} historical observations</small></div>
    <div className="aggregate-history-head"><span>Horizon</span><span>SPY median</span><span>QQQ median</span><span>Positive</span></div>
    {horizons.map(h => {
      const spy = data.SPY[h];
      const qqq = data.QQQ[h];
      const rates = [spy?.positive_rate, qqq?.positive_rate].filter((x): x is number => typeof x === "number" && Number.isFinite(x));
      const averageRate = rates.length ? rates.reduce((a,b) => a+b,0) / rates.length : null;
      return <div className={`aggregate-history-row ${["10","30","60"].includes(h) ? "core-horizon" : ""}`} key={h}>
        <b>{h}D</b><span className="history-return">{pct(spy?.median,2)}</span><span className="history-return">{pct(qqq?.median,2)}</span>
        <span className="history-positive">{rates.length ? rates.map(x => pct(x,0)).join(" / ") : "context only"}{averageRate !== null ? <i><em style={{width:`${Math.max(0,Math.min(100,averageRate*100))}%`}} /></i> : null}</span>
      </div>;
    })}
  </div>;
}

export default function AggregateHistoricalEvidence({ evidence, cashPolicy, currentAction, currentCondition }: {
  evidence: CanonicalHistoricalEvidence | null;
  cashPolicy?: CashPolicyEvidence | null;
  currentAction?: string | null;
  currentCondition?: string | null;
}) {
  const actionKey = currentAction || "";
  const conditionKey = currentCondition || "";
  const actionEvidence = cashPolicy?.actions?.[actionKey];
  const conditionEvidence = cashPolicy?.conditions?.[conditionKey];

  if (cashPolicy && actionEvidence) {
    return <section className="card section-card historical-performance-card">
      <style>{`
        .historical-performance-card{position:relative;overflow:hidden}.historical-performance-card:before{content:"";position:absolute;inset:0 auto auto 0;width:100%;height:3px;background:linear-gradient(90deg,var(--green),#7bb893 46%,transparent)}
        .aggregate-history-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.aggregate-history-card{border:1px solid var(--line);border-radius:16px;overflow:hidden;background:linear-gradient(180deg,rgba(255,255,255,.62),rgba(255,255,255,.28));box-shadow:0 10px 28px rgba(28,45,34,.045)}
        .aggregate-history-head,.aggregate-history-row{display:grid;grid-template-columns:62px 1fr 1fr 1.15fr;gap:9px;padding:10px 12px;align-items:center}.aggregate-history-head{background:linear-gradient(90deg,#eceae3,#f5f4ef);font-size:8px;font-weight:900;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.aggregate-history-row{border-top:1px solid var(--line);font-size:10px;transition:background .15s ease}.aggregate-history-row:hover{background:rgba(47,118,80,.045)}.aggregate-history-row.core-horizon{background:rgba(47,118,80,.025)}.aggregate-history-row b{font-size:11px;letter-spacing:-.01em}.history-return{font-weight:850;color:var(--green);font-variant-numeric:tabular-nums}.history-positive{font-variant-numeric:tabular-nums;color:#41473f}.history-positive i{display:block;height:3px;margin-top:5px;background:#e3e0d8;border-radius:99px;overflow:hidden}.history-positive em{display:block;height:100%;background:linear-gradient(90deg,#9ac7aa,var(--green));border-radius:99px}
        .aggregate-history-title{padding:13px 12px 11px;font-size:15px;font-weight:900;letter-spacing:-.02em}.aggregate-history-title small{display:block;margin-top:3px;color:var(--muted);font-size:9px;font-weight:650;letter-spacing:0}.archive-note{margin-top:12px;font-size:9px;line-height:1.5;color:var(--muted)}
        .policy-note{position:relative;border:1px solid rgba(47,118,80,.22);border-radius:14px;padding:13px 14px 13px 17px;margin:0 0 14px;font-size:10px;line-height:1.55;background:linear-gradient(90deg,rgba(47,118,80,.08),rgba(255,255,255,.22))}.policy-note:before{content:"";position:absolute;left:0;top:12px;bottom:12px;width:3px;border-radius:8px;background:var(--green)}
        @media(max-width:680px){.aggregate-history-grid{grid-template-columns:1fr}.aggregate-history-head,.aggregate-history-row{grid-template-columns:50px 1fr 1fr 1.25fr;padding:9px 9px;gap:6px}.history-positive{font-size:9px}}
      `}</style>
      <div className="section-heading"><div><span className="kicker">HISTORICAL PERFORMANCE</span><h2>How has this setup behaved historically?</h2></div><span className="pill">{cashPolicy.n_sessions.toLocaleString()} sessions</span></div>
      <p className="section-intro">Same reconstructed spare-cash policy, now shown across 5, 10, 15, 30, 60 and 90 trading days. The table follows today&apos;s action and market condition.</p>
      {actionKey === "HOLD_CASH" ? <div className="policy-note"><b>HOLD CASH historically:</b> among {cashPolicy.hold_to_next_deploy.n.toLocaleString()} measurable cases, the next DEPLOY arrived after a median {cashPolicy.hold_to_next_deploy.median_wait_sessions} sessions. Waiting produced a cheaper eventual entry {pct(cashPolicy.hold_to_next_deploy.SPY.cheaper_entry_rate,0)} of the time for SPY and {pct(cashPolicy.hold_to_next_deploy.QQQ.cheaper_entry_rate,0)} for QQQ. This is not a bearish or sell signal.</div> : null}
      {actionKey === "WATCH" ? <div className="policy-note"><b>WATCH historically:</b> the next DEPLOY arrived after a median {cashPolicy.watch_to_next_deploy.median_wait_sessions} trading session in the measurable sample. WATCH means the setup is close, not that deployment has already qualified.</div> : null}
      {actionKey === "DEPLOY" ? <div className="policy-note"><b>DEPLOY historically:</b> the reconstructed policy passed the primary SPY/QQQ forward-quality gates and the tested 3/5-session delayed-entry comparisons. The additional 5D, 15D and 90D rows are reported from the same state ledger, not a separate backtest.</div> : null}
      <div className="aggregate-history-grid">
        <StateTable title={`Action · ${label(actionKey)}`} data={actionEvidence} />
        {conditionEvidence ? <StateTable title={`Condition · ${label(conditionKey)}`} data={conditionEvidence} /> : null}
      </div>
      <div className="archive-note">Proxy study {cashPolicy.date_range[0]} through {cashPolicy.date_range[1]} · verdict {cashPolicy.overall_proxy_policy_verdict}. {cashPolicy.note}</div>
    </section>;
  }

  if (!evidence) return <section className="card section-card"><div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Aggregate outcomes</h2></div></div><div className="notice"><CircleAlert size={16} /> Historical aggregate evidence is unavailable. No reconstructed episode ledger is substituted.</div></section>;
  const horizons = ["5", "10", "15", "30", "60"];
  const count = evidence.final_policy_validation.count;
  return <section className="card section-card">
    <div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>What happened after favorable RE-ENTRY signals?</h2></div><span className="pill">{count} episodes</span></div>
    <p className="section-intro">Archived aggregate evidence is shown only because the current cash-policy evidence could not be loaded.</p>
    <div className="aggregate-history-grid">
      {(["SPY","QQQ"] as const).map(asset => <div className="aggregate-history-card" key={asset}><div className="aggregate-history-title">{asset}</div><div className="aggregate-history-head"><span>Horizon</span><span>Average</span><span>Median</span><span>Positive</span></div>{horizons.map(h => { const x = evidence.final_policy_validation[asset][h]; if (!x) return null; return <div className="aggregate-history-row" key={`${asset}-${h}`}><b>{h}D</b><span>{pct(x.mean_return,2)}</span><span>{pct(x.median_return,2)}</span><span>{pct(x.positive_rate,0)}</span></div>; })}</div>)}
    </div>
    <div className="archive-note">Archived sample {evidence.provenance.sample_start} through {evidence.provenance.sample_end}. No row-by-row historical episode ledger is rendered.</div>
  </section>;
}
