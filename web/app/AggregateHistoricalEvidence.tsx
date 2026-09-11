import { CircleAlert } from "lucide-react";
import type { CanonicalHistoricalEvidence } from "../lib/historicalEvidence";

const pct = (value?: number | null, digits = 1) => typeof value === "number" && Number.isFinite(value)
  ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
  : "-";

export default function AggregateHistoricalEvidence({ evidence }: { evidence: CanonicalHistoricalEvidence | null }) {
  if (!evidence) return <section className="card section-card"><div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Aggregate outcomes</h2></div></div><div className="notice"><CircleAlert size={16} /> Historical aggregate evidence is unavailable. No reconstructed episode ledger is substituted.</div></section>;
  const horizons = ["5", "10", "30", "60"];
  const count = evidence.final_policy_validation.count;
  return <section className="card section-card">
    <style>{`.aggregate-history-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.aggregate-history-card{border:1px solid var(--line);border-radius:14px;overflow:hidden}.aggregate-history-head,.aggregate-history-row{display:grid;grid-template-columns:70px 1fr 1fr 1fr;gap:8px;padding:10px 12px;align-items:center}.aggregate-history-head{background:#efede7;font-size:8px;font-weight:800;color:var(--muted);text-transform:uppercase}.aggregate-history-row{border-top:1px solid var(--line);font-size:10px}.aggregate-history-title{padding:12px;font-size:15px;font-weight:900}.archive-note{margin-top:12px;font-size:9px;line-height:1.5;color:var(--muted)}@media(max-width:680px){.aggregate-history-grid{grid-template-columns:1fr}}`}</style>
    <div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>What happened after favorable RE-ENTRY signals?</h2></div><span className="pill">{count} episodes</span></div>
    <p className="section-intro">Aggregate archived evidence only. This predecessor validator is supporting context and is not presented as validation of REENTRY_UNIFIED_v1.</p>
    <div className="aggregate-history-grid">
      {(["SPY","QQQ"] as const).map(asset => <div className="aggregate-history-card" key={asset}><div className="aggregate-history-title">{asset}</div><div className="aggregate-history-head"><span>Horizon</span><span>Average</span><span>Median</span><span>Positive</span></div>{horizons.map(h => { const x = evidence.final_policy_validation[asset][h]; return <div className="aggregate-history-row" key={`${asset}-${h}`}><b>{h}D</b><span>{pct(x.mean_return,2)}</span><span>{pct(x.median_return,2)}</span><span>{pct(x.positive_rate,0)}</span></div>; })}</div>)}
    </div>
    <div className="archive-note">Archived sample {evidence.provenance.sample_start} through {evidence.provenance.sample_end}. No row-by-row historical episode ledger is rendered.</div>
  </section>;
}
