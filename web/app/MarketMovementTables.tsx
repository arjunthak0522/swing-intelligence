"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, Radio } from "lucide-react";

type SubsectorProxy = {
  label: string;
  parent_sector: string;
  drawdown_20d: number;
  drawdown_60d: number;
  return_5d: number;
  relative_strength_20d_vs_spy: number;
  relative_strength_20d_vs_parent: number;
  repairing: boolean;
};

type Snapshot = {
  signal_snapshot?: { sectors?: Record<string, { drawdown_20d: number }> };
  subsector_intelligence?: {
    by_sector?: Record<string, { damage_share_3pct?: number; repair_share?: number }>;
    proxies?: Record<string, SubsectorProxy>;
  };
};

type LiveSnapshot = { quotes: Record<string, { change_pct: number | null }> };

type WashoutSnapshot = {
  state?: string;
  candidate_action?: string;
  turn_family_count?: number;
  generated_at_utc?: string;
  daily_context_state?: string;
  families?: Record<string, boolean>;
  values?: {
    timestamp_et?: string;
    SPXA20R?: number | null;
    NYMO?: number | null;
    NAMO?: number | null;
    NYUD?: number | null;
    NAUD?: number | null;
    nyse_down_up_ratio?: number | null;
    nasdaq_down_up_ratio?: number | null;
  };
};

const sectorNames: Record<string, string> = {
  XLC: "Communication Services", XLY: "Consumer Discretionary", XLP: "Consumer Staples",
  XLE: "Energy", XLF: "Financials", XLV: "Health Care", XLI: "Industrials",
  XLB: "Materials", XLRE: "Real Estate", XLK: "Technology", XLU: "Utilities",
};

type SortDirection = "desc" | "asc";
type SectorSort = "today" | "drawdown" | "status";
type SubsectorSort = "today" | "fiveDay" | "drawdown" | "status";

const pct = (value?: number | null, digits = 1) => typeof value === "number" && Number.isFinite(value)
  ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
  : "-";

function subsectorState(x: SubsectorProxy) {
  if (x.repairing) return { label: "REPAIRING", dot: "repair", cls: "good-text", rank: 4 };
  if (x.drawdown_20d <= -0.05) return { label: "DEEP CORRECTION", dot: "damage", cls: "bad-text", rank: 0 };
  if (x.drawdown_20d <= -0.03) return { label: "DAMAGED", dot: "damage", cls: "muted", rank: 1 };
  if (x.drawdown_20d <= -0.02) return { label: "RESET", dot: "reset", cls: "muted", rank: 2 };
  return { label: "NEUTRAL", dot: "neutral", cls: "muted", rank: 3 };
}

function numeric(value: number | null | undefined, fallback = Number.NEGATIVE_INFINITY) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function washoutClass(state?: string) {
  const value = (state || "").toUpperCase();
  if (value === "WASHOUT") return "good-text";
  if (value === "WASHOUT_WATCH") return "warn";
  if (value === "OVERSOLD") return "bad-text";
  return "muted";
}

function washoutLabel(state?: string) {
  const value = (state || "").toUpperCase();
  if (value === "WASHOUT") return "GO EARLY";
  if (value === "WASHOUT_WATCH") return "WATCH";
  if (value === "OVERSOLD") return "WAIT";
  return value || "UNAVAILABLE";
}

function SortButton({ active, direction, children, onClick }: { active: boolean; direction: SortDirection; children: ReactNode; onClick: () => void }) {
  return <button type="button" className={`sort-chip${active ? " active" : ""}`} onClick={onClick}>{children}{active ? <ChevronDown size={12} className={direction === "asc" ? "sort-up" : ""} /> : null}</button>;
}

