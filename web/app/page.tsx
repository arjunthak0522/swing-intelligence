import { ChevronRight, CircleAlert, CircleCheck, Clock3, Radio } from "lucide-react";
import MarketMovementTables from "./MarketMovementTables";
import HistoricalEvidence from "./HistoricalEvidence";
import { getHistoricalEpisodeEvidence } from "../lib/historicalEvidence";
import {
  getIntradaySnapshot,
  getLatestEpisode,
  getLatestSnapshot,
  pct,
  type IntradaySnapshot,
  type ReentryEpisode,
  type ReentrySnapshot,
  type SubsectorProxy,
} from "../lib/reentry";

export const dynamic = "force-dynamic";

const sectorNames: Record<string, string> = {
  XLC: "Communication Services",
  XLY: "Consumer Discretionary",
  XLP: "Consumer Staples",
  XLE: "Energy",
  XLF: "Financials",
  XLV: "Health Care",
  XLI: "Industrials",
  XLB: "Materials",
  XLRE: "Real Estate",
  XLK: "Technology",
  XLU: "Utilities",
};

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

function subsectorState(x: SubsectorProxy) {
  if (x.repairing) return { label: "REPAIRING", dot: "repair", cls: "good-text" };
  if (x.drawdown_20d <= -0.05) return { label: "DEEP CORRECTION", dot: "damage", cls: "bad-text" };
  if (x.drawdown_20d <= -0.03) return { label: "DAMAGED", dot: "damage", cls: "muted" };
  if (x.drawdown_20d <= -0.02) return { label: "RESET", dot: "reset", cls: "muted" };
  return { label: "NEUTRAL", dot: "neutral", cls: "muted" };
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

function EpisodeSummary({ episode, official }: { episode: ReentryEpisode | null; official: ReentrySnapshot }) {
  if (!episode) return null;
  return (
    <section className="card section-card action-card">
      <div className="section-heading">
        <div><span className="kicker">CURRENT RE-ENTRY EPISODE</span><h2>{formatDate(episode.episode_start)}</h2></div>
        <StatusPill>{episode.active ? "ACTIVE" : "COMPLETED"}</StatusPill>
      </div>
      <p className="section-intro">
        This is one continuous re-entry opportunity, not a new entry every day. The signal first fired on {formatDate(episode.episode_start)} and remained favorable through {formatDate(episode.favorable_through)}.
        {official.signal === "WAIT" ? " Today’s WAIT applies only to a new/additional deployment." : ""}
      </p>
      <div className="vehicle-strip">
        <div className="vehicle-primary"><div><span>S&P 500</span><b>SPY</b></div><small>Close when episode first fired</small><strong>${episode.entry_closes.SPY.toFixed(2)}</strong><em>{formatDate(episode.episode_start)}</em></div>
        <div className="vehicle-primary"><div><span>Nasdaq 100</span><b>QQQ</b></div><small>Close when episode first fired</small><strong>${episode.entry_closes.QQQ.toFixed(2)}</strong><em>{formatDate(episode.episode_start)}</em></div>
      </div>
      <div className="notice"><CircleCheck size={16} /> Last favorable close: <b>{formatDate(episode.favorable_through)}</b>{episode.ended_on ? <> · Episode ended when the official signal changed on <b>{formatDate(episode.ended_on)}</b>.</> : null}</div>
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

function VehicleCard({ s }: { s: ReentrySnapshot }) {
  const h = s.historical_validation;
  return (
    <section className="card section-card action-card">
      <div className="section-heading"><div><span className="kicker">WHAT THIS MEANS</span><h2>Broad-market re-entry</h2></div><StatusPill>SPY + QQQ</StatusPill></div>
      <p className="section-intro">The model currently answers whether continuing to wait after a pullback is still helping. When the answer is RE-ENTER, SPY and QQQ are the validated broad-market destination set. Sector and subsector ETFs explain the setup; they are not separate buy calls and this tool does not decide position size.</p>
      <div className="vehicle-strip">
        <div className="vehicle-primary"><div><span>S&P 500</span><b>SPY</b></div><small>Broad market</small><strong>{pct(h.SPY_10D_median_after_signal, 2)}</strong><em>10D historical median after RE-ENTRY signals</em></div>
        <div className="vehicle-primary"><div><span>Nasdaq 100</span><b>QQQ</b></div><small>Growth heavy</small><strong>{pct(h.QQQ_10D_median_after_signal, 2)}</strong><em>10D historical median after RE-ENTRY signals</em></div>
      </div>
      <div className="notice"><CircleAlert size={16} /> The app will not claim SPY or QQQ is preferred until a separate vehicle-selection rule is historically validated.</div>
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

function MarketInternals({ s }: { s: ReentrySnapshot }) {
  const proxies = Object.entries(s.subsector_intelligence?.proxies || {}).sort((a, b) => Math.abs(b[1].drawdown_20d) - Math.abs(a[1].drawdown_20d));
  return (
    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">ALL SUBSECTORS</span><h2>What is moving underneath</h2></div><StatusPill>{proxies.length} tracked</StatusPill></div>
      <p className="section-intro">Every tracked subsector remains visible below. The first number is how far it sits below its recent 20-day high; REPAIRING means the group is recovering from a meaningful reset.</p>
      <div className="internal-list">
        {proxies.map(([symbol, x]) => {
          const state = subsectorState(x);
          const explanation = x.repairing
            ? `${x.label} is repairing after a meaningful reset. That is constructive early evidence, but it remains context rather than an independent re-entry trigger.`
            : state.label === "NEUTRAL"
              ? `${x.label} is not materially damaged on the 20-day measure and is not currently in repair mode.`
              : `${x.label} remains in a reset or correction. The engine tracks whether this weakness begins to stabilize and broaden into repair.`;
          return <details key={symbol} className="internal-row">
            <summary><div className="name-wrap"><span className="state-dot" data-state={state.dot} /><div><b>{x.label} <span>({symbol})</span></b><small>{sectorNames[x.parent_sector] || x.parent_sector}</small></div></div><div className="row-metrics"><span>{pct(x.drawdown_20d)}</span><strong className={state.cls}>{state.label}</strong><ChevronRight size={17} /></div></summary>
            <div className="detail-grid"><span>Below 20D high <b>{pct(x.drawdown_20d)}</b></span><span>Below 60D high <b>{pct(x.drawdown_60d)}</b></span><span>1D return <b>{pct(x.return_1d)}</b></span><span>5D return <b>{pct(x.return_5d)}</b></span><span>vs SPY 20D <b>{pct(x.relative_strength_20d_vs_spy)}</b></span><span>vs {x.parent_sector} 20D <b>{pct(x.relative_strength_20d_vs_parent)}</b></span></div>
            <p className="detail-copy">{explanation}</p>
          </details>;
        })}
      </div>
    </section>
  );
}

function SectorMap({ s }: { s: ReentrySnapshot }) {
  const sectors = Object.entries(s.signal_snapshot?.sectors || {}).sort((a, b) => a[1].drawdown_20d - b[1].drawdown_20d);
  return (
    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">ALL 11 SECTORS</span><h2>Damage and repair map</h2></div><StatusPill>{sectors.length}/11 loaded</StatusPill></div>
      <p className="section-intro">This is current market repair evidence, not the historical opportunity ranking above.</p>
      <div className="sector-table">
        <div className="sector-table-head"><span>Sector</span><span>Below 20D high</span><span>Subsectors 3%+ down</span><span>Repair now</span></div>
        {sectors.map(([symbol, x]) => { const group = s.subsector_intelligence?.by_sector?.[symbol]; const repairing = (group?.repair_share || 0) > 0; return <div className="sector-table-row" key={symbol}><div><b>{sectorNames[symbol] || symbol}</b><small>{symbol}</small></div><strong>{pct(x.drawdown_20d)}</strong><span>{pct(group?.damage_share_3pct)}</span><span className={repairing ? "good-text" : "muted"}>{repairing ? "Repairing now" : "No broad repair"}</span></div>; })}
      </div>
    </section>
  );
}

function Historical({ s }: { s: ReentrySnapshot }) {
  const h = s.historical_validation;
  const rows = [["5D", h.SPY_5D_median_after_signal, h.QQQ_5D_median_after_signal], ["10D", h.SPY_10D_median_after_signal, h.QQQ_10D_median_after_signal], ["30D", h.SPY_30D_median_after_signal, h.QQQ_30D_median_after_signal], ["60D", h.SPY_60D_median_after_signal, h.QQQ_60D_median_after_signal]] as const;
  const historyLabel = retailHistoryLabel(s.analog_decision);
  return <section className="card section-card"><div className="section-heading"><div><span className="kicker">SIMILAR PAST MARKETS</span><h2>What happened after prior RE-ENTRY signals</h2></div><StatusPill>{h.final_independent_reentry_episodes} independent signals</StatusPill></div><p className="section-intro">This is the validated strategy history. It is separate from today&apos;s nearest-market comparison and from the ETF opportunity estimates.</p><div className="history-table"><div className="history-head"><span>Horizon</span><span>SPY median</span><span>QQQ median</span></div>{rows.map(([label, spy, qqq]) => <div className="history-row" key={label}><b>{label}</b><span>{pct(spy, 2)}</span><span>{pct(qqq, 2)}</span></div>)}</div><div className="history-footer"><span>Similar past markets today</span><strong className={stateClass(historyLabel)}>{historyLabel}</strong></div></section>;
}

export default async function Home() {
  const [snapshot, intraday, episode, historicalEvidence] = await Promise.all([getLatestSnapshot(), getIntradaySnapshot(), getLatestEpisode(), getHistoricalEpisodeEvidence()]);
  if (!snapshot) {
    return <main className="shell"><section className="card data-blocked"><CircleAlert /> <div><b>OFFICIAL FEED UNAVAILABLE</b><p>No fallback decision is shown when the canonical close snapshot cannot be loaded.</p></div></section></main>;
  }
  const s = snapshot;
  const fresh = s.data_freshness?.same_day_complete === true;

  return <main className="shell">
    <header className="topbar"><div><span className="brand">RE-ENTRY</span><span className="tagline">Know when waiting stops helping.</span></div><div className="top-status">{fresh ? <><span className="live-dot" /> Official close feed</> : "DATA INCOMPLETE"}</div></header>
    {!fresh ? <section className="card data-blocked"><CircleAlert /> <div><b>DATA INCOMPLETE</b><p>The current decision is suppressed until every required input resolves to the same completed market session.</p></div></section> : <>
      <ProductPurpose />
      <Hero s={s} />
      <VehicleCard s={s} />
      <EpisodeSummary episode={episode} official={s} />
      <WhyNow s={s} />
      <div className="context-divider"><span className="kicker">WHAT IS HAPPENING TODAY · CONTEXT ONLY</span><p>Live movement helps explain what is happening underneath the official decision. It never replaces the completed-close RE-ENTRY signal.</p></div>
      <IntradayMonitor live={intraday} official={s} />
      <MarketMovementTables snapshot={s} live={intraday} />
      <HistoricalEvidence evidence={historicalEvidence} />
      <OutperformanceCard />
    </>}
    <footer>Official RE-ENTRY decisions use completed-close data. Intraday data is provisional market context only and never overwrites the validated close signal. Historical ETF opportunity estimates remain suppressed until their input history is reproducible.</footer>
  </main>;
}