import { CircleAlert, CircleCheck, ChevronDown } from "lucide-react";
import type { CanonicalHistoricalEvidence, HorizonMetric } from "../lib/historicalEvidence";

function pct(value?: number | null, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
    : "—";
}

function dateLabel(value?: string | null) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function MetricRow({ horizon, spy, qqq }: { horizon: string; spy: HorizonMetric; qqq: HorizonMetric }) {
  return <div className="history-row history-row-wide">
    <b>{horizon}D</b>
    <span><strong>{pct(spy.median_return, 2)}</strong><small>median</small></span>
    <span>{pct(spy.positive_rate, 0)}<small>positive</small></span>
    <span><strong>{pct(qqq.median_return, 2)}</strong><small>median</small></span>
    <span>{pct(qqq.positive_rate, 0)}<small>positive</small></span>
  </div>;
}

function FullMetricTable({ evidence }: { evidence: CanonicalHistoricalEvidence }) {
  const horizons = ["5", "7", "10", "15", "30", "60"];
  return <div className="validation-scroll"><div className="validation-detail-table">
    <div className="validation-detail-head"><span>Horizon</span><span>Asset</span><span>n</span><span>Median</span><span>Mean</span><span>Positive</span><span>25th–75th</span><span>Median adverse</span><span>10th-pct adverse</span><span>Median favorable</span><span>False start*</span></div>
    {horizons.flatMap((h) => (["SPY", "QQQ"] as const).map((asset) => {
      const x = evidence.final_policy_validation[asset][h];
      return <div className="validation-detail-row" key={`${asset}-${h}`}>
        <b>{h}D</b><b>{asset}</b><span>{x.n}</span><strong>{pct(x.median_return, 2)}</strong><span>{pct(x.mean_return, 2)}</span><span>{pct(x.positive_rate, 0)}</span><span>{pct(x.p25_return, 2)} to {pct(x.p75_return, 2)}</span><span>{pct(x.median_mae, 2)}</span><span>{pct(x.p10_mae, 2)}</span><span>{pct(x.median_mfe, 2)}</span><span>{pct(x.false_start_rate_return_lt_minus_2pct, 0)}</span>
      </div>;
    }))}
  </div></div>;
}

