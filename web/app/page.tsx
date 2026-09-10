import { CircleAlert, CircleCheck, Clock3, Radio } from "lucide-react";
import MarketMovementTables from "./MarketMovementTables";
import {
  getIntradaySnapshot,
  getLatestEpisode,
  getLatestSnapshot,
  getWashoutSnapshot,
  pct,
  type IntradaySnapshot,
  type ReentryEpisode,
  type ReentrySnapshot,
  type WashoutSnapshot,
} from "../lib/reentry";

export const dynamic = "force-dynamic";

function stateClass(value: string) {
  const v = value.toUpperCase();
  if (v.includes("GO_EARLY") || v.includes("GO EARLY") || v.includes("REPAIR") || v.includes("YES") || v.includes("LIVE") || v.includes("FAVORABLE")) return "good";
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

function episodeReturn(current?: number | null, entry?: number | null) {
  if (typeof current !== "number" || !Number.isFinite(current) || typeof entry !== "number" || !Number.isFinite(entry) || entry === 0) return "-";
  return pct(current / entry - 1, 2);
}

function signedNumber(value?: number | null, digits = 1) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function ratio(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2)}x` : "-";
}

function ProductPurpose() {
  return (
    <section className="card purpose-card">
      <span className="kicker">WHAT RE-ENTRY DOES</span>
      <h1>After a market pullback, should you keep waiting or put cash back into SPY/QQQ?</h1>
      <p>This is not a stock picker or trading dashboard. It tells you when waiting after a market pullback may no longer be helping.</p>
    </section>
  );
}

function UnifiedHero({ washout }: { washout: WashoutSnapshot }) {
  const u = washout.unified_engine;
  const phase = u?.market_phase || "UNAVAILABLE";
  const decision = u?.decision || u?.state || "UNAVAILABLE";
  const label = decision === "GO_EARLY" ? "GO EARLY" : decision;
  const phaseLabel = phase === "MARKET_CLOSED_FINAL" ? "MARKET CLOSED · FINAL" : phase === "CLOSE_SETTLING" ? "CLOSE SETTLING" : phase === "LIVE_PROVISIONAL" ? "LIVE · PROVISIONAL" : "UNAVAILABLE";
  const fast = u?.fast_family_count ?? washout.turn_family_count ?? 0;
  const context = u?.context_support_count ?? 0;
  const explanation = decision === "GO_EARLY"
    ? `Oversold conditions are present and reversal evidence has reached the early re-entry threshold: ${fast} fast turn${fast === 1 ? "" : "s"} plus ${context} context turn${context === 1 ? "" : "s"}.`
    : decision === "WATCH"
      ? `The market is washed out and some reversal evidence is appearing, but the unified threshold is not fully triggered yet.`
      : `The market may be weak or oversold, but there is not enough reversal evidence yet.`;
  return (
    <section className="hero card">
      <div className="eyebrow-row"><span className="eyebrow">RE-ENTRY DECISION</span><span className="freshness"><Clock3 size={14} /> {phaseLabel}</span></div>
      <div className="hero-grid">
        <div><div className={`signal ${stateClass(decision)}`}>{label}</div><div className="signal-subline">{explanation}</div></div>
        <div className="decision-summary"><span className="summary-label">ONE ENGINE</span><p>Same indicators and same decision rule during the session and after the close. Only the data status changes from provisional to final.</p><div className="decision-tags"><span><small>Oversold setup</small><b>{u?.oversold_gate ? "YES" : "NO"}</b></span><span><small>Fast turns</small><b>{fast}/4</b></span><span><small>Context turns</small><b>{context}/4</b></span></div></div>
      </div>
    </section>
  );
}

function EpisodeSummary({ episode, live }: { episode: ReentryEpisode | null; live: IntradaySnapshot | null }) {
  if (!episode) return null;
  const spyNow = live?.quotes?.SPY?.price;
  const qqqNow = live?.quotes?.QQQ?.price;
  return (
    <section className="card section-card action-card">
      <div className="section-heading">
        <div><span className="kicker">CURRENT RE-ENTRY EPISODE</span><h2>Since {formatDate(episode.episode_start)}</h2></div>
        <StatusPill>{episode.active ? "ACTIVE" : "COMPLETED"}</StatusPill>
      </div>
      <p className="section-intro">
        Performance since the first RE-ENTRY signal in this continuous episode.
      </p>
      <div className="vehicle-strip">
        <div className="vehicle-primary"><div><span>S&P 500</span><b>SPY</b></div><small>Return since RE-ENTRY began</small><strong>{episodeReturn(spyNow, episode.entry_closes.SPY)}</strong><em>From {formatDate(episode.episode_start)}</em></div>
        <div className="vehicle-primary"><div><span>Nasdaq 100</span><b>QQQ</b></div><small>Return since RE-ENTRY began</small><strong>{episodeReturn(qqqNow, episode.entry_closes.QQQ)}</strong><em>From {formatDate(episode.episode_start)}</em></div>
      </div>
      <div className="notice"><CircleCheck size={16} /> Episode remains tied to the original RE-ENTRY start date until the state changes.</div>
    </section>
  );
}

function IntradayMonitor({ live, washout }: { live: IntradaySnapshot | null; washout: WashoutSnapshot | null }) {
  const spy = live?.quotes?.SPY;
  const qqq = live?.quotes?.QQQ;
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
  const w = washout?.values;

  return (
    <section className="card section-card live-card">
      <div className="section-heading">
        <div><span className="kicker">{regularSession ? "RIGHT NOW · LIVE / PROVISIONAL" : "MARKET CLOSED · FINAL SESSION"}</span><h2>{regularSession ? "Live market context" : "Final market context"}</h2></div>
        <div className="eyebrow-row"><span className="freshness"><Radio size={14} /> Updated {updateLabel}</span><StatusPill>{statusLabel}</StatusPill></div>
      </div>
      <p className="section-intro">
        {regularSession
          ? "Current price action plus the market internals most directly tied to selling exhaustion."
          : "The market is closed, so this panel shows the latest completed intraday session rather than implying prices are moving now."}

      </p>
      {live ? <>
        <div className="live-grid">
          <div className="live-stat"><small>SPY {periodLabel}</small><strong>{pct(spy?.change_pct, 2)}</strong><span>{spy?.price?.toFixed(2) ?? "-"}</span></div>
          <div className="live-stat"><small>QQQ {periodLabel}</small><strong>{pct(qqq?.change_pct, 2)}</strong><span>{qqq?.price?.toFixed(2) ?? "-"}</span></div>
          <div className="live-stat"><small>NYSE A/D volume</small><strong>{signedNumber(w?.NYUD)}</strong><span>Net breadth-volume pressure</span></div>
          <div className="live-stat"><small>Nasdaq A/D volume</small><strong>{signedNumber(w?.NAUD)}</strong><span>Net breadth-volume pressure</span></div>
          <div className="live-stat"><small>NYSE down/up volume</small><strong>{ratio(w?.nyse_down_up_ratio)}</strong><span>Lower means selling is easing</span></div>
          <div className="live-stat"><small>Nasdaq down/up volume</small><strong>{ratio(w?.nasdaq_down_up_ratio)}</strong><span>Lower means selling is easing</span></div>
        </div>
        <div className="live-foot"><Radio size={14} /> Latest verified price bar {barLabel} · {live.summary.tracked_quotes}/{live.summary.expected_quotes} quotes available.</div>
      </> : <div className="notice"><CircleAlert size={16} /> Market-data feed is temporarily unavailable. No alternate legacy decision is substituted.</div>}
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

export default async function Home() {
  const [snapshot, intraday, episode, washout] = await Promise.all([getLatestSnapshot(), getIntradaySnapshot(), getLatestEpisode(), getWashoutSnapshot()]);
  const unified = washout?.unified_engine;

  return <main className="shell">
    <header className="topbar"><div><span className="brand">RE-ENTRY</span><span className="tagline">Know when waiting stops helping.</span></div><div className="top-status">{unified?.market_phase === "MARKET_CLOSED_FINAL" ? "Market closed · final" : unified?.market_phase === "LIVE_PROVISIONAL" ? <><span className="live-dot" /> Live engine</> : "Updating"}</div></header>
    {!washout || !unified ? <section className="card data-blocked"><CircleAlert /> <div><b>RE-ENTRY FEED UNAVAILABLE</b><p>No fallback decision is shown when the unified engine cannot be loaded.</p></div></section> : <>
      <ProductPurpose />
      <UnifiedHero washout={washout} />
      {snapshot && episode ? <EpisodeSummary episode={episode} live={intraday} /> : null}
      <IntradayMonitor live={intraday} washout={washout} />
      {snapshot ? <MarketMovementTables snapshot={snapshot} live={intraday} washout={washout} /> : null}
    </>}
    <footer>One RE-ENTRY engine. Live/provisional during market hours, final after the close. Historical analog research is supporting evidence only and cannot override the primary decision.</footer>
  </main>;
}
