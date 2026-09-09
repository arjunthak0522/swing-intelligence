import { CircleAlert, CircleCheck, Clock3, Radio } from "lucide-react";
import MarketMovementTables from "./MarketMovementTables";
import HistoricalEvidence from "./HistoricalEvidence";
import { getHistoricalEpisodeEvidence, getHistoricalEpisodeLedger } from "../lib/historicalEvidence";
import {
  getIntradaySnapshot,
  getLatestEpisode,
  getLatestSnapshot,
  pct,
  type IntradaySnapshot,
  type ReentryEpisode,
  type ReentrySnapshot,
} from "../lib/reentry";

export const dynamic = "force-dynamic";

function stateClass(value: string) {
  const v = value.toUpperCase();
  if (v.includes("REPAIR") || v.includes("YES") || v.includes("LIVE") || v.includes("FAVORABLE")) return "good";
  if (v.includes("WAIT") || v.includes("STABIL") || v.includes("DEVELOP") || v.includes("PARTIAL") || v.includes("RESET")) return "warn";
  if (v.includes("NO") || v.includes("WORSEN") || v.includes("HEAVY") || v.includes("DEGRADED") || v.includes("DEEP")) return "bad";
  return "neutral";
}

function retailHistoryLabel(value: string) {
  const v = value.toUpperCase();
  if (v === "CAUTIOUS YES") return "FAVORABLE";
  if (v.includes("YES")) return "FAVORABLE";
  if (v.includes("NO")) return "UNFAVORABLE";
  return value;
}

function StatusPill({ children }: { children: React.ReactNode }) {
  return <span className="pill">{children}</span>;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function ProductPurpose() {
  return (
    <section className="card purpose-card">
      <span className="kicker">WHAT RE-ENTRY DOES</span>
      <h1>After a market pullback, should you keep waiting—or put cash back into SPY/QQQ?</h1>
      <p>This is not a stock picker or trading dashboard. It tells you when waiting after a market pullback may no longer be helping.</p>
    </section>
  );
}

function Hero({ s }: { s: ReentrySnapshot }) {
  const closer = s.signal === "WAIT" && ["DEVELOPING", "MEANINGFUL", "BROAD"].includes(s.internal_reset);
  const displaySignal = s.signal === "WAIT" ? "WAIT FOR NEW ENTRY" : s.signal;
  return (
    <section className="hero card">
      <div className="eyebrow-row">
        <span className="eyebrow">OFFICIAL RE-ENTRY DECISION</span>
        <span className="freshness"><Clock3 size={14} /> {formatDate(s.as_of)} completed close</span>
      </div>
      <div className="hero-grid">
        <div>
          <div className={`signal ${stateClass(s.signal)}`}>{displaySignal}</div>
          <div className="signal-subline">{closer ? "A prior entry already occurred. Wait for a new setup before deploying additional cash." : s.signal_interpretation}</div>
        </div>
        <div className="decision-summary">
          <span className="summary-label">BOTTOM LINE</span>
          <p>{s.signal_interpretation}</p>
          <div className="decision-tags">
            <span><small>Pullback</small><b>{s.market_damage}</b></span>
            <span><small>Selling</small><b>{s.selling_pressure}</b></span>
            <span><small>Similar past markets</small><b>{retailHistoryLabel(s.analog_decision)}</b></span>
          </div>
        </div>
      </div>
    </section>
  );
}

function EpisodeSummary({ episode, official, live }: { episode: ReentryEpisode | null; official: ReentrySnapshot; live: IntradaySnapshot | null }) {
  if (!episode) return null;
  const spyPrice = live?.quotes?.SPY?.price;
  const qqqPrice = live?.quotes?.QQQ?.price;
  const spyPerformance = typeof spyPrice === "number" && episode.entry_closes.SPY > 0 ? (spyPrice / episode.entry_closes.SPY) - 1 : null;
  const qqqPerformance = typeof qqqPrice === "number" && episode.entry_closes.QQQ > 0 ? (qqqPrice / episode.entry_closes.QQQ) - 1 : null;
  const regularSession = live?.quotes?.SPY?.market_state === "REGULAR";
  const performanceLabel = regularSession ? "LIVE SINCE RE-ENTRY" : "SINCE RE-ENTRY";
  const latestTimestamp = live?.quotes?.SPY?.timestamp ? new Date(live.quotes.SPY.timestamp) : null;
  const timestampLabel = latestTimestamp
    ? latestTimestamp.toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })
    : null;

  return (
    <section className="card section-card action-card">
      <div className="section-heading">
        <div><span className="kicker">CURRENT RE-ENTRY EPISODE</span><h2>Started {formatDate(episode.episode_start)}</h2></div>
        <StatusPill>{episode.active ? "ACTIVE" : "COMPLETED"}</StatusPill>
      </div>
      <p className="section-intro">
        This is one continuous RE-ENTRY period. Performance below is measured from the first RE-ENTRY close on {formatDate(episode.episode_start)} to the latest verified market price.
        {official.signal === "WAIT" ? " The current WAIT applies only to a new or additional deployment." : ""}
      </p>
      <div className="vehicle-strip episode-performance-strip">
        <div className="vehicle-primary"><div><span>S&P 500</span><b>SPY</b></div><small>{performanceLabel}</small><strong className={typeof spyPerformance === "number" ? (spyPerformance >= 0 ? "good-text" : "bad-text") : "muted"}>{pct(spyPerformance, 2)}</strong><em>From {formatDate(episode.episode_start)}</em></div>
        <div className="vehicle-primary"><div><span>Nasdaq 100</span><b>QQQ</b></div><small>{performanceLabel}</small><strong className={typeof qqqPerformance === "number" ? (qqqPerformance >= 0 ? "good-text" : "bad-text") : "muted"}>{pct(qqqPerformance, 2)}</strong><em>From {formatDate(episode.episode_start)}</em></div>
      </div>
      <div className="notice"><CircleCheck size={16} /> {timestampLabel ? <>Performance uses the latest verified market price from <b>{timestampLabel}</b>.</> : <>Live performance is temporarily unavailable; the official completed-close signal remains authoritative.</>}</div>
    </section>
  );
}

