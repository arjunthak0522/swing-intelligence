import { ChevronDown, CircleAlert, CircleCheck, History } from "lucide-react";
import type { CanonicalHistoricalEvidence } from "../lib/historicalEvidence";

function pct(value?: number | null, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
    : "-";
}

function dateLabel(value?: string | null) {
  if (!value) return "-";
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

const headlineHorizons = ["5", "10", "30", "60"];
const allHorizons = ["5", "7", "10", "15", "30", "60"];

function PerformanceAssetTable({ evidence, asset }: { evidence: CanonicalHistoricalEvidence; asset: "SPY" | "QQQ" }) {
  return <div className="asset-performance-card">
    <div className="asset-performance-title"><div><span>{asset}</span><small>{asset === "SPY" ? "S&P 500" : "Nasdaq 100"}</small></div><b>After RE-ENTRY</b></div>
    <div className="asset-performance-head"><span>Horizon</span><span>Average</span><span>Median</span><span>Positive</span><span>n</span></div>
    {headlineHorizons.map(h => {
      const x = evidence.final_policy_validation[asset][h];
      return <div className="asset-performance-row" key={`${asset}-${h}`}>
        <strong>{h}D</strong><span>{pct(x.mean_return, 2)}</span><span>{pct(x.median_return, 2)}</span><span>{pct(x.positive_rate, 0).replace(/^\+/, "")}</span><small>{x.n}</small>
      </div>;
    })}
  </div>;
}

function FullMetricTable({ evidence }: { evidence: CanonicalHistoricalEvidence }) {
  return <div className="validation-scroll"><div className="validation-detail-table">
    <div className="validation-detail-head"><span>Asset</span><span>Horizon</span><span>n</span><span>Average</span><span>Median</span><span>% positive</span><span>25th-75th</span><span>Typical worst</span><span>Bad-tail worst</span><span>Typical best</span><span>False start*</span></div>
    {(["SPY", "QQQ"] as const).flatMap(asset => allHorizons.map(h => {
      const x = evidence.final_policy_validation[asset][h];
      return <div className="validation-detail-row" key={`${asset}-${h}`}>
        <b>{asset}</b><b>{h}D</b><span>{x.n}</span><span>{pct(x.mean_return, 2)}</span><span>{pct(x.median_return, 2)}</span><span>{pct(x.positive_rate, 0).replace(/^\+/, "")}</span><span>{pct(x.p25_return, 2)} to {pct(x.p75_return, 2)}</span><span>{pct(x.median_mae, 2)}</span><span>{pct(x.p10_mae, 2)}</span><span>{pct(x.median_mfe, 2)}</span><span>{pct(x.false_start_rate_return_lt_minus_2pct, 0).replace(/^\+/, "")}</span>
      </div>;
    }))}
  </div></div>;
}

export default function HistoricalEvidence({ evidence }: { evidence: CanonicalHistoricalEvidence | null }) {
  if (!evidence) return <section className="card section-card"><div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Prior RE-ENTRY results</h2></div></div><div className="notice"><CircleAlert size={16} /> Canonical historical evidence is temporarily unavailable. The app will not substitute a reconstruction for the archived validator.</div></section>;

  const retail = evidence.retail_validation_summary;

  return <section className="card section-card historical-evidence-card">
    <style>{`
      .historical-evidence-card .section-intro{max-width:780px}.performance-hero{margin:14px 0 18px;padding:15px 16px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.38);display:flex;align-items:center;justify-content:space-between;gap:18px}.performance-hero strong{font-size:24px;display:block}.performance-hero span{font-size:10px;color:var(--muted)}.performance-hero p{margin:0;max-width:590px;color:var(--muted);font-size:11px;line-height:1.55}.performance-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:12px 0 18px}.asset-performance-card{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:rgba(255,255,255,.28)}.asset-performance-title{padding:14px 15px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line)}.asset-performance-title div{display:flex;align-items:baseline;gap:8px}.asset-performance-title span{font-weight:900;font-size:20px}.asset-performance-title small,.asset-performance-title>b{font-size:9px;color:var(--muted);text-transform:uppercase}.asset-performance-head,.asset-performance-row{display:grid;grid-template-columns:74px 1fr 1fr 1fr 42px;gap:8px;align-items:center;padding:10px 14px}.asset-performance-head{background:#efede7;color:var(--muted);font-size:8px;font-weight:800;text-transform:uppercase}.asset-performance-row{border-top:1px solid var(--line);font-size:11px;font-variant-numeric:tabular-nums}.asset-performance-row:first-of-type{border-top:0}.asset-performance-row strong{font-size:12px}.asset-performance-row small{color:var(--muted)}.history-details{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.25);overflow:hidden}.history-details>summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:16px;padding:15px 16px}.history-details>summary::-webkit-details-marker{display:none}.history-details>summary small{display:block;color:var(--muted);font-weight:400;margin-top:3px}.history-details>summary svg{transition:transform .16s}.history-details[open]>summary svg{transform:rotate(180deg)}.history-details-body{border-top:1px solid var(--line);padding:16px}.history-note{font-size:10px;line-height:1.55;color:var(--muted)}.validation-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px}.validation-detail-table{min-width:1080px}.validation-detail-head,.validation-detail-row{display:grid;grid-template-columns:55px 70px 45px 78px 78px 72px 135px 105px 115px 105px 85px;gap:8px;align-items:center;padding:9px 12px}.validation-detail-head{background:#efede7;color:var(--muted);font-size:9px;font-weight:800;text-transform:uppercase}.validation-detail-row{border-top:1px solid var(--line);font-size:10px;font-variant-numeric:tabular-nums}.provenance-banner{display:flex;gap:10px;padding:13px;border-radius:12px;margin-bottom:12px}.provenance-banner.archived{background:#edf8f0}.provenance-banner p{margin:3px 0;font-size:10px;line-height:1.5}.provenance-banner small{color:var(--muted);font-size:9px}.history-method{margin-top:15px;color:var(--muted);font-size:10px;line-height:1.5}@media(max-width:760px){.performance-grid{grid-template-columns:1fr}.performance-hero{align-items:flex-start;flex-direction:column}.asset-performance-head,.asset-performance-row{grid-template-columns:62px 1fr 1fr 1fr 34px;padding-left:10px;padding-right:10px}}
    `}</style>

    <div className="section-heading"><div><span className="kicker">HISTORICAL PERFORMANCE</span><h2>What happened after RE-ENTRY?</h2></div><span className="pill">ARCHIVED VALIDATION</span></div>
    <p className="section-intro">The primary view is performance first: average return, median return and percentage of positive outcomes after prior RE-ENTRY signals. Research provenance is available below without crowding the answer.</p>

    <div className="performance-hero"><div><span>INDEPENDENT RE-ENTRY OPPORTUNITIES</span><strong>{retail.final_independent_reentry_episodes}</strong></div><p>The core timing policy remains validated. The tables below use the preserved archived validation statistics rather than rebuilding them from mutable historical vendor data.</p></div>

    <div className="performance-grid"><PerformanceAssetTable evidence={evidence} asset="SPY" /><PerformanceAssetTable evidence={evidence} asset="QQQ" /></div>

    <details className="history-details">
      <summary><span><b>More horizons and statistical detail</b><small>7D, 15D, quartiles, adverse/favorable excursion and false-start rates</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body">
        <div className="provenance-banner archived"><CircleCheck size={16} /><div><b>ARCHIVED / VALIDATED</b><p>Copied from the original canonical validation artifact and not recomputed from current historical vendor data.</p><small>Run {evidence.provenance.workflow_run_id} - engine {evidence.provenance.engine_commit.slice(0, 12)} - sample {dateLabel(evidence.provenance.sample_start)} through {dateLabel(evidence.provenance.sample_end)}</small></div></div>
        <FullMetricTable evidence={evidence} />
        <p className="history-note">* False start = forward return below -2% at that horizon. Typical worst = median maximum adverse excursion. Bad-tail worst = 10th-percentile maximum adverse excursion. Typical best = median maximum favorable excursion.</p>
      </div>
    </details>

    <div className="history-method"><History size={12} /> Archived aggregate source: original canonical GitHub Actions artifact - run {evidence.provenance.workflow_run_id} - engine <code>{evidence.provenance.engine_commit.slice(0, 12)}</code>.</div>
  </section>;
}
