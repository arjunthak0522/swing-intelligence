import { ChevronDown, CircleAlert, CircleCheck, Database, History } from "lucide-react";
import type { CanonicalHistoricalEvidence, HistoricalEpisodeLedger, HistoricalEpisodeRow } from "../lib/historicalEvidence";

function pct(value?: number | null, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
    : "-";
}

function num(value?: number | null, digits = 1) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "-";
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
        <strong>{h}D</strong><span>{pct(x.mean_return, 2)}</span><span>{pct(x.median_return, 2)}</span><span>{pct(x.positive_rate, 0)}</span><small>{x.n}</small>
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
        <b>{asset}</b><b>{h}D</b><span>{x.n}</span><span>{pct(x.mean_return, 2)}</span><span>{pct(x.median_return, 2)}</span><span>{pct(x.positive_rate, 0)}</span><span>{pct(x.p25_return, 2)} to {pct(x.p75_return, 2)}</span><span>{pct(x.median_mae, 2)}</span><span>{pct(x.p10_mae, 2)}</span><span>{pct(x.median_mfe, 2)}</span><span>{pct(x.false_start_rate_return_lt_minus_2pct, 0)}</span>
      </div>;
    }))}
  </div></div>;
}

function EpisodeDetails({ row }: { row: HistoricalEpisodeRow }) {
  const horizons = [5, 10, 30, 60];
  const state = row.next_state ? String(row.next_state).replaceAll("_", " ") : "ACTIVE";
  const spyTransition = row.SPY_transition_close as number | null;
  const qqqTransition = row.QQQ_transition_close as number | null;
  const spyStrict = row.SPY_strict_last_reenter_close_return as number | null;
  const qqqStrict = row.QQQ_strict_last_reenter_close_return as number | null;

  return <div className="episode-expanded">
    <div className="episode-story">
      <b>Period summary</b>
      <p>RE-ENTRY was active from {dateLabel(row.start)} through the {dateLabel(row.next_state_date)} close. Over that period, SPY returned <strong>{pct(row.SPY_episode_return, 2)}</strong> and QQQ returned <strong>{pct(row.QQQ_episode_return, 2)}</strong>.</p>
    </div>

    <div className="episode-detail-columns">
      <div className="episode-detail-panel">
        <b>Period details</b>
        <dl>
          <div><dt>SPY</dt><dd>${num(row.SPY_start_close, 2)} → ${num(spyTransition, 2)} <strong>{pct(row.SPY_episode_return, 2)}</strong></dd></div>
          <div><dt>QQQ</dt><dd>${num(row.QQQ_start_close, 2)} → ${num(qqqTransition, 2)} <strong>{pct(row.QQQ_episode_return, 2)}</strong></dd></div>
          <div><dt>Length</dt><dd>{row.reenter_sessions} {row.reenter_sessions === 1 ? "session" : "sessions"}</dd></div>
          <div><dt>State after period</dt><dd><strong>{state}</strong> on {dateLabel(row.next_state_date)}</dd></div>
        </dl>
      </div>
      <div className="episode-detail-panel">
        <b>Signal context</b>
        <dl>
          <div><dt>Signal source</dt><dd>{String(row.signal_source || "-").replaceAll("_", " ")}</dd></div>
          <div><dt>Similar-market state</dt><dd>{String(row.analog_at_start || "-")}</dd></div>
          <div><dt>Last RE-ENTRY close</dt><dd>{dateLabel(row.favorable_through)}</dd></div>
          <div><dt>Return before transition close</dt><dd>SPY {pct(spyStrict, 2)} · QQQ {pct(qqqStrict, 2)}</dd></div>
        </dl>
      </div>
    </div>

    <details className="forward-detail">
      <summary><span><b>What happened after the original signal?</b><small>Fixed forward returns from the first RE-ENTRY close</small></span><ChevronDown size={15} /></summary>
      <div className="row-forward-table">
        <div className="row-forward-head"><span>Asset</span>{horizons.map(h => <span key={h}>{h}D</span>)}</div>
        {(["SPY", "QQQ"] as const).map(asset => <div className="row-forward-row" key={asset}><b>{asset}</b>{horizons.map(h => <span key={h}>{pct(row[`${asset}_${h}d_from_start`] as number | null, 2)}</span>)}</div>)}
      </div>
    </details>
  </div>;
}

