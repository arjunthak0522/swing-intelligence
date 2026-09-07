import { ChevronRight, CircleAlert, CircleCheck, Clock3 } from "lucide-react";
import { getLatestSnapshot, pct, type OpportunityHistoryRow, type ReentrySnapshot } from "../lib/reentry";
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
  if (v === "NO RE-ENTRY SETUP") return "neutral";
  if (v.includes("REPAIR") || v.includes("YES")) return "good";
  if (v.includes("WAIT") || v.includes("STABIL") || v.includes("DEVELOP")) return "warn";
  if (v.includes("NO") || v.includes("WORSEN") || v.includes("HEAVY")) return "bad";
  return "neutral";
}

function StatusPill({ children }: { children: React.ReactNode }) {
  return <span className="pill">{children}</span>;
}

function Hero({ s, usingPreview }: { s: ReentrySnapshot; usingPreview: boolean }) {
  const closer = s.signal === "WAIT" && ["DEVELOPING", "MEANINGFUL", "BROAD"].includes(s.internal_reset);
  const noSetup = s.signal === "NO RE-ENTRY SETUP";
  return (
    <section className="hero card">
      <div className="eyebrow-row">
        <span className="eyebrow">1 · BROAD-MARKET RE-ENTRY</span>
        <span className="freshness"><Clock3 size={14} /> {s.as_of} close</span>
      </div>
      <div className="hero-grid">
        <div>
          <div className={`signal ${stateClass(s.signal)}`}>{s.signal}</div>
          <div className="signal-subline">
            {noSetup
              ? "There is no meaningful pullback creating a broad-market re-entry opportunity right now."
              : closer
                ? "The setup is getting closer, but waiting still has value."
                : s.signal_interpretation}
          </div>
        </div>
        <div className="decision-summary">
          <span className="summary-label">WHY THIS DECISION</span>
          <p>{s.signal_interpretation}</p>
          <div className="decision-tags">
            <span><small>Market pullback</small><b>{s.market_damage}</b></span>
            <span><small>Recovery</small><b>{s.selling_pressure}</b></span>
            <span><small>Past setups</small><b>{s.analog_decision}</b></span>
          </div>
        </div>
      </div>
      {usingPreview && <div className="preview-note">Research preview using the validated Sep 4 completed-close snapshot. Live API is not connected yet.</div>}
    </section>
  );
}

function BroadMarketAction({ s }: { s: ReentrySnapshot }) {
  const h = s.historical_validation;
  if (s.signal === "NO RE-ENTRY SETUP") {
    return (
      <section className="card section-card action-card">
        <div className="section-heading"><div><span className="kicker">BROAD MARKET</span><h2>No re-entry action right now</h2></div><StatusPill>SPY + QQQ universe</StatusPill></div>
        <p className="section-intro">SPY and QQQ remain the validated broad-market universe, but the engine is not identifying a correction-based re-entry setup today.</p>
      </section>
    );
  }
  const heading = s.signal === "RE-ENTER" ? "Where the RE-ENTRY signal applies" : "What we are waiting to re-enter";
  const intro = s.signal === "RE-ENTER"
    ? "The validated broad-market RE-ENTRY signal applies to SPY and QQQ. The engine does not choose between them unless a separate vehicle-selection rule is validated."
    : "The engine is still waiting before putting cash back into the validated broad-market universe of SPY and QQQ.";
  return (
    <section className="card section-card action-card">
      <div className="section-heading"><div><span className="kicker">BROAD MARKET</span><h2>{heading}</h2></div><StatusPill>{s.signal}</StatusPill></div>
      <p className="section-intro">{intro}</p>
      <div className="vehicle-strip">
        <div className="vehicle-primary"><div><span>S&P 500</span><b>SPY</b></div><small>Validated broad-market vehicle</small><strong>{pct(h.SPY_10D_median_after_signal, 2)}</strong><em>10D median after past RE-ENTRY signals</em></div>
        <div className="vehicle-primary"><div><span>Nasdaq 100</span><b>QQQ</b></div><small>Validated broad-market vehicle</small><strong>{pct(h.QQQ_10D_median_after_signal, 2)}</strong><em>10D median after past RE-ENTRY signals</em></div>
      </div>
      <div className="notice"><CircleAlert size={16} /> Historical returns shown here describe past RE-ENTRY signals. They are not a forecast for buying today.</div>
    </section>
  );
}

