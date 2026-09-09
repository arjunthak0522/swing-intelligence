import { CircleAlert, CircleCheck, ChevronDown, Database, History } from "lucide-react";
import type { CanonicalHistoricalEvidence, HistoricalEpisodeLedger, HistoricalEpisodeRow, HorizonMetric } from "../lib/historicalEvidence";

function pct(value?: number | null, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
    : "—";
}

function num(value?: number | null, digits = 1) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function dateLabel(value?: string | null) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function FullMetricTable({ evidence }: { evidence: CanonicalHistoricalEvidence }) {
  const horizons = ["5", "7", "10", "15", "30", "60"];
  return <div className="validation-scroll"><div className="validation-detail-table">
    <div className="validation-detail-head"><span>Horizon</span><span>Asset</span><span>n</span><span>Median</span><span>Average</span><span>% positive</span><span>25th–75th</span><span>Typical worst</span><span>Bad-tail worst</span><span>Typical best</span><span>False start*</span></div>
    {horizons.flatMap((h) => (["SPY", "QQQ"] as const).map((asset) => {
      const x = evidence.final_policy_validation[asset][h];
      return <div className="validation-detail-row" key={`${asset}-${h}`}>
        <b>{h}D</b><b>{asset}</b><span>{x.n}</span><strong>{pct(x.median_return, 2)}</strong><span>{pct(x.mean_return, 2)}</span><span>{pct(x.positive_rate, 0)}</span><span>{pct(x.p25_return, 2)} to {pct(x.p75_return, 2)}</span><span>{pct(x.median_mae, 2)}</span><span>{pct(x.p10_mae, 2)}</span><span>{pct(x.median_mfe, 2)}</span><span>{pct(x.false_start_rate_return_lt_minus_2pct, 0)}</span>
      </div>;
    }))}
  </div></div>;
}

function HeadlineMetricRows({ evidence }: { evidence: CanonicalHistoricalEvidence }) {
  const horizons = ["5", "7", "10", "15", "30", "60"];
  return <div className="headline-results-scroll"><div className="headline-results">
    <div className="headline-results-head"><span>Horizon</span><span>Asset</span><span>n</span><span>Median</span><span>Average</span><span>% positive</span></div>
    {horizons.flatMap((h) => (["SPY", "QQQ"] as const).map(asset => {
      const x = evidence.final_policy_validation[asset][h];
      return <div className="headline-results-row" key={`${h}-${asset}`}><b>{h}D</b><b>{asset}</b><span>{x.n}</span><strong>{pct(x.median_return, 2)}</strong><span>{pct(x.mean_return, 2)}</span><span>{pct(x.positive_rate, 0)}</span></div>;
    }))}
  </div></div>;
}

function EpisodeDetails({ row }: { row: HistoricalEpisodeRow }) {
  const horizons = [5, 10, 30, 60];
  return <div className="episode-expanded">
    <div className="episode-detail-grid">
      <div><small>SPY start → favorable-through close</small><b>${num(row.SPY_start_close, 2)} → ${num(row.SPY_favorable_through_close, 2)}</b></div>
      <div><small>QQQ start → favorable-through close</small><b>${num(row.QQQ_start_close, 2)} → ${num(row.QQQ_favorable_through_close, 2)}</b></div>
      <div><small>SPY max gain / worst move while favorable</small><b>{pct(row.SPY_max_gain_during_episode, 2)} / {pct(row.SPY_max_adverse_during_episode, 2)}</b></div>
      <div><small>QQQ max gain / worst move while favorable</small><b>{pct(row.QQQ_max_gain_during_episode, 2)} / {pct(row.QQQ_max_adverse_during_episode, 2)}</b></div>
      <div><small>Signal source</small><b>{String(row.signal_source || "—").replaceAll("_", " ")}</b></div>
      <div><small>Similar-past-markets state at start</small><b>{String(row.analog_at_start || "—")}</b></div>
    </div>
    <div className="row-forward-table">
      <div className="row-forward-head"><span>From first RE-ENTER close</span>{horizons.map(h => <span key={h}>{h}D</span>)}</div>
      {(["SPY", "QQQ"] as const).map(asset => <div className="row-forward-row" key={asset}><b>{asset}</b>{horizons.map(h => <span key={h}>{pct(row[`${asset}_${h}d_from_start`] as number | null, 2)}</span>)}</div>)}
    </div>
    <p className="history-note">These row-level fixed-horizon numbers are reconstructed close-to-close diagnostics from the first RE-ENTER close. They are not substituted for the archived canonical validation statistics above.</p>
  </div>;
}