function EpisodePerformanceSummary({ ledger }: { ledger: HistoricalEpisodeLedger }) {
  const spy = ledger.summary.SPY_episode_return;
  const qqq = ledger.summary.QQQ_episode_return;
  return <div className="episode-performance-block">
    <div className="subsection-heading"><div><span className="kicker">HISTORICAL RE-ENTRY PERIODS</span><h3>What happened while each RE-ENTRY signal stayed active?</h3></div><span className="pill">{ledger.completed_episode_count} completed</span></div>
    <p className="history-note">Each period starts when RE-ENTRY first fires and ends at the close when that active period is over.</p>
    <div className="episode-performance-grid">
      <div className="episode-asset-card"><b>SPY</b><div><span>Average period return</span><strong>{pct(spy.mean, 2)}</strong></div><div><span>Median period return</span><strong>{pct(spy.median, 2)}</strong></div><div><span>Periods positive</span><strong>{pct(spy.positive_rate, 0)}</strong></div></div>
      <div className="episode-asset-card"><b>QQQ</b><div><span>Average period return</span><strong>{pct(qqq.mean, 2)}</strong></div><div><span>Median period return</span><strong>{pct(qqq.median, 2)}</strong></div><div><span>Periods positive</span><strong>{pct(qqq.positive_rate, 0)}</strong></div></div>
      <div className="duration-card"><span>Typical RE-ENTRY duration</span><strong>{num(ledger.summary.duration_sessions.median, 0)} sessions</strong><small>{num(ledger.summary.duration_sessions.mean, 1)} session average</small></div>
    </div>
  </div>;
}

function EpisodeLedger({ ledger }: { ledger: HistoricalEpisodeLedger | null }) {
  if (!ledger) return <details className="history-details"><summary><span><b>Historical RE-ENTRY periods</b><small>Period-by-period results</small></span><ChevronDown size={18} /></summary><div className="history-details-body"><div className="notice"><CircleAlert size={16} /> The reconstructed period history is unavailable, so row-level results are suppressed rather than invented.</div></div></details>;
  const rows = [...ledger.episodes].reverse();
  return <>
    <EpisodePerformanceSummary ledger={ledger} />
    <details className="history-details episode-ledger-details">
      <summary><span><b>Historical RE-ENTRY periods</b><small>Every completed period, newest first</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body">
        <div className="definition-box"><b>How to read it</b><p>Each row shows one RE-ENTRY period, how long it lasted, and the SPY and QQQ return over that period.</p></div>
        <div className="episode-table-scroll">
          <div className="episode-ledger-head"><span>RE-ENTRY period</span><span>Length</span><span>SPY result</span><span>QQQ result</span><span></span></div>
          <div className="episode-ledger">
            {rows.map((row, i) => <details className="episode-row" key={`${row.start}-${i}`}>
              <summary><div className="episode-summary-grid"><span className="period-cell"><b>{dateLabel(row.start)}</b><small>to {dateLabel(row.next_state_date)}</small></span><span>{row.reenter_sessions} {row.reenter_sessions === 1 ? "session" : "sessions"}</span><strong>{pct(row.SPY_episode_return, 2)}</strong><strong>{pct(row.QQQ_episode_return, 2)}</strong><ChevronDown size={15} /></div></summary>
              <EpisodeDetails row={row} />
            </details>)}
          </div>
        </div>
        <details className="period-methodology">
          <summary><span><b>Methodology & reconstruction details</b><small>Audit trail for this historical period view</small></span><ChevronDown size={15} /></summary>
          <div className="provenance-banner reconstructed"><Database size={16} /><div><b>RECONSTRUCTED - inspection layer</b><p>{ledger.provenance.data_note}</p><small>Frozen engine {ledger.provenance.engine_commit.slice(0, 12)} - rebuilt {dateLabel(ledger.provenance.rebuild_date)}</small></div></div>
        </details>
      </div>
    </details>
  </>;
}