function WhyNow({ s }: { s: ReentrySnapshot }) {
  const insights = s.market_insights;
  return (
    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">WHY</span><h2>What is driving the broad-market decision</h2></div></div>
      <p className="section-intro">{insights?.headline || "The engine combines market damage, internal repair and historical evidence into one decision."}</p>
      <div className="two-col">
        <div className="reason-panel supportive">
          <h3><CircleCheck size={17} /> Supporting re-entry</h3>
          {(insights?.supporting_reentry || []).slice(0, 4).map((x, i) => (
            <div className="reason" key={i}><div><b>{x.title}{x.symbol ? ` (${x.symbol})` : ""}</b>{x.state && <StatusPill>{x.state}</StatusPill>}</div><p>{x.detail}</p>{x.why_it_matters && <small>{x.why_it_matters}</small>}</div>
          ))}
        </div>
        <div className="reason-panel holding">
          <h3><CircleAlert size={17} /> Why waiting may still help</h3>
          {(insights?.holding_back || []).slice(0, 4).map((x, i) => (
            <div className="reason" key={i}><div><b>{x.title}</b>{x.state && <StatusPill>{x.state}</StatusPill>}</div><p>{x.detail}</p></div>
          ))}
        </div>
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
      <div className="section-heading"><div><span className="kicker">2 · HISTORICAL BACKTEST</span><h2>What happened after past RE-ENTRY signals?</h2></div><StatusPill>{h.final_independent_reentry_episodes} independent signals</StatusPill></div>
      <p className="section-intro">This is the strategy&apos;s historical evidence. These medians show what SPY and QQQ did after prior validated RE-ENTRY signals. They do not predict today&apos;s return and they are separate from today&apos;s nearest historical-setup verdict.</p>
      <div className="history-table">
        <div className="history-head"><span>After signal</span><span>SPY median</span><span>QQQ median</span></div>
        {rows.map(([label, spy, qqq]) => <div className="history-row" key={label}><b>{label}</b><span>{pct(spy, 2)}</span><span>{pct(qqq, 2)}</span></div>)}
      </div>
      <div className="history-footer"><span>Do today&apos;s historical setups support broad-market re-entry?</span><strong className={stateClass(s.analog_decision)}>{s.analog_decision}</strong></div>
    </section>
  );
}

function OpportunityHistory({ history }: { history?: Record<string, OpportunityHistoryRow> | null }) {
  if (!history) return <small>Historical post-RE-ENTRY evidence is not available for this ETF&apos;s usable history.</small>;
  const rows = ["10", "30", "60"].map((h) => [h, history[h]] as const).filter(([, row]) => row);
  if (!rows.length) return <small>Historical post-RE-ENTRY evidence is not available for this ETF&apos;s usable history.</small>;
  return (
    <small>
      {rows.map(([h, row], index) => (
        <span key={h}>{index ? " · " : ""}{h}D: {pct(row?.median, 1)} median, {pct(row?.positive_rate, 0)} positive{row?.n ? ` (n=${row.n})` : ""}</span>
      ))}
    </small>
  );
}