function IntradayMonitor({ live, official }: { live: IntradaySnapshot | null; official: ReentrySnapshot }) {
  const spy = live?.quotes?.SPY;
  const qqq = live?.quotes?.QQQ;
  const vix = live?.quotes?.["^VIX"];
  const regularSession = spy?.market_state === "REGULAR";
  const lastBar = spy?.timestamp ? new Date(spy.timestamp) : null;
  const barLabel = lastBar
    ? lastBar.toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })
    : "latest available bar";
  const updateLabel = lastBar
    ? lastBar.toLocaleString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit", timeZoneName: "short" })
    : "Unavailable";
  const periodLabel = regularSession ? "today" : "last session";
  const statusLabel = live ? (regularSession ? live.status : "MARKET CLOSED") : "UNAVAILABLE";

  return (
    <section className="card section-card live-card">
      <div className="section-heading">
        <div><span className="kicker">RIGHT NOW · PROVISIONAL</span><h2>{regularSession ? "Live market context" : "Latest intraday session"}</h2></div>
        <div className="eyebrow-row"><span className="freshness"><Radio size={14} /> Updated {updateLabel}</span><StatusPill>{statusLabel}</StatusPill></div>
      </div>
      <p className="section-intro">
        {regularSession
          ? "This layer updates from 5-minute market bars so you can see what is happening now while the official completed-close decision remains in force."
          : "The market is closed, so this panel shows the latest completed intraday session rather than implying prices are moving now."}
        {` It does not replace the official ${formatDate(official.as_of)} close signal.`}
      </p>
      {live ? <>
        <div className="live-grid">
          <div className="live-stat"><small>SPY {periodLabel}</small><strong>{pct(spy?.change_pct, 2)}</strong><span>{spy?.price?.toFixed(2) ?? "-"}</span></div>
          <div className="live-stat"><small>QQQ {periodLabel}</small><strong>{pct(qqq?.change_pct, 2)}</strong><span>{qqq?.price?.toFixed(2) ?? "-"}</span></div>
          <div className="live-stat"><small>VIX {periodLabel}</small><strong>{pct(vix?.change_pct, 2)}</strong><span>{vix?.price?.toFixed(2) ?? "-"}</span></div>
          <div className="live-stat"><small>Sectors positive</small><strong>{pct(live.summary.sectors_positive_share, 0)}</strong><span>11 tracked</span></div>
          <div className="live-stat"><small>Subsectors positive</small><strong>{pct(live.summary.subsectors_positive_share, 0)}</strong><span>30+ tracked</span></div>
          <div className="live-stat"><small>Factors positive</small><strong>{pct(live.summary.factors_positive_share, 0)}</strong><span>8 tracked</span></div>
        </div>
        <div className="live-foot"><Radio size={14} /> Latest verified bar {barLabel} · {live.summary.tracked_quotes}/{live.summary.expected_quotes} quotes available · official decision remains <b>{official.signal}</b> until the close engine recalculates.</div>
      </> : <div className="notice"><CircleAlert size={16} /> Intraday feed is temporarily unavailable. The official completed-close signal remains authoritative.</div>}
    </section>
  );
}

