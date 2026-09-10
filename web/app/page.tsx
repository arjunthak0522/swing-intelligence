import { AlertTriangle, CheckCircle2, Clock3, Database, Radio } from "lucide-react";
import {
  decisionLabel,
  getUnifiedSnapshot,
  num,
  pct,
  phaseLabel,
  type UnifiedSnapshot,
} from "../lib/unifiedReentry";
import "./unified-dashboard.css";

export const dynamic = "force-dynamic";

function decisionClass(value?: string | null) {
  if (value === "GO_EARLY") return "u-good";
  if (value === "WATCH") return "u-warn";
  if (value === "WAIT") return "u-neutral";
  return "u-bad";
}

function qualityClass(value?: string | null) {
  if (value === "OK") return "ok";
  if (value === "PARTIAL") return "partial";
  return "degraded";
}

function formatTimestamp(value?: string | null) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function explanation(snapshot: UnifiedSnapshot) {
  const u = snapshot.unified_engine;
  if (!u) return "The unified decision is unavailable.";
  if (u.decision === "GO_EARLY") {
    return `The market is in an oversold setup and reversal evidence has crossed the early re-entry threshold with ${u.fast_family_count} fast turn${u.fast_family_count === 1 ? "" : "s"} and ${u.context_support_count} context turn${u.context_support_count === 1 ? "" : "s"}.`;
  }
  if (u.decision === "WATCH") {
    return `The market is oversold and reversal evidence is developing, but it has not yet crossed the GO EARLY threshold. Current evidence: ${u.fast_family_count} fast turn${u.fast_family_count === 1 ? "" : "s"} and ${u.context_support_count} context turn${u.context_support_count === 1 ? "" : "s"}.`;
  }
  if (u.oversold_gate) {
    return `The market is oversold, but reversal evidence is not strong enough yet. Current evidence: ${u.fast_family_count} fast turns and ${u.context_support_count} context turns.`;
  }
  return "The market is not currently inside the unified engine's oversold setup gate, so RE-ENTRY remains at WAIT.";
}

function FamilyPill({ active, label }: { active: boolean; label: string }) {
  return <span className={`u-pill ${active ? "on" : "off"}`}>{active ? "TURNING" : "NOT TURNING"} - {label}</span>;
}

function IndicatorRow({
  name,
  family,
  value,
  active,
  note,
}: {
  name: string;
  family: string;
  value: string;
  active: boolean;
  note: string;
}) {
  return (
    <div className="u-indicator-row">
      <div className="u-indicator-name"><strong>{name}</strong><small>{family}</small></div>
      <div className="u-indicator-value">{value}</div>
      <FamilyPill active={active} label={active ? "supporting" : "inactive"} />
      <div className="u-indicator-note">{note}</div>
    </div>
  );
}

function DecisionHero({ snapshot }: { snapshot: UnifiedSnapshot }) {
  const u = snapshot.unified_engine!;
  const q = snapshot.data_quality;
  const degraded = q?.status === "DEGRADED";
  return (
    <section className="u-card">
      <div className="u-hero-top">
        <div><span className="u-kicker">RE-ENTRY DECISION</span></div>
        <span className="u-phase"><Clock3 size={14} /> {phaseLabel(u.market_phase)} - {formatTimestamp(u.timestamp_et)}</span>
      </div>
      <div className={`u-decision ${degraded ? "u-bad" : decisionClass(u.decision)}`}>
        {degraded ? "DATA DEGRADED" : decisionLabel(u.decision)}
      </div>
      <p className="u-hero-copy">
        {degraded
          ? "One or more required data families are incomplete. The underlying REENTRY_UNIFIED_v1 calculation is preserved for audit, but this snapshot should not be treated as actionable until data quality recovers."
          : explanation(snapshot)}
      </p>
      <div className="u-score-grid">
        <div className="u-score"><small>Oversold setup</small><strong>{u.oversold_gate ? "YES" : "NO"}</strong></div>
        <div className="u-score"><small>Fast reversal families</small><strong>{u.fast_family_count}/4</strong></div>
        <div className="u-score"><small>Context families</small><strong>{u.context_support_count}/4</strong></div>
      </div>
    </section>
  );
}

