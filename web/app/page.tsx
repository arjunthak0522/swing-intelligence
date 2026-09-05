import { ArrowDownRight, ArrowUpRight, ChevronRight, CircleAlert, CircleCheck, Clock3 } from "lucide-react";
import { getLatestSnapshot, pct, type ReentrySnapshot } from "../lib/reentry";
import { sampleSnapshot } from "../lib/sampleSnapshot";

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
  if (v.includes("REPAIR") || v.includes("YES")) return "good";
  if (v.includes("WAIT") || v.includes("STABIL") || v.includes("DEVELOP")) return "warn";
  if (v.includes("NO") || v.includes("WORSEN") || v.includes("HEAVY")) return "bad";
  return "neutral";
}

function StatusPill({ children }: { children: React.ReactNode }) {
  return <span className="pill">{children}</span>;
}

function Hero({ s, usingPreview }: { s: ReentrySnapshot; usingPreview: boolean }) {
  return (
    <section className="hero card">
      <div className="eyebrow-row">
        <span className="eyebrow">RE-ENTRY</span>
        <span className="freshness"><Clock3 size={14} /> As of {s.as_of} close</span>
      </div>
      <div className={`signal ${stateClass(s.signal)}`}>{s.signal}</div>
      <p className="hero-copy">{s.signal_interpretation}</p>
      <div className="status-grid">
        <div><span>Market damage</span><strong>{s.market_damage}</strong></div>
        <div><span>Internal reset</span><strong>{s.internal_reset}</strong></div>
        <div><span>Selling pressure</span><strong>{s.selling_pressure}</strong></div>
        <div><span>Historical evidence</span><strong>{s.analog_decision}</strong></div>
      </div>
      {usingPreview && <div className="preview-note">Research preview using the validated Sep 4 completed-close snapshot. Live API is not connected yet.</div>}
    </section>
  );
}

function VehicleCard({ s }: { s: ReentrySnapshot }) {
  const h = s.historical_validation;
  return (
    <section className="card section-card">
      <div className="section-heading">
        <div>
          <span className="kicker">ACTION</span>
          <h2>What the engine is for</h2>
        </div>
        <StatusPill>Broad-market re-entry</StatusPill>
      </div>
      <p className="section-intro">The validated decision is whether to redeploy cash into broad equities. SPY and QQQ are the intended vehicles. Sector and subsector ETFs are evidence, not standalone buy signals.</p>
      <div className="vehicle-grid">
        <div className="vehicle">
          <div className="vehicle-title"><span>S&P 500</span><b>SPY</b></div>
          <p>Broad, diversified re-entry vehicle.</p>
          <div className="mini-stats"><span>10D median after signal <b>{pct(h.SPY_10D_median_after_signal, 2)}</b></span><span>60D <b>{pct(h.SPY_60D_median_after_signal, 2)}</b></span></div>
        </div>
        <div className="vehicle">
          <div className="vehicle-title"><span>Nasdaq 100</span><b>QQQ</b></div>
          <p>Growth-heavy re-entry vehicle.</p>
          <div className="mini-stats"><span>10D median after signal <b>{pct(h.QQQ_10D_median_after_signal, 2)}</b></span><span>60D <b>{pct(h.QQQ_60D_median_after_signal, 2)}</b></span></div>
        </div>
      </div>
      <div className="notice"><CircleAlert size={16} /> No validated SPY-vs-QQQ preference rule is being invented here. The app will only show a preferred vehicle after that comparison is separately validated.</div>
    </section>
  );
}

