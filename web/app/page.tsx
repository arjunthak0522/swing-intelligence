import { CircleAlert, Clock3, Radio } from "lucide-react";
import MarketMovementTables from "./MarketMovementTables";
import ReentryDecisionDetails from "./ReentryDecisionDetails";
import AggregateHistoricalEvidence from "./AggregateHistoricalEvidence";
import { getHistoricalEpisodeEvidence } from "../lib/historicalEvidence";
import {
  getIntradaySnapshot,
  getLatestSnapshot,
  getWashoutSnapshot,
  pct,
  type IntradaySnapshot,
  type WashoutSnapshot,
} from "../lib/reentry";

export const dynamic = "force-dynamic";

function stateClass(value: string) {
  const v = value.toUpperCase();
  if (v.includes("GO_EARLY") || v.includes("GO EARLY")) return "good";
  if (v.includes("WATCH")) return "warn";
  if (v.includes("WAIT")) return "neutral";
  return "neutral";
}

function formatTimestamp(value?: string | null) {
  if (!value) return "UNAVAILABLE";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}

function getFeedState(washout: WashoutSnapshot | null) {
  const u = washout?.unified_engine;
  if (!washout || !u) return { kind: "UNAVAILABLE" as const, label: "RE-ENTRY ENGINE UNAVAILABLE" };
  if ((u.data_quality_status || washout.data_quality?.status || "").toUpperCase() === "UNAVAILABLE") return { kind: "UNAVAILABLE" as const, label: "RE-ENTRY ENGINE UNAVAILABLE" };
  const phase = u.market_phase || "UNAVAILABLE";
  const stamp = u.timestamp_et || washout.snapshot_generated_at_et || washout.values?.timestamp_et;
  if ((phase === "LIVE_PROVISIONAL" || phase === "CLOSE_SETTLING") && stamp) {
    const ageMs = Date.now() - new Date(stamp).getTime();
    if (!Number.isFinite(ageMs) || ageMs > 30 * 60 * 1000) return { kind: "STALE" as const, label: "STALE DATA" };
  }
  if (!stamp) return { kind: "STALE" as const, label: "STALE DATA" };
  return { kind: "OK" as const, label: "OK" };
}

function phaseLabel(phase?: string) {
  if (phase === "MARKET_CLOSED_FINAL") return "MARKET CLOSED - FINAL";
  if (phase === "CLOSE_SETTLING") return "CLOSE SETTLING";
  if (phase === "LIVE_PROVISIONAL") return "LIVE - PROVISIONAL";
  return "UNAVAILABLE";
}

function UnifiedHero({ washout }: { washout: WashoutSnapshot }) {
  const u = washout.unified_engine!;
  const decision = u.decision || u.state || "UNAVAILABLE";
  const label = decision === "GO_EARLY" ? "GO EARLY" : decision;
  const fast = u.fast_family_count ?? 0;
  const context = u.context_support_count ?? 0;
  const stamp = u.timestamp_et || washout.snapshot_generated_at_et || washout.values?.timestamp_et;
  return <section className="hero card">
    <div className="eyebrow-row"><span className="eyebrow">RE-ENTRY</span><span className="freshness"><Clock3 size={14} /> {phaseLabel(u.market_phase)}</span></div>
    <div className="hero-grid">
      <div><div className={`signal ${stateClass(decision)}`}>{label}</div><div className="signal-subline">{u.decision_reason || "Canonical unified decision reason unavailable."}</div></div>
      <div className="decision-summary"><span className="summary-label">CURRENT ENGINE STATE</span><div className="decision-tags"><span><small>Oversold setup</small><b>{u.oversold_gate ? "YES" : "NO"}</b></span><span><small>Fast reversal families</small><b>{fast}/4</b></span><span><small>Context support</small><b>{context}/4</b></span></div><p>Snapshot {formatTimestamp(stamp)}. Engine {u.engine_version || "REENTRY_UNIFIED_v1"}.</p></div>
    </div>
  </section>;
}

function MarketContext({ live, washout }: { live: IntradaySnapshot | null; washout: WashoutSnapshot }) {
  const phase = washout.unified_engine?.market_phase;
  const regularSession = phase === "LIVE_PROVISIONAL";
  const spy = live?.quotes?.SPY;
  const qqq = live?.quotes?.QQQ;
  const last = spy?.timestamp ? formatTimestamp(spy.timestamp) : "UNAVAILABLE";
  return <section className="card section-card live-card">
    <div className="section-heading"><div><span className="kicker">MARKET PHASE</span><h2>{phaseLabel(phase)}</h2></div><span className="freshness"><Radio size={14} /> Price context {last}</span></div>
    {live ? <div className="live-grid"><div className="live-stat"><small>SPY {regularSession ? "today" : "last session"}</small><strong>{pct(spy?.change_pct,2)}</strong><span>{spy?.price?.toFixed(2) ?? "-"}</span></div><div className="live-stat"><small>QQQ {regularSession ? "today" : "last session"}</small><strong>{pct(qqq?.change_pct,2)}</strong><span>{qqq?.price?.toFixed(2) ?? "-"}</span></div></div> : <div className="notice"><CircleAlert size={16} /> Price-context feed unavailable. The canonical RE-ENTRY decision is not replaced or recomputed.</div>}
  </section>;
}

export default async function Home() {
  const [snapshot, intraday, washout, historical] = await Promise.all([getLatestSnapshot(), getIntradaySnapshot(), getWashoutSnapshot(), getHistoricalEpisodeEvidence()]);
  const feed = getFeedState(washout);
  const unified = washout?.unified_engine;

  return <main className="shell">
    <header className="topbar"><div><span className="brand">RE-ENTRY</span><span className="tagline">Know when waiting stops helping.</span></div><div className="top-status">{unified ? phaseLabel(unified.market_phase) : "UNAVAILABLE"}</div></header>
    {feed.kind !== "OK" ? <section className="card data-blocked"><CircleAlert /> <div><b>{feed.label}</b><p>{feed.kind === "STALE" ? "The canonical unified snapshot is older than the allowed live-session freshness window. It is shown below for transparency but must not be treated as current." : "No fallback decision is shown when the unified engine cannot be loaded."}</p></div></section> : null}
    {!washout || !unified ? null : <>
      <UnifiedHero washout={washout} />
      <MarketContext live={intraday} washout={washout} />
      <ReentryDecisionDetails washout={washout} />
      {snapshot ? <MarketMovementTables snapshot={snapshot} live={intraday} /> : <section className="card section-card"><div className="notice"><CircleAlert size={16} /> Sector and subsector context unavailable.</div></section>}
      <AggregateHistoricalEvidence evidence={historical} />
    </>}
    <footer>REENTRY_UNIFIED_v1 is the only operational decision source. Live readings are provisional, final readings are labeled final, and archived historical evidence cannot override the canonical decision.</footer>
  </main>;
}