function MarketContext({ snapshot }: { snapshot: UnifiedSnapshot }) {
  const prices = snapshot.market_prices || {};
  const rows = [
    ["SPY", "S&P 500 ETF"],
    ["QQQ", "Nasdaq 100 ETF"],
    ["^VIX", "VIX"],
  ] as const;
  return (
    <section className="u-card">
      <div className="u-section-heading">
        <div><span className="u-kicker">MARKET CONTEXT</span><h2>Current market move</h2></div>
        <span className="u-phase"><Radio size={14} /> Display context only - not a decision input</span>
      </div>
      <div className="u-market-grid">
        {rows.map(([symbol, label]) => {
          const row = prices[symbol];
          return (
            <div className="u-market-stat" key={symbol}>
              <small>{label}</small>
              <strong>{row?.price != null ? num(row.price, 2) : "-"}</strong>
              <span>{pct(row?.change_pct, 2)} vs prior close</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function IndicatorMatrix({ snapshot }: { snapshot: UnifiedSnapshot }) {
  const v = snapshot.values || {};
  const f = snapshot.families || {};
  const c = snapshot.unified_engine?.context_support || {
    MMFD_IMPROVING: false,
    NASI_TURNING_UP: false,
    VVIX_EASING: false,
    SKEW_NARROWING: false,
  };

  return (
    <section className="u-card">
      <div className="u-section-heading">
        <div><span className="u-kicker">WHAT THE ENGINE SEES</span><h2>All 8 decision families</h2></div>
        <span className="u-phase"><Database size={14} /> One unified rule</span>
      </div>
      <p className="u-section-intro">These are the exact fast and context families used by REENTRY_UNIFIED_v1. No analog vote, legacy completed-close strategy, or separate intraday trading rule is shown here.</p>
      <div className="u-indicator-table">
        <IndicatorRow
          name="Fast breadth"
          family="FAST 1 OF 4"
          value={v.SPXA20R != null ? `${num(v.SPXA20R, 1)}% above 20DMA` : "-"}
          active={Boolean(f.fast_breadth_turn)}
          note="Turns on when S&P 500 short-term breadth improves versus the preceding same-session snapshot."
        />
        <IndicatorRow
          name="Breadth momentum"
          family="FAST 2 OF 4"
          value={`NYMO ${num(v.NYMO, 1)} / NAMO ${num(v.NAMO, 1)}`}
          active={Boolean(f.momentum_turn)}
          note="Turns on when either NYMO or NAMO improves versus the preceding same-session snapshot."
        />
        <IndicatorRow
          name="A/D volume"
          family="FAST 3 OF 4"
          value={`NYSE ${num(v.NYUD, 0)} / Nasdaq ${num(v.NAUD, 0)}`}
          active={Boolean(f.net_volume_turn)}
          note="Turns on when net advance-decline volume improves on either exchange."
        />
        <IndicatorRow
          name="Down/up volume relief"
          family="FAST 4 OF 4"
          value={`NYSE ${num(v.nyse_down_up_ratio, 2)}x / Nasdaq ${num(v.nasdaq_down_up_ratio, 2)}x`}
          active={Boolean(f.down_up_ratio_relief)}
          note="Turns on when either down/up volume ratio improves by more than 15% versus the preceding same-session snapshot."
        />
        <IndicatorRow
          name="MMFD"
          family="CONTEXT 1 OF 4"
          value={v.MMFD != null ? `${num(v.MMFD, 1)}% above live 5DMA` : "-"}
          active={Boolean(c.MMFD_IMPROVING)}
          note={`Internal all-stock breadth calculation. Coverage ${snapshot.data_quality?.mmfd_coverage_pct != null ? `${num(snapshot.data_quality.mmfd_coverage_pct, 1)}%` : "unavailable"}.`}
        />
        <IndicatorRow
          name="NASI+"
          family="CONTEXT 2 OF 4"
          value={`${num(v.NASI_RSI, 1)} - ${v.NASI_DIRECTION || "UNAVAILABLE"}`}
          active={Boolean(c.NASI_TURNING_UP)}
          note="Internal ratio-adjusted McClellan Summation Index RSI. Research is separately checking bootstrap stability."
        />
        <IndicatorRow
          name="VVIX"
          family="CONTEXT 3 OF 4"
          value={`${num(v.VVIX, 1)} - ${v.VVIX_DIRECTION || "UNAVAILABLE"}`}
          active={Boolean(c.VVIX_EASING)}
          note={`Volatility-of-volatility context. Two-year percentile ${v.VVIX_PERCENTILE_2Y != null ? `${num(v.VVIX_PERCENTILE_2Y, 1)}%` : "unavailable"}.`}
        />
        <IndicatorRow
          name="SPX downside skew"
          family="CONTEXT 4 OF 4"
          value={`${num(v.SKEW_LIVE_PROXY, 2)} vol pts - ${v.SKEW_DIRECTION || "UNAVAILABLE"}`}
          active={Boolean(c.SKEW_NARROWING)}
          note="Live 25-delta SPX put IV minus call IV proxy. Post-close fallback preserves only the last valid same-session proxy."
        />
      </div>
    </section>
  );
}

function DataQuality({ snapshot }: { snapshot: UnifiedSnapshot }) {
  const q = snapshot.data_quality;
  const problems = [...(q?.issues || []), ...(q?.warnings || [])];
  return (
    <section className="u-card">
      <div className="u-quality-top">
        <div><span className="u-kicker">DATA RELIABILITY</span><h2>Can this snapshot be trusted?</h2></div>
        <span className={`u-quality-pill ${qualityClass(q?.status)}`}>
          {q?.status === "OK" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
          {q?.status || "UNAVAILABLE"}
        </span>
      </div>
      {problems.length ? (
        <ul className="u-quality-list">{problems.map((x) => <li key={x}>{x}</li>)}</ul>
      ) : (
        <p className="u-quality-clear">All required decision families are present and the current hard coverage checks passed.</p>
      )}
      {snapshot.market_price_errors?.length ? (
        <ul className="u-quality-list">{snapshot.market_price_errors.map((x) => <li key={x}>Display-only price context: {x}</li>)}</ul>
      ) : null}
    </section>
  );
}

function ProspectiveEvidence({ snapshot }: { snapshot: UnifiedSnapshot }) {
  const h = snapshot.prospective_history;
  return (
    <section className="u-card">
      <div className="u-section-heading">
        <div><span className="u-kicker">PROSPECTIVE VALIDATION</span><h2>Evidence being captured now</h2></div>
      </div>
      <p className="u-section-intro">This is live point-in-time evidence for the new unified engine. It is intentionally kept separate from historical statistics generated by the retired model.</p>
      <div className="u-history-grid">
        <div className="u-history-stat"><small>Snapshots</small><strong>{h?.snapshot_count ?? 0}</strong><span>actual captured states</span></div>
        <div className="u-history-stat"><small>Market days</small><strong>{h?.market_days ?? 0}</strong><span>with unified evidence</span></div>
        <div className="u-history-stat"><small>State transitions</small><strong>{h?.state_transitions ?? 0}</strong><span>same-day flips</span></div>
        <div className="u-history-stat"><small>GO EARLY</small><strong>{h?.go_early_snapshots ?? 0}</strong><span>captured snapshots</span></div>
        <div className="u-history-stat"><small>WATCH</small><strong>{h?.watch_snapshots ?? 0}</strong><span>captured snapshots</span></div>
      </div>
      <div className="u-research-note">Whipsaw and persistence variants are being measured in shadow research only. No confirmation delay, hysteresis rule, or CPCE threshold has been promoted into the live decision.</div>
    </section>
  );
}

function Sources({ snapshot }: { snapshot: UnifiedSnapshot }) {
  const sources = snapshot.sources || {};
  return (
    <section className="u-card">
      <div className="u-section-heading"><div><span className="u-kicker">PROVENANCE</span><h2>Where each family comes from</h2></div></div>
      <div className="u-source-grid">
        {Object.entries(sources).map(([key, row]) => (
          <div className="u-source" key={key}>
            <strong>{key.replaceAll("_", " ")}</strong>
            <small>{row.provider || "Source unavailable"}</small>
            <small>{row.timestamp ? `Observed ${formatTimestamp(row.timestamp)}` : "Source timestamp not separately available"}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

export default async function Page() {
  const snapshot = await getUnifiedSnapshot();
  if (!snapshot?.unified_engine) {
    return (
      <main className="unified-shell">
        <div className="u-unavailable">
          <h1>RE-ENTRY unavailable</h1>
          <p>The unified snapshot could not be loaded. No legacy decision is substituted.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="unified-shell">
      <header className="unified-header">
        <div className="unified-brand">RE-ENTRY</div>
        <div className="unified-purpose">After a market pullback, should you keep waiting or begin putting cash back into SPY/QQQ? One engine answers that question during the session and after the close.</div>
      </header>
      <DecisionHero snapshot={snapshot} />
      <MarketContext snapshot={snapshot} />
      <IndicatorMatrix snapshot={snapshot} />
      <DataQuality snapshot={snapshot} />
      <ProspectiveEvidence snapshot={snapshot} />
      <Sources snapshot={snapshot} />
    </main>
  );
}