export default function HistoricalEvidence({ evidence, ledger }: { evidence: CanonicalHistoricalEvidence | null; ledger: HistoricalEpisodeLedger | null }) {
  if (!evidence) return <section className="card section-card"><div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Prior RE-ENTRY results</h2></div></div><div className="notice"><CircleAlert size={16} /> Canonical historical evidence is temporarily unavailable. The app will not substitute a reconstruction for the archived validator.</div></section>;

  const retail = evidence.retail_validation_summary;
  const final = evidence.final_policy_validation;

  return <section className="card section-card historical-evidence-card">
    <style>{`
      .historical-evidence-card .section-intro{max-width:780px}.performance-hero{margin:14px 0 18px;padding:15px 16px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.38);display:flex;align-items:center;justify-content:space-between;gap:18px}.performance-hero strong{font-size:24px;display:block}.performance-hero span{font-size:10px;color:var(--muted)}.performance-hero p{margin:0;max-width:590px;color:var(--muted);font-size:11px;line-height:1.55}.performance-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:12px 0 18px}.asset-performance-card{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:rgba(255,255,255,.28)}.asset-performance-title{padding:14px 15px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line)}.asset-performance-title div{display:flex;align-items:baseline;gap:8px}.asset-performance-title span{font-weight:900;font-size:20px}.asset-performance-title small,.asset-performance-title>b{font-size:9px;color:var(--muted);text-transform:uppercase}.asset-performance-head,.asset-performance-row{display:grid;grid-template-columns:74px 1fr 1fr 1fr 42px;gap:8px;align-items:center;padding:10px 14px}.asset-performance-head{background:#efede7;color:var(--muted);font-size:8px;font-weight:800;text-transform:uppercase}.asset-performance-row{border-top:1px solid var(--line);font-size:11px;font-variant-numeric:tabular-nums}.asset-performance-row:first-of-type{border-top:0}.asset-performance-row strong{font-size:12px}.asset-performance-row small{color:var(--muted)}.subsection-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin:20px 0 8px}.subsection-heading h3{margin:3px 0 0;font-size:16px}.episode-performance-block{border-top:1px solid var(--line);margin-top:20px;padding-top:4px}.episode-performance-grid{display:grid;grid-template-columns:1fr 1fr .7fr;gap:10px;margin:12px 0 16px}.episode-asset-card,.duration-card{border:1px solid var(--line);border-radius:13px;padding:13px;background:rgba(255,255,255,.28)}.episode-asset-card>b{display:block;font-size:16px;margin-bottom:8px}.episode-asset-card>div{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 0;border-top:1px solid var(--line)}.episode-asset-card span,.duration-card span,.duration-card small{font-size:9px;color:var(--muted)}.episode-asset-card strong{font-size:12px}.duration-card{display:flex;flex-direction:column;justify-content:center}.duration-card strong{font-size:18px;margin:6px 0}.history-details{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.25);overflow:hidden}.history-details>summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:16px;padding:15px 16px}.history-details>summary::-webkit-details-marker,.episode-row>summary::-webkit-details-marker,.forward-detail>summary::-webkit-details-marker,.period-methodology>summary::-webkit-details-marker{display:none}.history-details>summary small{display:block;color:var(--muted);font-weight:400;margin-top:3px}.history-details>summary svg,.episode-row>summary svg,.forward-detail>summary svg,.period-methodology>summary svg{transition:transform .16s}.history-details[open]>summary svg,.episode-row[open]>summary svg,.forward-detail[open]>summary svg,.period-methodology[open]>summary svg{transform:rotate(180deg)}.history-details-body{border-top:1px solid var(--line);padding:16px}.history-note{font-size:10px;line-height:1.55;color:var(--muted)}.validation-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px}.validation-detail-table{min-width:1080px}.validation-detail-head,.validation-detail-row{display:grid;grid-template-columns:55px 70px 45px 78px 78px 72px 135px 105px 115px 105px 85px;gap:8px;align-items:center;padding:9px 12px}.validation-detail-head{background:#efede7;color:var(--muted);font-size:9px;font-weight:800;text-transform:uppercase}.validation-detail-row{border-top:1px solid var(--line);font-size:10px;font-variant-numeric:tabular-nums}.provenance-banner{display:flex;gap:10px;padding:13px;border-radius:12px;margin-bottom:12px}.provenance-banner.archived{background:#edf8f0}.provenance-banner.reconstructed{background:#fff6e5}.provenance-banner p{margin:3px 0;font-size:10px;line-height:1.5}.provenance-banner small{color:var(--muted);font-size:9px}.definition-box{border:1px solid var(--line);border-radius:12px;padding:13px;margin-bottom:14px}.definition-box p{margin:5px 0 0;color:var(--muted);font-size:10px;line-height:1.5}.episode-table-scroll{overflow-x:auto;border-radius:10px}.episode-ledger-head,.episode-summary-grid{display:grid;grid-template-columns:minmax(260px,2fr) 120px 120px 120px 28px;gap:18px;align-items:center;min-width:760px}.episode-ledger-head{padding:11px 18px;background:#efede7;text-transform:uppercase;font-size:8px;font-weight:800;color:var(--muted)}.episode-ledger{border:1px solid var(--line);border-top:0;border-radius:0 0 10px 10px;overflow:hidden;min-width:760px}.episode-row{border-top:1px solid var(--line)}.episode-row:first-child{border-top:0}.episode-row>summary{list-style:none;cursor:pointer;display:block;padding:0}.episode-summary-grid{padding:16px 18px;font-size:11px;font-variant-numeric:tabular-nums}.episode-summary-grid>strong{font-size:12px}.period-cell b{display:block;font-size:11px}.period-cell small{display:block;color:var(--muted);font-size:9px;margin-top:3px}.episode-expanded{background:rgba(248,247,243,.8);padding:16px;border-top:1px solid var(--line)}.episode-story{padding:12px 14px;border:1px solid var(--line);border-radius:11px;background:rgba(255,255,255,.5)}.episode-story>b{font-size:11px}.episode-story p{margin:5px 0 0;font-size:10px;line-height:1.6;color:var(--muted)}.episode-story strong{color:var(--text)}.episode-detail-columns{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.episode-detail-panel{border:1px solid var(--line);border-radius:11px;padding:12px;background:rgba(255,255,255,.28)}.episode-detail-panel>b{display:block;font-size:11px;margin-bottom:7px}.episode-detail-panel dl{margin:0}.episode-detail-panel dl>div{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding:6px 0;border-top:1px solid var(--line);font-size:9px}.episode-detail-panel dt{color:var(--muted)}.episode-detail-panel dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}.forward-detail{margin-top:10px;border-top:1px solid var(--line)}.forward-detail>summary,.period-methodology>summary{list-style:none;cursor:pointer;padding:11px 2px 2px;display:flex;align-items:center;justify-content:space-between;gap:12px}.forward-detail>summary small,.period-methodology>summary small{display:block;color:var(--muted);font-size:8px;margin-top:2px;font-weight:400}.period-methodology{margin-top:12px;border-top:1px solid var(--line)}.period-methodology .provenance-banner{margin:10px 0 0}.row-forward-table{margin-top:8px;border:1px solid var(--line);border-radius:9px;overflow:hidden}.row-forward-head,.row-forward-row{display:grid;grid-template-columns:1.3fr repeat(4,1fr);gap:8px;padding:8px 10px;font-size:9px}.row-forward-head{background:#efede7;color:var(--muted);font-weight:800}.row-forward-row{border-top:1px solid var(--line)}.history-method{margin-top:15px;color:var(--muted);font-size:10px;line-height:1.5}.evidence-method-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.evidence-method-grid>div{border:1px solid var(--line);border-radius:12px;padding:12px}.evidence-method-grid b{display:block;margin-bottom:5px}.evidence-method-grid p{margin:0;color:var(--muted);font-size:10px;line-height:1.5}@media(max-width:760px){.performance-grid,.episode-performance-grid,.evidence-method-grid,.episode-detail-columns{grid-template-columns:1fr}.performance-hero{align-items:flex-start;flex-direction:column}.asset-performance-head,.asset-performance-row{grid-template-columns:62px 1fr 1fr 1fr 34px;padding-left:10px;padding-right:10px}}
    `}</style>

    <div className="section-heading"><div><span className="kicker">HISTORICAL PERFORMANCE</span><h2>What happened after RE-ENTRY?</h2></div><span className="pill">ARCHIVED VALIDATION</span></div>
    <p className="section-intro">The primary view is performance first: average return, median return and percentage of positive outcomes after prior RE-ENTRY signals. Research provenance and reconstruction details are available below without crowding the answer.</p>

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

    <EpisodeLedger ledger={ledger} />

    <details className="history-details">
      <summary><span><b>About this evidence</b><small>Why the archived validator and reconstructed period counts differ</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body">
        <div className="evidence-method-grid">
          <div><b>Archived entry-timing validation</b><p>{retail.final_independent_reentry_episodes} independent retail opportunities are preserved in the canonical validation. The detailed frozen validator contains {final.count} cooldown-selected events. These are validation samples, not contiguous favorable periods.</p></div>
          <div><b>Reconstructed continuous periods</b><p>{ledger ? `${ledger.episode_count} contiguous RE-ENTRY periods are available for inspection.` : "The reconstructed row ledger is currently unavailable."} Consecutive favorable days are grouped into one period, so this count is expected to differ from the archived validation counts.</p></div>
        </div>
      </div>
    </details>

    <details className="history-details">
      <summary><span><b>Current episode origin audit</b><small>Why the current episode begins Aug 28, 2026</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body"><div className="history-table compact-history-table"><div className="history-head"><span>Date</span><span>Archived state</span><span>Start-day close</span></div>{evidence.latest_policy_rows.map(row => <div className="history-row" key={row.date}><b>{dateLabel(row.date)}</b><span>{row.final_policy_signal}</span><span>{row.SPY ? `SPY $${row.SPY.toFixed(2)} - QQQ $${row.QQQ?.toFixed(2)}` : "-"}</span></div>)}</div><div className="notice"><CircleCheck size={16} /> Aug 27 was NO RE-ENTRY SETUP. Aug 28 changed to RE-ENTER and the archived completed closes through Sep 4 stayed RE-ENTER; the production episode continued afterward.</div></div>
    </details>

    <div className="history-method"><History size={12} /> Archived aggregate source: original canonical GitHub Actions artifact - run {evidence.provenance.workflow_run_id} - engine <code>{evidence.provenance.engine_commit.slice(0, 12)}</code>. Reconstructed rows remain separately labeled and never replace the archived aggregate statistics.</div>
  </section>;
}