export default function MarketMovementTables({ snapshot, live }: { snapshot: Snapshot; live: LiveSnapshot | null }) {
  const [sectorSort, setSectorSort] = useState<SectorSort>("today");
  const [sectorDirection, setSectorDirection] = useState<SortDirection>("desc");
  const [subsectorSort, setSubsectorSort] = useState<SubsectorSort>("today");
  const [subsectorDirection, setSubsectorDirection] = useState<SortDirection>("desc");
  const [washout, setWashout] = useState<WashoutSnapshot | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const url = `https://raw.githubusercontent.com/arjunthak0522/swing-intelligence/intraday-signal-research/data/reentry/exhaustion_intraday_current.json?t=${Date.now()}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (active) setWashout(data);
      } catch {
        if (active) setWashout(null);
      }
    };
    load();
    const timer = window.setInterval(load, 60_000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const toggleSectorSort = (next: SectorSort) => {
    if (next === sectorSort) setSectorDirection((d) => d === "desc" ? "asc" : "desc");
    else { setSectorSort(next); setSectorDirection(next === "drawdown" ? "asc" : "desc"); }
  };
  const toggleSubsectorSort = (next: SubsectorSort) => {
    if (next === subsectorSort) setSubsectorDirection((d) => d === "desc" ? "asc" : "desc");
    else { setSubsectorSort(next); setSubsectorDirection(next === "drawdown" ? "asc" : "desc"); }
  };

  const sectors = useMemo(() => Object.entries(snapshot.signal_snapshot?.sectors || {}).map(([symbol, x]) => {
    const group = snapshot.subsector_intelligence?.by_sector?.[symbol];
    const repairing = (group?.repair_share || 0) > 0;
    return { symbol, label: sectorNames[symbol] || symbol, today: live?.quotes?.[symbol]?.change_pct ?? null, drawdown: x.drawdown_20d, damageShare: group?.damage_share_3pct ?? null, repairing };
  }).sort((a, b) => {
    let av = 0; let bv = 0;
    if (sectorSort === "today") { av = numeric(a.today); bv = numeric(b.today); }
    else if (sectorSort === "drawdown") { av = a.drawdown; bv = b.drawdown; }
    else { av = a.repairing ? 1 : 0; bv = b.repairing ? 1 : 0; }
    return sectorDirection === "desc" ? bv - av : av - bv;
  }), [snapshot, live, sectorSort, sectorDirection]);

  const subsectors = useMemo(() => Object.entries(snapshot.subsector_intelligence?.proxies || {}).map(([symbol, x]) => {
    const state = subsectorState(x);
    return { symbol, x, state, today: live?.quotes?.[symbol]?.change_pct ?? null };
  }).sort((a, b) => {
    let av = 0; let bv = 0;
    if (subsectorSort === "today") { av = numeric(a.today); bv = numeric(b.today); }
    else if (subsectorSort === "fiveDay") { av = a.x.return_5d; bv = b.x.return_5d; }
    else if (subsectorSort === "drawdown") { av = a.x.drawdown_20d; bv = b.x.drawdown_20d; }
    else { av = a.state.rank; bv = b.state.rank; }
    return subsectorDirection === "desc" ? bv - av : av - bv;
  }), [snapshot, live, subsectorSort, subsectorDirection]);

  const washoutTime = washout?.values?.timestamp_et
    ? new Date(washout.values.timestamp_et).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit", timeZoneName: "short" })
    : "Awaiting first valid session snapshot";
  const familyEntries = Object.entries(washout?.families || {});

  return <>
    <section className="card section-card live-card">
      <div className="section-heading">
        <div><span className="kicker">INTRADAY WASHOUT · SHADOW TEST</span><h2>Is the selling impulse starting to reverse?</h2></div>
        <span className={`pill ${washoutClass(washout?.state)}`}>{washoutLabel(washout?.state)}</span>
      </div>
      <p className="section-intro">Research signal only. It updates from the live intraday exhaustion study and does not overwrite the official completed-close RE-ENTRY decision.</p>
      {washout ? <>
        <div className="live-grid">
          <div className="live-stat"><small>State</small><strong className={washoutClass(washout.state)}>{washout.state || "-"}</strong><span>{washout.candidate_action || "-"}</span></div>
          <div className="live-stat"><small>Independent turns</small><strong>{washout.turn_family_count ?? 0}</strong><span>2+ = intraday WASHOUT</span></div>
          <div className="live-stat"><small>S&amp;P breadth</small><strong>{washout.values?.SPXA20R?.toFixed?.(1) ?? "-"}</strong><span>% above 20D avg</span></div>
          <div className="live-stat"><small>NYSE down/up volume</small><strong>{washout.values?.nyse_down_up_ratio?.toFixed?.(2) ?? "-"}x</strong><span>Selling pressure</span></div>
          <div className="live-stat"><small>Nasdaq down/up volume</small><strong>{washout.values?.nasdaq_down_up_ratio?.toFixed?.(2) ?? "-"}x</strong><span>Selling pressure</span></div>
          <div className="live-stat"><small>Last update</small><strong>{washoutTime}</strong><span>30-minute research snapshots</span></div>
        </div>
        <div className="notice"><Radio size={14} /> {familyEntries.length ? familyEntries.map(([name, on]) => `${name.replaceAll("_", " ")}: ${on ? "TURN" : "no turn"}`).join(" · ") : "Awaiting family-level turn data."}</div>
      </> : <div className="notice">Intraday WASHOUT research feed is temporarily unavailable. The official completed-close signal remains authoritative.</div>}
    </section>

    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">ALL 11 SECTORS</span><h2>Sector Daily Moves &amp; Repair</h2></div><span className="pill">{sectors.length}/11 loaded</span></div>
      <p className="section-intro">Today&apos;s movement first, with pullback and repair context beside it. The default view ranks the strongest sectors today from top to bottom.</p>
      <div className="sort-bar" aria-label="Sort sectors"><span>Sort by</span><SortButton active={sectorSort === "today"} direction={sectorDirection} onClick={() => toggleSectorSort("today")}>Today</SortButton><SortButton active={sectorSort === "drawdown"} direction={sectorDirection} onClick={() => toggleSectorSort("drawdown")}>Below 20D high</SortButton><SortButton active={sectorSort === "status"} direction={sectorDirection} onClick={() => toggleSectorSort("status")}>Repair status</SortButton></div>
      <div className="sector-table movement-table">
        <div className="sector-table-head sector-move-head"><span>Sector</span><span>Today</span><span>Below 20D high</span><span>Subsectors 3%+ down</span><span>Status</span></div>
        {sectors.map((row) => <div className="sector-table-row sector-move-row" key={row.symbol}><div><b>{row.label}</b><small>{row.symbol}</small></div><strong className={numeric(row.today, 0) > 0 ? "good-text" : numeric(row.today, 0) < 0 ? "bad-text" : "muted"}>{pct(row.today)}</strong><span>{pct(row.drawdown)}</span><span>{pct(row.damageShare)}</span><span className={row.repairing ? "good-text" : "muted"}>{row.repairing ? "Repairing" : "No broad repair"}</span></div>)}
      </div>
      <div className="notice">Sector 5-day return is not currently published by the validated close snapshot, so it is intentionally not shown rather than inferred.</div>
    </section>

    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">ALL SUBSECTORS</span><h2>Subsector Daily Moves &amp; Repair</h2></div><span className="pill">{subsectors.length} tracked</span></div>
      <p className="section-intro">Today&apos;s movement first, with the 5-day move and recent pullback immediately beside it. Every tracked subsector remains visible.</p>
      <div className="sort-bar" aria-label="Sort subsectors"><span>Sort by</span><SortButton active={subsectorSort === "today"} direction={subsectorDirection} onClick={() => toggleSubsectorSort("today")}>Today</SortButton><SortButton active={subsectorSort === "fiveDay"} direction={subsectorDirection} onClick={() => toggleSubsectorSort("fiveDay")}>5D</SortButton><SortButton active={subsectorSort === "drawdown"} direction={subsectorDirection} onClick={() => toggleSubsectorSort("drawdown")}>Below 20D high</SortButton><SortButton active={subsectorSort === "status"} direction={subsectorDirection} onClick={() => toggleSubsectorSort("status")}>Status</SortButton></div>
      <div className="subsector-head"><span>Subsector</span><span>Today</span><span>5D</span><span>Below 20D high</span><span>Status</span><span></span></div>
      <div className="internal-list">
        {subsectors.map(({ symbol, x, state, today }) => <details key={symbol} className="internal-row movement-row"><summary><div className="name-wrap"><span className="state-dot" data-state={state.dot} /><div><b>{x.label} <span>({symbol})</span></b><small>{sectorNames[x.parent_sector] || x.parent_sector}</small></div></div><div className="movement-metrics"><strong className={numeric(today, 0) > 0 ? "good-text" : numeric(today, 0) < 0 ? "bad-text" : "muted"}>{pct(today)}</strong><span>{pct(x.return_5d)}</span><span>{pct(x.drawdown_20d)}</span><b className={state.cls}>{state.label}</b><ChevronRight size={17} /></div></summary><div className="detail-grid"><span>Today <b>{pct(today)}</b></span><span>5D return <b>{pct(x.return_5d)}</b></span><span>Below 20D high <b>{pct(x.drawdown_20d)}</b></span><span>Below 60D high <b>{pct(x.drawdown_60d)}</b></span><span>vs SPY 20D <b>{pct(x.relative_strength_20d_vs_spy)}</b></span><span>vs {x.parent_sector} 20D <b>{pct(x.relative_strength_20d_vs_parent)}</b></span></div><p className="detail-copy">{x.repairing ? `${x.label} is repairing after a meaningful reset. This is constructive context, not an independent re-entry trigger.` : state.label === "NEUTRAL" ? `${x.label} is not materially damaged on the 20-day measure and is not currently in repair mode.` : `${x.label} remains in a reset or correction. The engine tracks whether this weakness begins to stabilize and broaden into repair.`}</p></details>)}
      </div>
    </section>
  </>;
}