function Opportunities({ s }: { s: ReentrySnapshot }) {
  const evidence = s.opportunity_evidence;
  const evidenceSectors = evidence?.sectors || [];
  const evidenceSubsectors = evidence?.subsectors || [];

  const proxies = Object.entries(s.subsector_intelligence?.proxies || {});
  const fallbackSubsectors = proxies
    .filter(([, x]) => x.repairing)
    .sort((a, b) => a[1].drawdown_20d - b[1].drawdown_20d);
  const fallbackSectors = Object.entries(s.subsector_intelligence?.by_sector || {})
    .filter(([, group]) => (group.damage_share_3pct || 0) >= 0.50 && (group.repair_share || 0) >= 0.25)
    .sort((a, b) => (b[1].repair_share || 0) - (a[1].repair_share || 0));

  const hasEvidenceCandidates = evidenceSectors.length > 0 || evidenceSubsectors.length > 0;
  const hasFallbackCandidates = fallbackSubsectors.length > 0 || fallbackSectors.length > 0;
  const hasCandidates = evidence ? hasEvidenceCandidates : hasFallbackCandidates;

  return (
    <section className="card section-card">
      <div className="section-heading">
        <div><span className="kicker">3 · SECTOR / SUBSECTOR OPPORTUNITIES</span><h2>Is anything under the surface attractive right now?</h2></div>
        <StatusPill>{hasCandidates ? "REPAIR CANDIDATES PRESENT" : "NO REPAIR CANDIDATES"}</StatusPill>
      </div>
      <p className="section-intro">A candidate must first be damaged enough to reset and then show current repair. When historical evidence is available, the same row also shows what that ETF did after past canonical RE-ENTRY episodes. This does not create a separate sector timing engine: the broad-market RE-ENTRY decision above remains the controlling timing call.</p>

      {!hasCandidates ? (
        <div className="notice"><CircleAlert size={16} /> No sector or subsector currently meets the existing repair-candidate conditions.</div>
      ) : evidence ? (
        <div className="two-col">
          <div className="reason-panel supportive">
            <h3><CircleCheck size={17} /> Sectors showing repair now</h3>
            {evidenceSectors.slice(0, 6).map((x) => (
              <div className="reason" key={x.symbol}>
                <div><b>{x.label} ({x.symbol})</b><StatusPill>{x.current_state}</StatusPill></div>
                <p>{pct(x.damage_share_3pct)} of tracked subsectors are down 3%+ and {pct(x.repair_share)} are repairing.</p>
                <OpportunityHistory history={x.historical_after_reentry} />
              </div>
            ))}
            {evidenceSectors.length === 0 && <div className="reason"><p>No sector currently meets the existing sector-repair threshold.</p></div>}
          </div>

          <div className="reason-panel supportive">
            <h3><CircleCheck size={17} /> Subsectors showing repair now</h3>
            {evidenceSubsectors.slice(0, 6).map((x) => (
              <div className="reason" key={x.symbol}>
                <div><b>{x.label} ({x.symbol})</b><StatusPill>{x.current_state}</StatusPill></div>
                <p>{pct(x.drawdown_20d)} from its 20-day high, {pct(x.return_5d)} over the last 5 days. Parent: {sectorNames[x.parent_sector] || x.parent_sector}.</p>
                <OpportunityHistory history={x.historical_after_reentry} />
              </div>
            ))}
            {evidenceSubsectors.length === 0 && <div className="reason"><p>No tracked subsector is currently flagged as repairing.</p></div>}
          </div>
        </div>
      ) : (
        <div className="two-col">
          <div className="reason-panel supportive">
            <h3><CircleCheck size={17} /> Sectors showing repair now</h3>
            {fallbackSectors.slice(0, 6).map(([symbol, group]) => (
              <div className="reason" key={symbol}>
                <div><b>{sectorNames[symbol] || symbol} ({symbol})</b><StatusPill>REPAIRING</StatusPill></div>
                <p>{pct(group.damage_share_3pct)} of tracked subsectors are down 3%+ and {pct(group.repair_share)} are repairing.</p>
                <small>Historical candidate evidence has not yet been attached to this snapshot.</small>
              </div>
            ))}
          </div>
          <div className="reason-panel supportive">
            <h3><CircleCheck size={17} /> Subsectors showing repair now</h3>
            {fallbackSubsectors.slice(0, 6).map(([symbol, x]) => (
              <div className="reason" key={symbol}>
                <div><b>{x.label} ({symbol})</b><StatusPill>REPAIRING</StatusPill></div>
                <p>{pct(x.drawdown_20d)} from its 20-day high, {pct(x.return_5d)} over the last 5 days.</p>
                <small>Historical candidate evidence has not yet been attached to this snapshot.</small>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="notice"><CircleAlert size={16} /> “REPAIRING” means a current opportunity candidate. It is not a standalone buy call. Historical statistics are outcomes after canonical broad-market RE-ENTRY episodes, not forecasts for this specific trade.</div>
    </section>
  );
}

function MarketInternals({ s }: { s: ReentrySnapshot }) {
  const proxies = Object.entries(s.subsector_intelligence?.proxies || {}).sort((a, b) => Math.abs(b[1].drawdown_20d) - Math.abs(a[1].drawdown_20d));
  return (
    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">DEEPER EVIDENCE</span><h2>What is moving underneath</h2></div><StatusPill>{pct(s.subsector_intelligence?.aggregate?.damage_share_3pct)} damaged 3%+</StatusPill></div>
      <p className="section-intro">Use this only when you want the underlying evidence behind the opportunity section.</p>
      <div className="internal-list">
        {proxies.slice(0, 8).map(([symbol, x]) => (
          <details key={symbol} className="internal-row">
            <summary><div className="name-wrap"><span className="state-dot" data-state={x.repairing ? "repair" : "damage"} /><div><b>{x.label} <span>({symbol})</span></b><small>{sectorNames[x.parent_sector] || x.parent_sector}</small></div></div><div className="row-metrics"><span>{pct(x.drawdown_20d)}</span><strong className={x.repairing ? "good-text" : "muted"}>{x.repairing ? "REPAIRING" : "DAMAGED"}</strong><ChevronRight size={17} /></div></summary>
            <div className="detail-grid"><span>20D drawdown <b>{pct(x.drawdown_20d)}</b></span><span>60D drawdown <b>{pct(x.drawdown_60d)}</b></span><span>1D return <b>{pct(x.return_1d)}</b></span><span>5D return <b>{pct(x.return_5d)}</b></span><span>vs SPY 20D <b>{pct(x.relative_strength_20d_vs_spy)}</b></span><span>vs {x.parent_sector} 20D <b>{pct(x.relative_strength_20d_vs_parent)}</b></span></div>
            <p className="detail-copy">{x.repairing ? `${x.label} is repairing after a meaningful reset. That is constructive evidence, but it remains context rather than an independent re-entry trigger.` : `${x.label} remains materially damaged or lagging. The engine tracks whether this weakness begins to stabilize and repair.`}</p>
          </details>
        ))}
      </div>
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
      {!fresh ? (
        <section className="card data-blocked"><CircleAlert /> <div><b>DATA INCOMPLETE</b><p>No re-entry, historical-comparison, or opportunity conclusion is shown until every required input resolves to the same completed market session.</p></div></section>
      ) : (
        <>
          <Hero s={s} usingPreview={usingPreview} />
          <BroadMarketAction s={s} />
          <WhyNow s={s} />
          <Historical s={s} />
          <Opportunities s={s} />
          <MarketInternals s={s} />
        </>
      )}
      <footer>RE-ENTRY uses completed-close data and reevaluates after every market session. Historical evidence supports decision timing, not guaranteed returns. Sector/subsector repair candidates are supporting evidence unless separately validated as standalone entry rules.</footer>
    </main>
  );
}
