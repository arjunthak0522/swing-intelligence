import { CircleAlert, CircleCheck } from "lucide-react";
import type { HistoricalEpisodeEvidence } from "../lib/historicalEvidence";

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

function nextStateLabel(value?: string | null) {
  if (!value) return "Sample end";
  if (value === "NO RE-ENTRY SETUP") return "No setup";
  return value;
}

export default function HistoricalEvidence({ evidence }: { evidence: HistoricalEpisodeEvidence | null }) {
  if (!evidence) {
    return <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Prior RE-ENTRY episodes</h2></div></div>
      <div className="notice"><CircleAlert size={16} /> Episode-level evidence is temporarily unavailable. No reconstructed historical rows are shown without a frozen evidence artifact.</div>
    </section>;
  }

  const summary = evidence.continuous_episode_summary;
  const spy = summary.SPY.return_during_episode;
  const qqq = summary.QQQ.return_during_episode;
  const duration = summary.episode_length_sessions;
  const validation = evidence.archived_entry_timing_validation;
  const horizons = ["5D", "10D", "30D", "60D"] as const;

  return <section className="card section-card historical-evidence-card">
    <div className="section-heading">
      <div><span className="kicker">HISTORICAL EVIDENCE</span><h2>What happened during prior RE-ENTRY episodes?</h2></div>
      <span className="pill">{evidence.continuous_episode_count} continuous episodes</span>
    </div>
    <p className="section-intro">An episode begins when the completed-close decision first changes to RE-ENTER and ends on the last consecutive close that still says RE-ENTER. Returns below are measured from the first RE-ENTER close through that last favorable close.</p>
    <div className="notice"><CircleCheck size={16} /> The following WAIT or NO SETUP date is shown separately and is not included in the return. This measures history; it does not create an exit or sell rule.</div>

    <div className="history-summary-grid">
      <div><small>Completed episodes measured</small><strong>{summary.completed_episode_count}</strong><span>{summary.active_at_sample_end_count ? `${summary.active_at_sample_end_count} active at sample end` : "all completed"}</span></div>
      <div><small>SPY positive during episode</small><strong>{pct(spy.positive_rate, 0)}</strong><span>median return {pct(spy.median, 2)}</span></div>
      <div><small>QQQ positive during episode</small><strong>{pct(qqq.positive_rate, 0)}</strong><span>median return {pct(qqq.median, 2)}</span></div>
      <div><small>Median RE-ENTER duration</small><strong>{duration.median?.toFixed(0) ?? "—"}</strong><span>trading sessions</span></div>
    </div>

    <div className="history-subsection">
      <div className="history-subheading"><div><span className="summary-label">ORIGINAL ENTRY-TIMING VALIDATION</span><h3>What happened after RE-ENTRY fired?</h3></div><span>{validation.validation_event_count} archived validation events</span></div>
      <p className="history-note">This is a separate test from the continuous episodes above. These are the original archived canonical validation results using cooldown-selected RE-ENTRY events, preserved from the validation run rather than recalculated from mutable historical inputs.</p>
      <div className="history-table">
        <div className="history-head"><span>Horizon</span><span>SPY median</span><span>QQQ median</span></div>
        {horizons.map((h) => <div className="history-row" key={h}><b>{h}</b><span>{pct(validation.fixed_horizon.SPY[h].median, 2)} <small>n={validation.fixed_horizon.SPY[h].n}</small></span><span>{pct(validation.fixed_horizon.QQQ[h].median, 2)} <small>n={validation.fixed_horizon.QQQ[h].n}</small></span></div>)}
      </div>
    </div>

    <div className="history-subsection">
      <div className="history-subheading"><div><span className="summary-label">ALL CONTINUOUS EPISODES</span><h3>Every reconstructed RE-ENTRY episode</h3></div><span>{evidence.continuous_episodes.length} rows · newest first</span></div>
      <p className="history-note">“Last favorable” is the final consecutive completed close still showing RE-ENTER. “Max adverse” is the worst close-to-close move from the episode’s starting close while RE-ENTRY remained favorable.</p>
      <div className="episode-table-wrap">
        <div className="episode-table">
          <div className="episode-head"><span>RE-ENTRY began</span><span>Last favorable</span><span>Sessions</span><span>SPY return</span><span>QQQ return</span><span>SPY max adverse</span><span>QQQ max adverse</span><span>Next state</span></div>
          {evidence.continuous_episodes.map((row) => <div className="episode-row" key={row.start}>
            <b>{dateLabel(row.start)}</b>
            <span>{dateLabel(row.last_favorable)}</span>
            <span>{row.reenter_sessions}</span>
            <strong className={row.SPY_return_during_episode >= 0 ? "good-text" : "bad-text"}>{pct(row.SPY_return_during_episode, 2)}</strong>
            <strong className={row.QQQ_return_during_episode >= 0 ? "good-text" : "bad-text"}>{pct(row.QQQ_return_during_episode, 2)}</strong>
            <span>{pct(row.SPY_max_adverse_during_episode, 2)}</span>
            <span>{pct(row.QQQ_max_adverse_during_episode, 2)}</span>
            <span>{nextStateLabel(row.next_state)}{row.next_state_date ? ` · ${dateLabel(row.next_state_date)}` : ""}</span>
          </div>)}
        </div>
      </div>
    </div>

    <div className="history-method">Continuous episodes: frozen reconstruction through {dateLabel(evidence.canonical_sample_end)} using engine <code>{evidence.canonical_engine_commit.slice(0, 12)}</code>. Original fixed-horizon validation: {validation.validation_event_count} archived events. Historical-input drift is tracked separately and does not silently rewrite the archived validation statistics.</div>
  </section>;
}
