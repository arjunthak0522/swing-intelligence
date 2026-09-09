import { CircleAlert, Clock3, Radio, ChevronDown } from "lucide-react";
import MarketMovementTables from "./MarketMovementTables";
import HistoricalEvidence from "./HistoricalEvidence";
import ShadowValidationPanel from "./ShadowValidationPanel";
import VolumeBreadthPanel from "./VolumeBreadthPanel";
import { getHistoricalEpisodeEvidence } from "../lib/historicalEvidence";
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
  if (v.includes("REPAIR") || v.includes("YES") || v.includes("LIVE") || v.includes("FAVORABLE") || v.includes("STABLE")) return "good";
  if (v.includes("WAIT") || v.includes("STABIL") || v.includes("DEVELOP") || v.includes("PARTIAL") || v.includes("RESET") || v.includes("WATCH") || v.includes("CAUTION")) return "warn";
  if (v.includes("NO") || v.includes("WORSEN") || v.includes("HEAVY") || v.includes("DEGRADED") || v.includes("DEEP") || v.includes("DETERIORATING")) return "bad";
  return "neutral";
}

function retailHistoryLabel(value: string) {
  const v = value.toUpperCase();
  if (v === "CAUTIOUS YES") return "FAVORABLE";
  if (v.includes("YES")) return "FAVORABLE";
  if (v.includes("NO")) return "UNFAVORABLE";
  return value;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function DecisionHero({ s }: { s: ReentrySnapshot }) {
  const closer = s.signal === "WAIT" && ["DEVELOPING", "MEANINGFUL", "BROAD"].includes(s.internal_reset);
  const displaySignal = s.signal === "WAIT" ? "WAIT FOR NEW ENTRY" : s.signal;
  return (
    <section className="decision-hero">
      <div className="decision-label-row">
        <span className="kicker">OFFICIAL DECISION</span>
        <span className="freshness"><Clock3 size={14} /> {formatDate(s.as_of)} completed close</span>
      </div>
      <div className={`decision-word ${stateClass(s.signal)}`}>{displaySignal}</div>
      <p className="decision-copy">{closer ? "A prior entry already occurred. Wait for a new setup before deploying additional cash." : s.signal_interpretation}</p>
    </section>
  );
}

function EpisodeStrip({ episode, live }: { episode: ReentryEpisode | null; live: IntradaySnapshot | null }) {
  if (!episode) return null;
  const spyPrice = live?.quotes?.SPY?.price;
  const qqqPrice = live?.quotes?.QQQ?.price;
  const spyPerformance = typeof spyPrice === "number" && episode.entry_closes.SPY > 0 ? spyPrice / episode.entry_closes.SPY - 1 : null;
  const qqqPerformance = typeof qqqPrice === "number" && episode.entry_closes.QQQ > 0 ? qqqPrice / episode.entry_closes.QQQ - 1 : null;
  return (
    <section className="episode-strip">
      <div className="episode-meta"><span className="kicker">CURRENT RE-ENTRY EPISODE</span><b>Started {formatDate(episode.episode_start)}</b></div>
      <div className="episode-metric"><span>SPY</span><strong className={typeof spyPerformance === "number" ? (spyPerformance >= 0 ? "good-text" : "bad-text") : "muted"}>{pct(spyPerformance, 2)}</strong><small>since re-entry</small></div>
      <div className="episode-metric"><span>QQQ</span><strong className={typeof qqqPerformance === "number" ? (qqqPerformance >= 0 ? "good-text" : "bad-text") : "muted"}>{pct(qqqPerformance, 2)}</strong><small>since re-entry</small></div>
      <span className="pill">{episode.active ? "ACTIVE" : "COMPLETED"}</span>
    </section>
  );
}

function LiveToday({ live, official }: { live: IntradaySnapshot | null; official: ReentrySnapshot }) {
  const quality = live?.state_quality;
  const spy = live?.quotes?.SPY;
  const qqq = live?.quotes?.QQQ;
  const vix = live?.quotes?.["^VIX"];
  const regular = spy?.market_state === "REGULAR";
  const updated = spy?.timestamp ? new Date(spy.timestamp).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit", timeZoneName: "short" }) : null;

  if (!live || !quality) {
    return <section className="today-card"><div><span className="kicker">LIVE TODAY</span><h2>Intraday context unavailable</h2></div><p>The completed-close decision remains authoritative.</p></section>;
  }

  return (
    <section className="today-card">
      <div className="today-topline">
        <div><span className="kicker">LIVE TODAY · CONTEXT ONLY</span><h2 className={stateClass(quality.label)}>{quality.label}</h2></div>
        <span className="freshness"><Radio size={14} /> {regular ? "Live" : "Latest session"}{updated ? ` · ${updated}` : ""}</span>
      </div>
      <div className="today-drivers">
        <div><small>PRICE</small><b className={quality.risks.broad_negative ? "bad-text" : "good-text"}>{quality.risks.broad_negative ? "WEAK" : "HOLDING UP"}</b></div>
        <VolumeBreadthPanel compact />
        <div><small>VOLATILITY</small><b className={quality.risks.vix_up ? "bad-text" : "good-text"}>{quality.risks.vix_up ? "VIX RISING" : "NOT RISING"}</b></div>
      </div>
      <p className="today-copy">{quality.label === "DETERIORATING" ? "Today's market action is putting meaningful pressure on the active RE-ENTRY state." : quality.label === "CAUTION" ? "Multiple deterioration conditions are present, but the official close decision has not changed." : quality.label === "WATCH" ? "One deterioration condition is present. The official close decision remains unchanged." : "Today's market action is broadly supporting the existing RE-ENTRY state."}</p>
      <details className="compact-disclosure">
        <summary>View live detail <ChevronDown size={15} /></summary>
        <div className="live-detail-grid">
          <div><small>SPY today</small><b>{pct(spy?.change_pct, 2)}</b></div>
          <div><small>QQQ today</small><b>{pct(qqq?.change_pct, 2)}</b></div>
          <div><small>VIX today</small><b>{pct(vix?.change_pct, 2)}</b></div>
        </div>
        <VolumeBreadthPanel />
        <div className="context-note"><CircleAlert size={15} /> Official decision remains <b>{official.signal}</b> until the completed-close engine recalculates.</div>
      </details>
    </section>
  );
}

function WhyDecision({ s }: { s: ReentrySnapshot }) {
  const support = s.market_insights?.supporting_reentry || [];
  const hold = s.market_insights?.holding_back || [];
  const rows = [
    { label: "Market damage", value: s.market_damage, detail: "How much broad-market damage is present relative to the pullback context." },
    { label: "Internal reset", value: s.internal_reset, detail: support[0] || s.market_insights?.headline || s.signal_interpretation },
    { label: "Selling pressure", value: s.selling_pressure, detail: hold[0] || "Completed-close evidence describing whether selling pressure is worsening or stabilizing." },
    { label: "Similar past markets", value: retailHistoryLabel(s.analog_decision), detail: "Nearest prior broad-market states are used as historical context for the official decision." },
  ];
  return (
    <section className="simple-section">
      <div className="simple-heading"><span className="kicker">WHY THIS DECISION</span><h2>Four things that matter</h2></div>
      <div className="evidence-list">
        {rows.map((row) => <details key={row.label} className="evidence-row"><summary><span>{row.label}</span><b className={stateClass(row.value)}>{row.value}</b><ChevronDown size={16} /></summary><p>{row.detail}</p></details>)}
      </div>
    </section>
  );
}

function MarketInternalsSummary({ snapshot, live }: { snapshot: ReentrySnapshot; live: IntradaySnapshot | null }) {
  const sectors = Object.keys(snapshot.signal_snapshot?.sectors || {}).map((symbol) => ({ symbol, move: live?.quotes?.[symbol]?.change_pct ?? null })).filter((x) => typeof x.move === "number") as { symbol: string; move: number }[];
  sectors.sort((a, b) => b.move - a.move);
  const strongest = sectors.slice(0, 3);
  const weakest = sectors.slice(-3).reverse();
  return (
    <section className="simple-section">
      <div className="simple-heading"><span className="kicker">MARKET INTERNALS</span><h2>What is leading and lagging today?</h2></div>
      <div className="internals-summary-grid internals-summary-grid-two">
        <div><small>STRONGEST SECTORS</small>{strongest.map((x) => <span key={x.symbol}><b>{x.symbol}</b>{pct(x.move, 1)}</span>)}</div>
        <div><small>WEAKEST SECTORS</small>{weakest.map((x) => <span key={x.symbol}><b>{x.symbol}</b>{pct(x.move, 1)}</span>)}</div>
      </div>
      <details className="deep-disclosure"><summary>Explore all sectors & subsectors <ChevronDown size={16} /></summary><div className="nested-detail"><MarketMovementTables snapshot={snapshot} live={live} /></div></details>
    </section>
  );
}

function ResearchSection() {
  return (
    <details className="research-section">
      <summary><div><span className="kicker">RESEARCH & VALIDATION</span><h2>Experimental layers and forward testing</h2><p>Nothing here changes the official RE-ENTRY decision.</p></div><div className="research-status"><span className="pill">COLLAPSED BY DEFAULT</span><ChevronDown size={18} /></div></summary>
      <div className="research-body">
        <ShadowValidationPanel />
        <section className="research-note">
          <div><span className="kicker">ETF RELATIVE OPPORTUNITY</span><h3>Under validation</h3></div>
          <p>Historical ETF ranking percentages remain suppressed until the underlying adjusted-price history is point-in-time reproducible.</p>
        </section>
        <section className="research-note">
          <div><span className="kicker">SHORT-TERM OVERSOLD / EXHAUSTION</span><h3>Research planned</h3></div>
          <p>Breadth exhaustion, normalized downside stretch, VWAP recovery, and volatility reversal are not yet part of the official or live decision layer.</p>
        </section>
      </div>
    </details>
  );
}

function PageStyles() {
  return <style>{`
    .decision-hero{padding:34px 0 26px;border-bottom:1px solid var(--line)}
    .decision-label-row,.today-topline,.simple-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}
    .decision-word{font-size:72px;line-height:.95;font-weight:900;letter-spacing:-.065em;margin:16px 0 12px}.decision-word.good{color:var(--green)}.decision-word.warn{color:var(--amber)}.decision-word.bad{color:var(--red)}
    .decision-copy{max-width:760px;margin:0;font-size:17px;line-height:1.55;color:#41433e}
    .episode-strip{display:grid;grid-template-columns:1.5fr 1fr 1fr auto;gap:20px;align-items:center;padding:20px 0;border-bottom:1px solid var(--line)}.episode-meta span,.episode-meta b,.episode-metric span,.episode-metric strong,.episode-metric small{display:block}.episode-meta b{margin-top:5px}.episode-metric span,.episode-metric small{font-size:9px;color:var(--muted)}.episode-metric strong{font-size:32px;letter-spacing:-.04em;margin:2px 0}
    .today-card{padding:26px 0;border-bottom:1px solid var(--line)}.today-card h2{font-size:38px;margin:4px 0 0;letter-spacing:-.04em}.today-card h2.good{color:var(--green)}.today-card h2.warn{color:var(--amber)}.today-card h2.bad{color:var(--red)}
    .today-drivers{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:18px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.today-drivers>div{padding:14px 0}.today-drivers>div+div{border-left:1px solid var(--line);padding-left:18px}.today-drivers small,.today-drivers b{display:block}.today-drivers small{font-size:9px;color:var(--muted);margin-bottom:4px}.today-copy{font-size:13px;color:#4a4d46;margin:14px 0 0}
    .compact-disclosure,.deep-disclosure{margin-top:12px}.compact-disclosure>summary,.deep-disclosure>summary{display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;font-weight:800;color:var(--muted);list-style:none}.compact-disclosure>summary::-webkit-details-marker,.deep-disclosure>summary::-webkit-details-marker{display:none}.compact-disclosure[open]>summary svg,.deep-disclosure[open]>summary svg{transform:rotate(180deg)}
    .live-detail-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}.live-detail-grid>div{padding:12px;background:#f4f1eb;border-radius:10px}.live-detail-grid small,.live-detail-grid b{display:block}.live-detail-grid small{font-size:9px;color:var(--muted)}.live-detail-grid b{margin-top:3px}.context-note{display:flex;gap:8px;align-items:flex-start;margin-top:10px;font-size:10px;color:var(--muted)}
    .simple-section{padding:30px 0;border-bottom:1px solid var(--line)}.simple-heading h2{font-size:26px;letter-spacing:-.025em;margin:4px 0 0}
    .evidence-list{margin-top:16px;border-top:1px solid var(--line)}.evidence-row{border-bottom:1px solid var(--line)}.evidence-row>summary{display:grid;grid-template-columns:1fr auto 22px;gap:16px;align-items:center;padding:15px 0;cursor:pointer;list-style:none}.evidence-row>summary::-webkit-details-marker{display:none}.evidence-row>summary span{font-size:12px;font-weight:700}.evidence-row>summary b{font-size:12px}.evidence-row>summary b.good{color:var(--green)}.evidence-row>summary b.warn{color:var(--amber)}.evidence-row>summary b.bad{color:var(--red)}.evidence-row[open]>summary svg{transform:rotate(180deg)}.evidence-row p{margin:0 0 15px;max-width:760px;font-size:11px;color:var(--muted);line-height:1.5}
    .internals-summary-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-top:16px}.internals-summary-grid-two{grid-template-columns:1fr 1fr}.internals-summary-grid>div{padding:14px 0}.internals-summary-grid small{display:block;color:var(--muted);font-size:9px;margin-bottom:7px}.internals-summary-grid span{display:flex;justify-content:space-between;gap:10px;font-size:11px;padding:3px 0}.internals-summary-grid strong{display:block;font-size:28px;letter-spacing:-.04em}.nested-detail{margin-top:16px}.nested-detail>.card,.nested-detail>section.card,.nested-detail>details.card{box-shadow:none!important}
    .research-section{margin:30px 0 12px;border:1px solid var(--line);border-radius:16px;overflow:hidden}.research-section>summary{display:flex;justify-content:space-between;gap:20px;align-items:center;padding:20px 22px;cursor:pointer;list-style:none}.research-section>summary::-webkit-details-marker{display:none}.research-section>summary h2{margin:4px 0 3px;font-size:20px}.research-section>summary p{margin:0;color:var(--muted);font-size:10px}.research-status{display:flex;align-items:center;gap:8px}.research-section[open] .research-status svg{transform:rotate(180deg)}.research-body{padding:0 16px 16px;border-top:1px solid var(--line)}.research-note{padding:18px 8px;border-top:1px solid var(--line)}.research-note h3{margin:3px 0 0;font-size:16px}.research-note p{margin:8px 0 0;font-size:11px;color:var(--muted);max-width:760px}
    .good-text{color:var(--green)}.bad-text{color:var(--red)}
    @media(max-width:760px){.decision-word{font-size:48px}.decision-label-row,.today-topline,.simple-heading{display:block}.freshness{display:inline-flex;margin-top:8px}.episode-strip{grid-template-columns:1fr 1fr}.episode-meta{grid-column:1/-1}.today-drivers,.live-detail-grid,.internals-summary-grid{grid-template-columns:1fr 1fr}.today-drivers>div+div{border-left:0;padding-left:0}.today-drivers>div:nth-child(3){grid-column:1/-1}.research-section>summary{align-items:flex-start}.research-status .pill{display:none}}
  `}</style>;
}

export default async function Home() {
  const [snapshot, intraday, episode, historicalEvidence] = await Promise.all([
    getLatestSnapshot(),
    getIntradaySnapshot(),
    getLatestEpisode(),
    getHistoricalEpisodeEvidence(),
  ]);

  if (!snapshot) {
    return <main className="shell"><section className="card data-blocked"><CircleAlert /> <div><b>OFFICIAL FEED UNAVAILABLE</b><p>No fallback decision is shown when the canonical close snapshot cannot be loaded.</p></div></section></main>;
  }

  const fresh = snapshot.data_freshness?.same_day_complete === true;

  return <main className="shell">
    <PageStyles />
    <header className="topbar"><div><span className="brand">RE-ENTRY</span><span className="tagline">Know when waiting stops helping.</span></div><div className="top-status">{fresh ? <><span className="live-dot" /> Official close feed</> : "DATA INCOMPLETE"}</div></header>
    {!fresh ? <section className="card data-blocked"><CircleAlert /> <div><b>DATA INCOMPLETE</b><p>The current decision is suppressed until every required input resolves to the same completed market session.</p></div></section> : <>
      <DecisionHero s={snapshot} />
      <EpisodeStrip episode={episode} live={intraday} />
      <LiveToday live={intraday} official={snapshot} />
      <WhyDecision s={snapshot} />
      <MarketInternalsSummary snapshot={snapshot} live={intraday} />
      <HistoricalEvidence evidence={historicalEvidence} />
      <ResearchSection />
    </>}
    <footer>Official RE-ENTRY decisions use completed-close data. Live context and research layers never overwrite the validated close signal.</footer>
  </main>;
}