function OutperformanceCard() {
  return (
    <section className="card section-card action-card">
      <div className="section-heading"><div><span className="kicker">HISTORICAL OPPORTUNITY</span><h2>ETF relative-opportunity layer</h2></div><StatusPill>UNDER VALIDATION</StatusPill></div>
      <p className="section-intro">This section remains visible, but its ETF ranking numbers are temporarily suppressed. A reproducibility audit found that mutable adjusted historical ETF prices could change a previously published nearest-neighbor estimate after the fact.</p>
      <div className="notice"><CircleAlert size={16} /> No REZ, ITA, XTN, or other relative-opportunity percentage will be displayed until the historical input series is point-in-time reproducible and the layer passes a fresh backtest.</div>
      <div className="notice"><CircleCheck size={16} /> This does not affect the official RE-ENTRY decision. The Sep 4 core decision was independently rebuilt from the frozen engine and reproduced as RE-ENTER with the same headline inputs and decision states.</div>
    </section>
  );
}

function WhyNow({ s }: { s: ReentrySnapshot }) {
  const insights = s.market_insights;
  const support = insights?.supporting_reentry || [];
  const hold = insights?.holding_back || [];
  const repairingGroups = (insights?.key_groups || []).filter(x => x.state === "REPAIRING");
  return (
    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">WHY</span><h2>Why {s.signal === "RE-ENTER" ? "RE-ENTER" : "this decision"}?</h2></div></div>
      <p className="section-intro">{insights?.headline || s.signal_interpretation}</p>
      <div className="two-col">
        <div className="reason-panel supportive">
          <h3><CircleCheck size={17} /> What supports re-entry</h3>
          {support.slice(0, 4).map((text, i) => <div className="reason" key={`support-${i}`}><p>{text}</p></div>)}
          <div className="reason"><p className="summary-label">REPAIR HAPPENING NOW</p><small>These groups are recovering from recent weakness. They are supporting evidence, not separate buy signals.</small></div>
          {repairingGroups.map(x => <div className="reason" key={x.symbol}><div><b>{x.label} ({x.symbol})</b><StatusPill>{x.state}</StatusPill></div><p>{x.interpretation}</p><small>{x.why_it_matters}</small></div>)}
        </div>
        <div className="reason-panel holding">
          <h3><CircleAlert size={17} /> Reasons to keep waiting</h3>
          {hold.slice(0, 4).map((text, i) => <div className="reason" key={`hold-${i}`}><p>{text}</p></div>)}
          {hold.length === 0 && <div className="reason"><p>No additional validated reasons to keep waiting are being surfaced.</p></div>}
        </div>
      </div>
    </section>
  );
}