export default function HistoricalEvidence({ evidence }: { evidence: CanonicalHistoricalEvidence | null }) {
  if (!evidence) return <section className="card section-card"><div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Prior RE-ENTRY results</h2></div></div><div className="notice"><CircleAlert size={16} /> Canonical historical evidence is temporarily unavailable. The app will not substitute a freshly reconstructed backtest.</div></section>;

  const retail = evidence.retail_validation_summary;
  const final = evidence.final_policy_validation;
  const headlineHorizons = ["5", "10", "30", "60"];

  return <section className="card section-card historical-evidence-card">
    <style>{`
      .historical-evidence-card .history-summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:0 0 16px}.historical-evidence-card .history-summary-grid>div{border:1px solid var(--line);border-radius:13px;padding:14px;background:rgba(255,255,255,.35)}.historical-evidence-card .history-summary-grid small,.historical-evidence-card .history-summary-grid span{display:block;color:var(--muted);font-size:10px}.historical-evidence-card .history-summary-grid strong{display:block;margin:7px 0 3px;font-size:22px}.history-head-wide,.history-row-wide{grid-template-columns:.55fr 1fr 1fr 1fr 1fr!important}.history-row-wide span{display:flex;gap:6px;align-items:baseline}.history-row-wide small{color:var(--muted);font-size:9px}.history-details{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.25);overflow:hidden}.history-details>summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:16px;padding:15px 16px}.history-details>summary::-webkit-details-marker{display:none}.history-details>summary span{display:block}.history-details>summary small{display:block;color:var(--muted);font-weight:400;margin-top:3px}.history-details>summary svg{transition:transform .16s}.history-details[open]>summary svg{transform:rotate(180deg)}.history-details-body{border-top:1px solid var(--line);padding:0 16px 16px}.history-note{font-size:11px;line-height:1.5;color:var(--muted)}.validation-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px}.validation-detail-table{min-width:1080px}.validation-detail-head,.validation-detail-row{display:grid;grid-template-columns:70px 55px 45px 78px 78px 72px 135px 105px 115px 105px 85px;gap:8px;align-items:center;padding:9px 12px}.validation-detail-head{background:#efede7;color:var(--muted);font-size:9px;font-weight:800;text-transform:uppercase}.validation-detail-row{border-top:1px solid var(--line);font-size:10px;font-variant-numeric:tabular-nums}.compact-history-table{margin-top:14px}.history-method{margin-top:15px;color:var(--muted);font-size:10px;line-height:1.5}@media(max-width:760px){.historical-evidence-card .history-summary-grid{grid-template-columns:1fr 1fr}.history-head-wide,.history-row-wide{grid-template-columns:.55fr 1fr 1fr!important}.history-head-wide span:nth-child(3),.history-head-wide span:nth-child(5),.history-row-wide span:nth-child(3),.history-row-wide span:nth-child(5){display:none}.historical-evidence-card .history-summary-grid strong{font-size:18px}}
    `}</style>
    <div className="section-heading">
      <div><span className="kicker">HISTORICAL EVIDENCE</span><h2>What happened after prior RE-ENTRY signals?</h2></div>
      <span className="pill">{retail.final_independent_reentry_episodes} independent episodes</span>
    </div>
    <p className="section-intro">The headline results below are the original validated RE-ENTRY history. Nothing here is rebuilt from today&apos;s mutable market data.</p>

    <div className="history-summary-grid">
      <div><small>Independent RE-ENTRY episodes</small><strong>{retail.final_independent_reentry_episodes}</strong><span>validated retail history</span></div>
      <div><small>SPY median after 30D</small><strong>{pct(retail.SPY_30D_median_after_signal, 2)}</strong><span>after signal fired</span></div>
      <div><small>QQQ median after 30D</small><strong>{pct(retail.QQQ_30D_median_after_signal, 2)}</strong><span>after signal fired</span></div>
      <div><small>Validation status</small><strong>VALIDATED</strong><span>canonical policy</span></div>
    </div>

    <div className="history-table">
      <div className="history-head history-head-wide"><span>Horizon</span><span>SPY median</span><span>SPY positive</span><span>QQQ median</span><span>QQQ positive</span></div>
      {headlineHorizons.map((h) => <MetricRow key={h} horizon={h} spy={final.SPY[h]} qqq={final.QQQ[h]} />)}
    </div>

    <details className="history-details">
      <summary><span><b>Complete canonical validation</b><small>All archived 5D, 7D, 10D, 15D, 30D and 60D outcome statistics</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body">
        <div className="notice"><CircleCheck size={16} /> Exact archived final-policy validator: <b>{final.count} cooldown-selected validation events</b>, sample {dateLabel(evidence.provenance.sample_start)} through {dateLabel(evidence.provenance.sample_end)}.</div>
        <p className="history-note">The 193 validator events and the 189 independent retail episodes are two preserved validation definitions and are intentionally labeled separately rather than forced into one count.</p>
        <FullMetricTable evidence={evidence} />
        <p className="history-note">* False start = forward return below -2% at that horizon. “Adverse” and “favorable” are maximum adverse/favorable excursion statistics from the archived validation run.</p>
      </div>
    </details>

    <details className="history-details">
      <summary><span><b>Current episode origin audit</b><small>Why the current RE-ENTRY episode starts Aug 28, 2026</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body">
        <div className="history-table compact-history-table">
          <div className="history-head"><span>Date</span><span>Official archived state</span><span>Start-day close</span></div>
          {evidence.latest_policy_rows.map((row) => <div className="history-row" key={row.date}><b>{dateLabel(row.date)}</b><span>{row.final_policy_signal}</span><span>{row.SPY ? `SPY $${row.SPY.toFixed(2)} · QQQ $${row.QQQ?.toFixed(2)}` : "—"}</span></div>)}
        </div>
        <div className="notice"><CircleCheck size={16} /> Aug 27 was NO RE-ENTRY SETUP; Aug 28 changed to RE-ENTER and every archived completed close through Sep 4 remained RE-ENTER. The Sep 8 production close also remained RE-ENTER, so this is one continuous current episode.</div>
      </div>
    </details>

    <details className="history-details">
      <summary><span><b>Every historical episode row</b><small>Row-by-row pre-launch episode history and realized episode returns</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body">
        <div className="notice"><CircleAlert size={16} /> The original canonical validation preserved the aggregate outcomes above but did not preserve a complete row-by-row list of all historical episode dates in the surviving artifact. The older episode-timing artifacts are no longer retrievable. RE-ENTRY will not manufacture those rows from revised historical data.</div>
        <p className="history-note">Going forward, every live episode is persisted from its first RE-ENTRY close through its last consecutive favorable close. The following WAIT / NO SETUP date is recorded separately and is not included in the episode return. This is historical measurement, not an exit or sell rule.</p>
      </div>
    </details>

    <div className="history-method">Source: original canonical GitHub Actions artifact · run {evidence.provenance.workflow_run_id} · engine <code>{evidence.provenance.engine_commit.slice(0, 12)}</code> · sample through {dateLabel(evidence.provenance.sample_end)}.</div>
  </section>;
}