function EpisodeLedger({ ledger }: { ledger: HistoricalEpisodeLedger | null }) {
  if (!ledger) return <details className="history-details"><summary><span><b>All historical RE-ENTRY episodes</b><small>Episode-by-episode results</small></span><ChevronDown size={18} /></summary><div className="history-details-body"><div className="notice"><CircleAlert size={16} /> The reconstructed episode ledger is unavailable, so row-level results are suppressed rather than invented.</div></div></details>;

  const completed = ledger.episodes.filter(x => x.next_state_date);
  const rows = [...ledger.episodes].reverse();
  const spy = ledger.summary.SPY_episode_return;
  const qqq = ledger.summary.QQQ_episode_return;

  return <details className="history-details episode-ledger-details">
    <summary><span><b>All {ledger.episode_count} reconstructed continuous RE-ENTRY episodes</b><small>Expand to inspect every historical episode, newest first</small></span><ChevronDown size={18} /></summary>
    <div className="history-details-body">
      <div className="provenance-banner reconstructed"><Database size={16} /><div><b>RECONSTRUCTED — not the archived validator</b><p>{ledger.provenance.data_note}</p><small>Frozen engine {ledger.provenance.engine_commit.slice(0, 12)} · rebuilt {dateLabel(ledger.provenance.rebuild_date)}</small></div></div>
      <div className="definition-box"><b>Exactly what an episode means here</b><p>{ledger.definition}</p><p>{ledger.forward_return_definition}</p></div>
      <div className="episode-summary-strip">
        <div><small>Completed episodes</small><strong>{completed.length}</strong></div>
        <div><small>SPY episode return</small><strong>{pct(spy.median, 2)} median</strong><span>{pct(spy.mean, 2)} avg · {pct(spy.positive_rate, 0)} positive</span></div>
        <div><small>QQQ episode return</small><strong>{pct(qqq.median, 2)} median</strong><span>{pct(qqq.mean, 2)} avg · {pct(qqq.positive_rate, 0)} positive</span></div>
        <div><small>Typical duration</small><strong>{num(ledger.summary.duration_sessions.median, 0)} sessions</strong><span>{num(ledger.summary.duration_sessions.mean, 1)} average</span></div>
      </div>
      <div className="episode-ledger-head"><span>RE-ENTRY began</span><span>Favorable through</span><span>Next state</span><span>Sessions</span><span>SPY episode</span><span>QQQ episode</span><span></span></div>
      <div className="episode-ledger">
        {rows.map((row, i) => <details className="episode-row" key={`${row.start}-${i}`}>
          <summary>
            <span><b>{dateLabel(row.start)}</b></span>
            <span>{dateLabel(row.favorable_through)}</span>
            <span>{row.next_state_date ? <><b>{String(row.next_state).replaceAll("_", " ")}</b><small>{dateLabel(row.next_state_date)}</small></> : <b>ACTIVE</b>}</span>
            <span>{row.reenter_sessions}</span>
            <strong>{pct(row.SPY_episode_return, 2)}</strong>
            <strong>{pct(row.QQQ_episode_return, 2)}</strong>
            <ChevronDown size={15} />
          </summary>
          <EpisodeDetails row={row} />
        </details>)}
      </div>
    </div>
  </details>;
}