function HistoricalTableLayoutFix() {
  return <style>{`
    .historical-evidence-card .episode-ledger-details .definition-box{display:none}
    .historical-evidence-card .episode-ledger-details .history-details-body{padding:0}
    .historical-evidence-card .episode-ledger{width:100%;overflow:hidden;border-radius:0;border-left:0;border-right:0}
    .historical-evidence-card .episode-ledger-head,
    .historical-evidence-card .episode-row>summary{display:grid!important;grid-template-columns:minmax(280px,2.2fr) minmax(110px,.8fr) minmax(110px,.8fr) minmax(110px,.8fr) 28px!important;gap:18px!important;align-items:center!important;width:100%!important;min-width:0!important}
    .historical-evidence-card .episode-ledger-head{padding:12px 22px!important;min-width:0!important}
    .historical-evidence-card .episode-row{width:100%!important;min-width:0!important}
    .historical-evidence-card .episode-row>summary{padding:16px 22px!important;min-height:62px;font-size:11px!important}
    .historical-evidence-card .episode-row>summary>span:first-child{display:flex;align-items:baseline;gap:7px;min-width:0;white-space:nowrap}
    .historical-evidence-card .episode-row>summary>span:first-child small{display:inline!important;margin:0!important;font-size:9px!important;white-space:nowrap}
    .historical-evidence-card .episode-row>summary>span:nth-child(2),
    .historical-evidence-card .episode-row>summary>strong{text-align:left;font-variant-numeric:tabular-nums}
    .historical-evidence-card .period-methodology{margin:12px 18px 16px}
    .episode-performance-strip .vehicle-primary strong{font-size:34px}
    @media(max-width:760px){
      .historical-evidence-card .episode-ledger{overflow-x:auto}
      .historical-evidence-card .episode-ledger-head,
      .historical-evidence-card .episode-row>summary{grid-template-columns:minmax(210px,1.7fr) 92px 92px 92px 24px!important;min-width:560px!important;gap:10px!important}
      .historical-evidence-card .episode-ledger-head,
      .historical-evidence-card .episode-row>summary{padding-left:14px!important;padding-right:14px!important}
    }
  `}</style>;
}

export default async function Home() {
  const [snapshot, intraday, episode, historicalEvidence, historicalLedger] = await Promise.all([getLatestSnapshot(), getIntradaySnapshot(), getLatestEpisode(), getHistoricalEpisodeEvidence(), getHistoricalEpisodeLedger()]);
  if (!snapshot) {
    return <main className="shell"><section className="card data-blocked"><CircleAlert /> <div><b>OFFICIAL FEED UNAVAILABLE</b><p>No fallback decision is shown when the canonical close snapshot cannot be loaded.</p></div></section></main>;
  }
  const s = snapshot;
  const fresh = s.data_freshness?.same_day_complete === true;

  return <main className="shell">
    <HistoricalTableLayoutFix />
    <header className="topbar"><div><span className="brand">RE-ENTRY</span><span className="tagline">Know when waiting stops helping.</span></div><div className="top-status">{fresh ? <><span className="live-dot" /> Official close feed</> : "DATA INCOMPLETE"}</div></header>
    {!fresh ? <section className="card data-blocked"><CircleAlert /> <div><b>DATA INCOMPLETE</b><p>The current decision is suppressed until every required input resolves to the same completed market session.</p></div></section> : <>
      <ProductPurpose />
      <Hero s={s} />
      <EpisodeSummary episode={episode} official={s} live={intraday} />
      <WhyNow s={s} />
      <div className="context-divider"><span className="kicker">WHAT IS HAPPENING TODAY · CONTEXT ONLY</span><p>Live movement helps explain what is happening underneath the official decision. It never replaces the completed-close RE-ENTRY signal.</p></div>
      <IntradayMonitor live={intraday} official={s} />
      <MarketMovementTables snapshot={s} live={intraday} />
      <HistoricalEvidence evidence={historicalEvidence} ledger={historicalLedger} />
      <OutperformanceCard />
    </>}
    <footer>Official RE-ENTRY decisions use completed-close data. Intraday data is provisional market context only and never overwrites the validated close signal. Historical ETF opportunity estimates remain suppressed until their input history is reproducible.</footer>
  </main>;
}