function WhyNow({ s }: { s: ReentrySnapshot }) {
  const insights = s.market_insights;
  return (
    <section className="card section-card">
      <div className="section-heading">
        <div><span className="kicker">WHY</span><h2>What is driving the call</h2></div>
      </div>
      <p className="section-intro">{insights?.headline || "The engine combines market damage, internal repair and historical evidence into one decision."}</p>
      <div className="two-col">
        <div className="reason-panel supportive">
          <h3><CircleCheck size={17} /> Supporting re-entry</h3>
          {(insights?.supporting_reentry || []).map((x, i) => (
            <div className="reason" key={i}>
              <div><b>{x.title}{x.symbol ? ` (${x.symbol})` : ""}</b>{x.state && <StatusPill>{x.state}</StatusPill>}</div>
              <p>{x.detail}</p>
              {x.why_it_matters && <small>{x.why_it_matters}</small>}
            </div>
          ))}
        </div>
        <div className="reason-panel holding">
          <h3><CircleAlert size={17} /> Holding it back</h3>
          {(insights?.holding_back || []).map((x, i) => (
            <div className="reason" key={i}>
              <div><b>{x.title}</b>{x.state && <StatusPill>{x.state}</StatusPill>}</div>
              <p>{x.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function MarketInternals({ s }: { s: ReentrySnapshot }) {
  const proxies = Object.entries(s.subsector_intelligence?.proxies || {})
    .sort((a, b) => Math.abs(b[1].drawdown_20d) - Math.abs(a[1].drawdown_20d));
  return (
    <section className="card section-card">
      <div className="section-heading">
        <div><span className="kicker">UNDER THE SURFACE</span><h2>Market internals</h2></div>
        <StatusPill>{pct(s.subsector_intelligence?.aggregate?.damage_share_3pct)} damaged 3%+</StatusPill>
      </div>
      <div className="internal-list">
        {proxies.slice(0, 8).map(([symbol, x]) => (
          <details key={symbol} className="internal-row">
            <summary>
              <div className="name-wrap"><span className="state-dot" data-state={x.repairing ? "repair" : "damage"} /><div><b>{x.label} <span>({symbol})</span></b><small>{sectorNames[x.parent_sector] || x.parent_sector}</small></div></div>
              <div className="row-metrics"><span>{pct(x.drawdown_20d)}</span><strong className={x.repairing ? "good-text" : "muted"}>{x.repairing ? "REPAIRING" : "DAMAGED"}</strong><ChevronRight size={17} /></div>
            </summary>
            <div className="detail-grid">
              <span>20D drawdown <b>{pct(x.drawdown_20d)}</b></span>
              <span>60D drawdown <b>{pct(x.drawdown_60d)}</b></span>
              <span>1D return <b>{pct(x.return_1d)}</b></span>
              <span>5D return <b>{pct(x.return_5d)}</b></span>
              <span>vs SPY 20D <b>{pct(x.relative_strength_20d_vs_spy)}</b></span>
              <span>vs {x.parent_sector} 20D <b>{pct(x.relative_strength_20d_vs_parent)}</b></span>
            </div>
            <p className="detail-copy">{x.repairing ? `${x.label} is repairing after a meaningful reset. That is constructive early evidence, but it remains context rather than an independent re-entry trigger.` : `${x.label} remains materially damaged or lagging. The engine tracks whether this weakness begins to stabilize and broaden into repair.`}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

function SectorMap({ s }: { s: ReentrySnapshot }) {
  const sectors = Object.entries(s.signal_snapshot?.sectors || {});
  return (
    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">BREADTH OF DAMAGE</span><h2>Sector map</h2></div></div>
      <div className="sector-grid">
        {sectors.map(([symbol, x]) => {
          const group = s.subsector_intelligence?.by_sector?.[symbol];
          const repairing = (group?.repair_share || 0) > 0;
          return <div className="sector" key={symbol}>
            <div className="sector-top"><b>{sectorNames[symbol] || symbol}</b><span>{symbol}</span></div>
            <strong>{pct(x.drawdown_20d)}</strong>
            <small>20D drawdown</small>
            <div className="sector-bottom"><span>{pct(group?.damage_share_3pct)} groups 3%+ down</span><span className={repairing ? "good-text" : "muted"}>{repairing ? "Repairing" : "No broad repair"}</span></div>
          </div>;
        })}
      </div>
    </section>
  );
}

function Historical({ s }: { s: ReentrySnapshot }) {
  const h = s.historical_validation;
  const rows = [
    ["5D", h.SPY_5D_median_after_signal, h.QQQ_5D_median_after_signal],
    ["10D", h.SPY_10D_median_after_signal, h.QQQ_10D_median_after_signal],
    ["30D", h.SPY_30D_median_after_signal, h.QQQ_30D_median_after_signal],
    ["60D", h.SPY_60D_median_after_signal, h.QQQ_60D_median_after_signal],
  ] as const;
  return (
    <section className="card section-card">
      <div className="section-heading">
        <div><span className="kicker">VALIDATED HISTORY</span><h2>Historical evidence</h2></div>
        <StatusPill>{h.final_independent_reentry_episodes} independent signals</StatusPill>
      </div>
      <p className="section-intro">These are outcomes after the validated RE-ENTRY signal historically. They are separate from the 40 nearest analogs used to judge today.</p>
      <div className="history-table">
        <div className="history-head"><span>Horizon</span><span>SPY median</span><span>QQQ median</span></div>
        {rows.map(([label, spy, qqq]) => <div className="history-row" key={label}><b>{label}</b><span>{pct(spy, 2)}</span><span>{pct(qqq, 2)}</span></div>)}
      </div>
      <div className="history-footer"><span>Current analog verdict</span><strong className={stateClass(s.analog_decision)}>{s.analog_decision}</strong></div>
    </section>
  );
}

export default async function Home() {
  let snapshot: ReentrySnapshot | null = null;
  try { snapshot = await getLatestSnapshot(); } catch { snapshot = null; }
  const usingPreview = !snapshot;
  const s = snapshot || sampleSnapshot;
  const fresh = s.data_freshness?.same_day_complete !== false;

  return (
    <main className="shell">
      <header className="topbar">
        <div><span className="brand">RE-ENTRY</span><span className="tagline">Know when waiting stops helping.</span></div>
        <div className="top-status">{fresh ? <><span className="live-dot" /> Completed-close data</> : "DATA INCOMPLETE"}</div>
      </header>
      {!fresh ? <section className="card data-blocked"><CircleAlert /> <div><b>DATA INCOMPLETE</b><p>The current decision is suppressed until every required input resolves to the same completed market session.</p></div></section> : <>
        <Hero s={s} usingPreview={usingPreview} />
        <VehicleCard s={s} />
        <WhyNow s={s} />
        <MarketInternals s={s} />
        <SectorMap s={s} />
        <Historical s={s} />
      </>}
      <footer>RE-ENTRY uses completed-close data and reevaluates after every market session. Historical evidence supports decision timing, not guaranteed returns.</footer>
    </main>
  );
}