export default function HistoricalEvidence({ evidence, ledger }: { evidence: CanonicalHistoricalEvidence | null; ledger: HistoricalEpisodeLedger | null }) {
  if (!evidence) return <section className="card section-card"><div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Prior RE-ENTRY results</h2></div></div><div className="notice"><CircleAlert size={16} /> Canonical historical evidence is temporarily unavailable. The app will not substitute a reconstruction for the archived validator.</div></section>;

  const retail = evidence.retail_validation_summary;
  const final = evidence.final_policy_validation;

  return <section className="card section-card historical-evidence-card">
    <style>{`
      .historical-evidence-card .history-summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 18px}.historical-evidence-card .history-summary-grid>div{border:1px solid var(--line);border-radius:13px;padding:14px;background:rgba(255,255,255,.35)}.historical-evidence-card .history-summary-grid small,.historical-evidence-card .history-summary-grid span{display:block;color:var(--muted);font-size:10px}.historical-evidence-card .history-summary-grid strong{display:block;margin:7px 0 3px;font-size:20px}.history-explainer{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}.history-explainer>div{border:1px solid var(--line);border-radius:14px;padding:14px}.history-explainer b{display:block;margin-bottom:6px}.history-explainer p{margin:0;color:var(--muted);font-size:11px;line-height:1.55}.source-badge{display:inline-flex!important;width:auto!important;border-radius:999px;padding:4px 8px;margin-bottom:8px;font-size:9px!important;font-weight:800}.source-badge.archived{background:#e7f6ec;color:#21643b}.source-badge.reconstructed{background:#fff1d6;color:#825400}.headline-results-scroll,.validation-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px}.headline-results{min-width:650px}.headline-results-head,.headline-results-row{display:grid;grid-template-columns:70px 65px 55px 105px 105px 95px;gap:10px;align-items:center;padding:10px 12px}.headline-results-head{background:#efede7;color:var(--muted);font-size:9px;font-weight:800;text-transform:uppercase}.headline-results-row{border-top:1px solid var(--line);font-size:11px;font-variant-numeric:tabular-nums}.history-details{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.25);overflow:hidden}.history-details>summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:16px;padding:15px 16px}.history-details>summary::-webkit-details-marker,.episode-row>summary::-webkit-details-marker{display:none}.history-details>summary span{display:block}.history-details>summary small{display:block;color:var(--muted);font-weight:400;margin-top:3px}.history-details>summary svg,.episode-row>summary svg{transition:transform .16s}.history-details[open]>summary svg,.episode-row[open]>summary svg{transform:rotate(180deg)}.history-details-body{border-top:1px solid var(--line);padding:16px}.history-note{font-size:10px;line-height:1.55;color:var(--muted)}.validation-detail-table{min-width:1080px}.validation-detail-head,.validation-detail-row{display:grid;grid-template-columns:70px 55px 45px 78px 78px 72px 135px 105px 115px 105px 85px;gap:8px;align-items:center;padding:9px 12px}.validation-detail-head{background:#efede7;color:var(--muted);font-size:9px;font-weight:800;text-transform:uppercase}.validation-detail-row{border-top:1px solid var(--line);font-size:10px;font-variant-numeric:tabular-nums}.provenance-banner{display:flex;gap:10px;padding:13px;border-radius:12px;margin-bottom:12px}.provenance-banner.archived{background:#edf8f0}.provenance-banner.reconstructed{background:#fff6e5}.provenance-banner p{margin:3px 0;font-size:10px;line-height:1.5}.provenance-banner small{color:var(--muted);font-size:9px}.definition-box{border:1px solid var(--line);border-radius:12px;padding:13px;margin-bottom:14px}.definition-box p{margin:5px 0 0;color:var(--muted);font-size:10px;line-height:1.5}.episode-summary-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}.episode-summary-strip>div{border:1px solid var(--line);border-radius:12px;padding:11px}.episode-summary-strip small,.episode-summary-strip span{display:block;color:var(--muted);font-size:9px}.episode-summary-strip strong{display:block;margin:5px 0;font-size:14px}.episode-ledger-head,.episode-row>summary{display:grid;grid-template-columns:1.15fr 1.15fr 1.4fr .65fr .9fr .9fr 20px;gap:8px;align-items:center}.episode-ledger-head{padding:9px 10px;background:#efede7;text-transform:uppercase;font-size:8px;font-weight:800;color:var(--muted);min-width:840px}.episode-ledger{border:1px solid var(--line);border-radius:10px;overflow-x:auto}.episode-row{min-width:840px;border-top:1px solid var(--line)}.episode-row:first-child{border-top:0}.episode-row>summary{list-style:none;cursor:pointer;padding:10px;font-size:10px;font-variant-numeric:tabular-nums}.episode-row>summary small{display:block;color:var(--muted);font-size:8px;margin-top:2px}.episode-expanded{background:rgba(248,247,243,.8);padding:12px;border-top:1px solid var(--line)}.episode-detail-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.episode-detail-grid>div{border:1px solid var(--line);border-radius:9px;padding:9px}.episode-detail-grid small{display:block;color:var(--muted);font-size:8px;margin-bottom:4px}.episode-detail-grid b{font-size:9px}.row-forward-table{margin-top:10px;border:1px solid var(--line);border-radius:9px;overflow:hidden}.row-forward-head,.row-forward-row{display:grid;grid-template-columns:1.5fr repeat(4,1fr);gap:8px;padding:8px 10px;font-size:9px}.row-forward-head{background:#efede7;color:var(--muted);font-weight:800}.row-forward-row{border-top:1px solid var(--line)}.history-method{margin-top:15px;color:var(--muted);font-size:10px;line-height:1.5}@media(max-width:760px){.historical-evidence-card .history-summary-grid,.history-explainer,.episode-summary-strip{grid-template-columns:1fr 1fr}.episode-detail-grid{grid-template-columns:1fr}.historical-evidence-card .history-summary-grid strong{font-size:17px}}
    `}</style>
    <div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Did prior RE-ENTRY signals actually work?</h2></div><span className="pill">FULL TRANSPARENCY</span></div>
    <p className="section-intro">Two different historical views answer two different questions. The green ARCHIVED view is the preserved validation of entry timing. The amber RECONSTRUCTED view lets you inspect every continuous RE-ENTRY stretch and what happened while the signal stayed favorable.</p>

    <div className="history-explainer">
      <div><span className="source-badge archived">ARCHIVED · VALIDATED</span><b>Entry-timing validation</b><p><strong>189</strong> is the preserved retail count of independent RE-ENTRY opportunities. The detailed frozen validator contains <strong>{final.count}</strong> cooldown-selected events. These are validation samples, not continuous day-to-day RE-ENTRY stretches.</p></div>
      <div><span className="source-badge reconstructed">RECONSTRUCTED · INSPECTION</span><b>Continuous RE-ENTRY episodes</b><p>{ledger ? <><strong>{ledger.episode_count}</strong> reconstructed contiguous RE-ENTRY stretches are available for inspection.</> : <>The row ledger is currently unavailable.</>} This count is expected to differ from 189/193 because consecutive favorable days are grouped into one episode using a different definition.</p></div>
    </div>

    <div className="history-summary-grid">
      <div><small>Independent retail opportunities</small><strong>{retail.final_independent_reentry_episodes}</strong><span>archived validation definition</span></div>
      <div><small>Detailed validator events</small><strong>{final.count}</strong><span>cooldown-selected</span></div>
      <div><small>Continuous episode rows</small><strong>{ledger?.episode_count ?? "—"}</strong><span>reconstructed for inspection</span></div>
      <div><small>Canonical result</small><strong>VALIDATED</strong><span>core timing policy</span></div>
    </div>

    <h3>Archived performance after RE-ENTRY fired</h3>
    <p className="history-note">Not median-only: every horizon shows sample size, median, average and percentage of positive outcomes. Expand the statistical detail for quartiles, adverse/favorable excursion and false-start rates.</p>
    <HeadlineMetricRows evidence={evidence} />

    <details className="history-details">
      <summary><span><b>Full archived statistical distribution</b><small>All preserved 5D, 7D, 10D, 15D, 30D and 60D statistics</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body">
        <div className="provenance-banner archived"><CircleCheck size={16} /><div><b>ARCHIVED / VALIDATED</b><p>Copied from the original canonical validation artifact; not recomputed from today&apos;s historical vendor data.</p><small>Run {evidence.provenance.workflow_run_id} · engine {evidence.provenance.engine_commit.slice(0, 12)} · sample {dateLabel(evidence.provenance.sample_start)} through {dateLabel(evidence.provenance.sample_end)}</small></div></div>
        <FullMetricTable evidence={evidence} />
        <p className="history-note">* False start = forward return below -2% at that horizon. Typical worst = median maximum adverse excursion. Bad-tail worst = 10th-percentile maximum adverse excursion. Typical best = median maximum favorable excursion.</p>
      </div>
    </details>

    <EpisodeLedger ledger={ledger} />

    <details className="history-details">
      <summary><span><b>Current episode origin audit</b><small>Why the current episode begins Aug 28, 2026</small></span><ChevronDown size={18} /></summary>
      <div className="history-details-body">
        <div className="history-table compact-history-table"><div className="history-head"><span>Date</span><span>Archived state</span><span>Start-day close</span></div>{evidence.latest_policy_rows.map(row => <div className="history-row" key={row.date}><b>{dateLabel(row.date)}</b><span>{row.final_policy_signal}</span><span>{row.SPY ? `SPY $${row.SPY.toFixed(2)} · QQQ $${row.QQQ?.toFixed(2)}` : "—"}</span></div>)}</div>
        <div className="notice"><CircleCheck size={16} /> Aug 27 was NO RE-ENTRY SETUP. Aug 28 changed to RE-ENTER and the archived completed closes through Sep 4 stayed RE-ENTER; the production episode continued afterward.</div>
      </div>
    </details>

    <div className="history-method"><History size={12} /> Archived aggregate source: original canonical GitHub Actions artifact · run {evidence.provenance.workflow_run_id} · engine <code>{evidence.provenance.engine_commit.slice(0, 12)}</code>. Reconstructed rows are deliberately labeled separately and never replace those archived aggregate statistics.</div>
  </section>;
}
