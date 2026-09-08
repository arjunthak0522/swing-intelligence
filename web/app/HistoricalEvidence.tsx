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
      <div className="section-heading"><div><span className="kicker">HISTORICAL EVIDENCE</span><h2>Prior RE-ENTRY signals</h2></div></div>
      <div className="notice"><CircleAlert size={16} /> Episode-level evidence is temporarily unavailable. The validated fixed-horizon evidence remains part of the official engine snapshot.</div>
    </section>;
  }

  const summary = evidence.summary_completed_episodes;
  const spy = summary.SPY.return_during_episode;
  const qqq = summary.QQQ.return_during_episode;
  const duration = summary.episode_length_sessions;
  const horizons = ["5D", "10D", "30D", "60D"] as const;

  return <section className="card section-card historical-evidence-card">
    <div className="section-heading">
      <div><span className="kicker">HISTORICAL EVIDENCE</span><h2>How prior RE-ENTRY signals actually performed</h2></div>
      <span className="pill">{evidence.validated_independent_reentry_signals} validated signals</span>
    </div>
    <p className="section-intro">For every validated independent RE-ENTRY signal, the primary result below measures the signal close through the last consecutive close that still said RE-ENTER. The following WAIT or NO SETUP date is shown separately and is not included in the return.</p>
    <div className="notice"><CircleCheck size={16} /> This is historical measurement only. It does not create an exit or sell rule.</div>

    <div className="history-summary-grid">
      <div><small>Completed signals measured</small><strong>{summary.completed_episode_count}</strong><span>{summary.active_at_sample_end_count ? `${summary.active_at_sample_end_count} open at sample end` : "all completed"}</span></div>
      <div><small>SPY positive while favorable</small><strong>{pct(spy.positive_rate, 0)}</strong><span>median {pct(spy.median, 2)}</span></div>
      <div><small>QQQ positive while favorable</small><strong>{pct(qqq.positive_rate, 0)}</strong><span>median {pct(qqq.median, 2)}</span></div>
      <div><small>Median favorable duration</small><strong>{duration.median?.toFixed(0) ?? "—"}</strong><span>trading sessions</span></div>
    </div>

    <div className="history-subsection">
      <div className="history-subheading"><div><span className="summary-label">FIXED-HORIZON VALIDATION</span><h3>What happened after RE-ENTRY first fired</h3></div><span>{evidence.validated_independent_reentry_signals} independent signals</span></div>
      <p className="history-note">This is the original validated forward-return view. It answers whether RE-ENTRY historically identified useful entry timing even after the favorable episode itself ended.</p>
      <div className="history-table">
        <div className="history-head"><span>Horizon</span><span>SPY median</span><span>QQQ median</span></div>
        {horizons.map((h) => <div className="history-row" key={h}><b>{h}</b><span>{pct(evidence.fixed_horizon_validation.SPY[`${h}_median`], 2)}</span><span>{pct(evidence.fixed_horizon_validation.QQQ[`${h}_median`], 2)}</span></div>)}
      </div>
    </div>

    <div className="history-subsection">
      <div className="history-subheading"><div><span className="summary-label">ALL VALIDATED SIGNALS</span><h3>Every historical RE-ENTRY signal</h3></div><span>{evidence.episodes.length} rows</span></div>
      <p className="history-note">Newest first. “Last favorable” is the final consecutive close still showing RE-ENTER after that validated signal date.</p>
      <div className="episode-table-wrap">
        <div className="episode-table">
          <div className="episode-head"><span>RE-ENTRY fired</span><span>Last favorable</span><span>Sessions</span><span>SPY</span><span>QQQ</span><span>SPY max adverse</span><span>QQQ max adverse</span><span>Next state</span></div>
          {evidence.episodes.map((row) => <div className="episode-row" key={row.start}>
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

    <div className="history-method">Frozen canonical engine: <code>{evidence.canonical_engine_commit.slice(0, 12)}</code> · validated signal selection uses the canonical 10-session cooldown.</div>
  </section>;
}
