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
    MMFD?: number | null;
    MMFD_STATE?: string | null;
    VVIX?: number | null;
    VVIX_STATE?: string | null;
    VVIX_PERCENTILE_2Y?: number | null;
    VVIX_DIRECTION?: string | null;
    SKEW_LIVE_PROXY?: number | null;
    SKEW_LIVE_PROXY_RATIO?: number | null;
    SKEW_DIRECTION?: string | null;
    SKEW_OFFICIAL_CLOSE?: number | null;
    SKEW_OFFICIAL_PERCENTILE_2Y?: number | null;
    NYMO?: number | null;
    NAMO?: number | null;
    NYUD?: number | null;
    NAUD?: number | null;
    nyse_down_up_ratio?: number | null;
    nasdaq_down_up_ratio?: number | null;
    NASI_RSI?: number | null;
    NASI_EMA4?: number | null;
    NASI_EMA10?: number | null;
    NASI_DIRECTION?: string | null;
  };
  mmfd_live?: {
    universe_size?: number;
    valid_5d_observations?: number;
    coverage_pct?: number;
    above_5dma_count?: number;
  };
  vvix_live?: {
    value?: number;
    prior_close?: number;
    change_points_vs_prior_close?: number;
    direction_vs_prior_close?: string;
    historical_percentile_2y?: number;
    completed_history_sessions?: number;
    state?: string;
  };
  unified_engine?: {
    engine_version?: string;
    primary_engine?: boolean;
    oversold_gate?: boolean;
    fast_family_count?: number;
    context_support_count?: number;
    context_support?: Record<string, boolean>;
    state?: string;
    decision?: string;
    logic?: string;
    market_phase?: string;
    timestamp_et?: string;
    market_date?: string;
  };
};

const sectorNames: Record<string, string> = {
  XLC: "Communication Services", XLY: "Consumer Discretionary", XLP: "Consumer Staples",
  XLE: "Energy", XLF: "Financials", XLV: "Health Care", XLI: "Industrials",
  XLB: "Materials", XLRE: "Real Estate", XLK: "Technology", XLU: "Utilities",
};

const familyNames: Record<string, string> = {
  fast_breadth_turn: "Fast breadth",
  momentum_turn: "Momentum",
  net_volume_turn: "A/D volume",
  down_up_ratio_relief: "Selling intensity",
};

type SortDirection = "desc" | "asc";
type SectorSort = "today" | "drawdown" | "status";
type SubsectorSort = "today" | "fiveDay" | "drawdown" | "status";

const pct = (value?: number | null, digits = 1) => typeof value === "number" && Number.isFinite(value)
  ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
  : "-";

const levelPct = (value?: number | null, digits = 0) => typeof value === "number" && Number.isFinite(value)
  ? `${(value * 100).toFixed(digits)}%`
  : "-";

const signed = (value?: number | null, digits = 1) => typeof value === "number" && Number.isFinite(value)
  ? `${value > 0 ? "+" : ""}${value.toFixed(digits)}`
  : "-";

const plain = (value?: number | null, digits = 1) => typeof value === "number" && Number.isFinite(value)
  ? value.toFixed(digits)
  : "-";

const finite = (value?: number | null) => typeof value === "number" && Number.isFinite(value);
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const position = (value: number | null | undefined, min: number, max: number) => finite(value)
  ? clamp(((Number(value) - min) / (max - min)) * 100, 0, 100)
  : null;

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

function washoutConclusion(state?: string) {
  const value = (state || "").toUpperCase();
  if (value === "WASHOUT") return "Two or more independent fast families have turned. The first credible internal reversal is underway.";
  if (value === "WASHOUT_WATCH") return "An early internal turn is developing, but only one independent family has reversed so far.";
  if (value === "OVERSOLD") return "Selling remains stretched and is not yet reversing across the fast internal families.";
  return "Waiting for a valid regular-session washout observation.";
}

function unifiedClass(state?: string) {
  const value = (state || "").toUpperCase();
  if (value === "GO_EARLY") return "good-text";
  if (value === "WATCH") return "warn";
  if (value === "WAIT") return "bad-text";
  return "muted";
}

function unifiedLabel(state?: string) {
  const value = (state || "").toUpperCase();
  if (value === "GO_EARLY") return "GO EARLY";
  if (value === "WATCH") return "WATCH";
  if (value === "WAIT") return "WAIT";
  return value || "UNAVAILABLE";
}

function unifiedConclusion(x?: WashoutSnapshot["unified_engine"]) {
  if (!x) return null;
  const fast = x.fast_family_count ?? 0;
  const context = x.context_support_count ?? 0;
  if ((x.state || "").toUpperCase() === "GO_EARLY") {
    if (fast >= 2) return `GO EARLY: ${fast} fast reversal families have turned.`;
    return `GO EARLY: ${fast} fast reversal family plus ${context} independent context turn${context === 1 ? "" : "s"}.`;
  }
  if ((x.state || "").toUpperCase() === "WATCH") return `WATCH: ${fast} fast reversal families and ${context} context turns are supportive, but the unified rule is not fully triggered.`;
  return "WAIT: the market may be oversold, but the unified reversal evidence has not turned enough yet.";
}

function breadthState(value?: number | null) {
  if (!finite(value)) return { label: "UNAVAILABLE", cls: "muted", note: "Waiting for breadth data." };
  if (Number(value) < 10) return { label: "EXTREME OVERSOLD", cls: "bad-text", note: "Fewer than 1 in 10 stocks are above their 20-day average." };
  if (Number(value) < 30) return { label: "OVERSOLD", cls: "bad-text", note: "Participation is deeply weak." };
  if (Number(value) < 50) return { label: "WEAK", cls: "warn", note: "Below neutral participation." };
  if (Number(value) < 70) return { label: "NORMAL / BROAD", cls: "muted", note: "Breadth is in a normal-to-healthy zone." };
  return { label: "STRONG", cls: "good-text", note: "Broad participation is strong." };
}

function mmfdState(value?: number | null) {
  if (!finite(value)) return { label: "UNAVAILABLE", cls: "muted", note: "Waiting for live 5-day breadth calculation." };
  if (Number(value) < 15) return { label: "EXTREME OVERSOLD", cls: "bad-text", note: "Fewer than 15% of U.S. stocks are above their own 5-day average." };
  if (Number(value) < 30) return { label: "OVERSOLD", cls: "bad-text", note: "Short-term breadth is broadly washed out." };
  if (Number(value) < 50) return { label: "WEAK", cls: "warn", note: "Fewer than half of stocks are above their 5-day average." };
  if (Number(value) <= 70) return { label: "NORMAL", cls: "muted", note: "Short-term participation is around a normal range." };
  if (Number(value) <= 85) return { label: "STRONG", cls: "good-text", note: "Short-term participation is broadly strong." };
  return { label: "EXTREME OVERBOUGHT", cls: "good-text", note: "More than 85% of stocks are above their 5-day average." };
}

function vvixState(percentile?: number | null, direction?: string | null) {
  if (!finite(percentile)) return { label: "UNAVAILABLE", cls: "muted", note: "Waiting for live volatility-of-volatility data." };
  const dir = (direction || "").toUpperCase();
  const suffix = dir === "RISING" ? " and rising" : dir === "FALLING" ? " and falling" : "";
  if (Number(percentile) >= 95) return { label: "EXTREME STRESS", cls: "bad-text", note: `VVIX is above 95% of its last two years${suffix}.` };
  if (Number(percentile) >= 80) return { label: "HIGH STRESS", cls: "bad-text", note: `VVIX is in the top 20% of its two-year range${suffix}.` };
  if (Number(percentile) >= 60) return { label: "ELEVATED", cls: "warn", note: `Volatility stress is above normal${suffix}.` };
  if (Number(percentile) >= 20) return { label: "NORMAL", cls: "muted", note: `Volatility-of-volatility is in a normal historical zone${suffix}.` };
  return { label: "CALM", cls: "good-text", note: `Volatility-of-volatility is unusually subdued${suffix}.` };
}

function skewState(percentile?: number | null, direction?: string | null) {
  if (!finite(percentile)) return { label: "UNAVAILABLE", cls: "muted", note: "Waiting for SPX tail-risk context." };
  const dir = (direction || "").toUpperCase();
  const live = dir === "WIDENING" ? " Live downside skew is widening." : dir === "NARROWING" ? " Live downside skew is narrowing." : dir === "FLAT" ? " Live downside skew is roughly unchanged." : "";
  if (Number(percentile) >= 95) return { label: "EXTREME TAIL RISK", cls: "bad-text", note: `Official SKEW is above 95% of its two-year history.${live}` };
  if (Number(percentile) >= 80) return { label: "HIGH TAIL RISK", cls: "bad-text", note: `Official SKEW is in the top 20% of its two-year history.${live}` };
  if (Number(percentile) >= 60) return { label: "ELEVATED", cls: "warn", note: `Tail-risk pricing is above normal.${live}` };
  if (Number(percentile) >= 20) return { label: "NORMAL", cls: "muted", note: `Tail-risk pricing is in a normal historical zone.${live}` };
  return { label: "LOW TAIL RISK", cls: "good-text", note: `Tail-risk pricing is unusually subdued.${live}` };
}

function momentumState(value?: number | null) {
  if (!finite(value)) return { label: "UNAVAILABLE", cls: "muted", note: "Waiting for oscillator data." };
  if (Number(value) <= -100) return { label: "OVERSOLD / EXTREME NEGATIVE", cls: "bad-text", note: "Breadth momentum is below the commonly used -100 oversold area." };
  if (Number(value) < 0) return { label: "NEGATIVE", cls: "warn", note: "Breadth momentum is below the zero line, but not at the -100 oversold area." };
  if (Number(value) < 100) return { label: "POSITIVE", cls: "good-text", note: "Breadth momentum is above the zero line." };
  return { label: "OVERBOUGHT / EXTREME POSITIVE", cls: "good-text", note: "Breadth momentum is above the commonly used +100 extreme-positive area." };
}

function adVolumeState(value?: number | null) {
  if (!finite(value)) return { label: "UNAVAILABLE", cls: "muted", note: "Waiting for A/D volume data." };
  if (Number(value) < 0) return { label: "DECLINING VOLUME LEADS", cls: "bad-text", note: "Net A/D volume is negative. Magnitude is shown without arbitrary fixed cutoffs." };
  if (Number(value) > 0) return { label: "ADVANCING VOLUME LEADS", cls: "good-text", note: "Net A/D volume is positive. Magnitude is shown without arbitrary fixed cutoffs." };
  return { label: "BALANCED", cls: "muted", note: "Advancing and declining volume are balanced." };
}

function ratioState(value?: number | null) {
  if (!finite(value)) return { label: "UNAVAILABLE", cls: "muted", note: "Waiting for down/up volume data." };
  if (Number(value) > 1) return { label: "DOWN VOLUME LEADS", cls: "warn", note: `Down volume is ${Math.round((Number(value) - 1) * 100)}% greater than up volume.` };
  if (Number(value) < 1) return { label: "UP VOLUME LEADS", cls: "good-text", note: `Up volume exceeds down volume; the ratio is ${Number(value).toFixed(2)}x.` };
  return { label: "BALANCED", cls: "muted", note: "Down and up volume are equal at the 1.00x arithmetic balance point." };
}

function nasiState(value?: number | null, direction?: string | null) {
  if (!finite(value)) return { label: "UNAVAILABLE", cls: "muted", note: "Waiting for internally calculated NASI+." };
  const dir = (direction || "").toUpperCase();
  const suffix = dir === "RISING" ? " and rising" : dir === "FALLING" ? " and still falling" : "";
  if (Number(value) < 10) return { label: "EXTREME OVERSOLD", cls: "bad-text", note: `0-100 scale: below 10 is extreme oversold${suffix}.` };
  if (Number(value) < 30) return { label: "OVERSOLD", cls: "bad-text", note: `0-100 scale: below 30 is oversold${suffix}.` };
  if (Number(value) < 50) return { label: "WEAK", cls: "warn", note: `Below the 50 neutral area${suffix}.` };
  if (Number(value) < 70) return { label: "NORMAL / POSITIVE", cls: "muted", note: `Above the 50 neutral area${suffix}.` };
  return { label: "OVERBOUGHT / STRONG", cls: "good-text", note: `0-100 scale: above 70 is strong/overbought${suffix}.` };
}

function MetricStat({ label, value, state, reference, note, marker }: { label: string; value: string; state: { label: string; cls: string; note: string }; reference: string; note?: string; marker: number | null }) {
  return <div className="live-stat metric-stat">
    <small>{label}</small>
    <strong>{value}</strong>
    <b className={`metric-state ${state.cls}`}>{state.label}</b>
    <div className="metric-scale" aria-hidden="true">{marker !== null ? <i style={{ left: `${marker}%` }} /> : null}</div>
    <span className="metric-reference">{reference}</span>
    <span className="metric-meaning">{note || state.note}</span>
  </div>;
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
  const w = washout?.values;
  const unified = washout?.unified_engine;
  const decisionState = unified?.state || washout?.state;
  const decisionLabel = unified ? unifiedLabel(unified.state) : washoutLabel(washout?.state);
  const decisionClass = unified ? unifiedClass(unified.state) : washoutClass(washout?.state);
  const decisionConclusion = unifiedConclusion(unified) || washoutConclusion(washout?.state);
  const contextEntries = Object.entries(unified?.context_support || {});
  const contextNames: Record<string, string> = { MMFD_IMPROVING: "5-day breadth improving", NASI_TURNING_UP: "Nasdaq breadth turning up", VVIX_EASING: "volatility stress easing", SKEW_NARROWING: "tail-risk skew narrowing" };
  const mmfdCoverage = finite(washout?.mmfd_live?.coverage_pct) ? ` Coverage ${plain(washout?.mmfd_live?.coverage_pct, 1)}%.` : "";

  return <>
    <style>{`
      .washout-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .washout-grid .live-stat { border-left: 0; border-top: 1px solid var(--line); }
      .washout-grid .live-stat:nth-child(-n+3) { border-top: 0; }
      .washout-grid .live-stat:not(:nth-child(3n+1)) { border-left: 1px solid var(--line); }
      .metric-stat { padding: 17px 16px 16px; }
      .metric-stat .metric-state { display: block; margin: 1px 0 9px; font-size: 9px; letter-spacing: .05em; }
      .metric-scale { position: relative; height: 5px; border-radius: 999px; background: #ddd9cf; margin: 8px 0 7px; }
      .metric-scale i { position: absolute; top: -3px; width: 2px; height: 11px; border-radius: 2px; background: var(--ink); transform: translateX(-1px); }
      .metric-stat .metric-reference { font-size: 8px; line-height: 1.35; min-height: 22px; }
      .metric-stat .metric-meaning { margin-top: 6px; color: #454840; font-size: 9px; line-height: 1.4; }
      .warn { color: var(--amber); }
      @media (max-width: 760px) {
        .washout-grid { grid-template-columns: 1fr; }
        .washout-grid .live-stat, .washout-grid .live-stat:not(:nth-child(3n+1)) { border-left: 0; border-top: 1px solid var(--line); }
        .washout-grid .live-stat:first-child { border-top: 0; }
      }
    `}</style>
    <section className="card section-card live-card">
      <div className="section-heading">
        <div><span className="kicker">RE-ENTRY ENGINE</span><h2>Has waiting stopped helping?</h2></div>
        <span className={`pill ${decisionClass}`}>{decisionLabel}</span>
      </div>
      <p className="section-intro"><b>{decisionConclusion}</b> One engine uses the same reversal logic all day. During market hours readings are live/provisional; after the close the final session snapshot remains the decision until the next session.</p>
      {washout ? <>
        <div className="live-grid washout-grid">
          <MetricStat label="Unified RE-ENTRY evidence" value={`${unified?.fast_family_count ?? washout.turn_family_count ?? 0} fast + ${unified?.context_support_count ?? 0} context`} state={unified?.state === "GO_EARLY" ? { label: "GO EARLY", cls: "good-text", note: "Oversold conditions plus enough independent reversal evidence are present." } : unified?.state === "WATCH" ? { label: "WATCH", cls: "warn", note: "Some reversal evidence is present, but not enough for the unified early-entry rule." } : { label: "WAIT", cls: "bad-text", note: "Oversold conditions are not yet accompanied by enough reversal evidence." }} reference="GO = 2+ fast turns OR 1 fast turn + 1 independent context turn" marker={position((unified?.fast_family_count ?? washout.turn_family_count ?? 0) + (unified?.context_support_count ?? 0), 0, 4)} />
          <MetricStat label="Original fast reversal families" value={`${washout.turn_family_count ?? 0}/4`} state={(washout.turn_family_count ?? 0) >= 2 ? { label: "EARLY WASHOUT", cls: "good-text", note: "Two or more original fast families have turned." } : (washout.turn_family_count ?? 0) === 1 ? { label: "ONE TURN", cls: "warn", note: "One original fast family has turned." } : { label: "NO TURN YET", cls: "bad-text", note: "No original fast family has turned yet." }} reference="0 none · 1 partial turn · 2+ original early-WASHOUT path" marker={position(washout.turn_family_count ?? 0, 0, 4)} />
          <MetricStat label="S&P 500 above 20-day average (SPXA20R)" value={`${plain(w?.SPXA20R, 1)}%`} state={breadthState(w?.SPXA20R)} reference="<10 extreme · <30 oversold · ~50 neutral · >70 strong" marker={position(w?.SPXA20R, 0, 100)} />
          <MetricStat label="U.S. stocks above 5-day average (MMFD)" value={`${plain(w?.MMFD, 1)}%`} state={mmfdState(w?.MMFD)} reference="<15 extreme · <30 oversold · ~50 neutral · >70 strong · >85 extreme" note={`${mmfdState(w?.MMFD).note}${mmfdCoverage}`} marker={position(w?.MMFD, 0, 100)} />
          <MetricStat label="NYSE breadth momentum (NYMO)" value={signed(w?.NYMO, 1)} state={momentumState(w?.NYMO)} reference="<-100 oversold/extreme negative · 0 neutral · >+100 extreme positive" marker={position(w?.NYMO, -150, 150)} />
          <MetricStat label="Nasdaq breadth momentum (NAMO)" value={signed(w?.NAMO, 1)} state={momentumState(w?.NAMO)} reference="<-100 oversold/extreme negative · 0 neutral · >+100 extreme positive" marker={position(w?.NAMO, -150, 150)} />
          <MetricStat label="Nasdaq breadth summation RSI (NASI+)" value={plain(w?.NASI_RSI, 1)} state={nasiState(w?.NASI_RSI, w?.NASI_DIRECTION)} reference="<10 extreme · <30 oversold · 50 neutral · >70 strong" note={`${nasiState(w?.NASI_RSI, w?.NASI_DIRECTION).note}${finite(w?.NASI_EMA10) ? ` EMA10 ${plain(w?.NASI_EMA10, 1)}.` : ""}`} marker={position(w?.NASI_RSI, 0, 100)} />
          <MetricStat label="Volatility of VIX (VVIX)" value={plain(w?.VVIX, 1)} state={vvixState(w?.VVIX_PERCENTILE_2Y, w?.VVIX_DIRECTION)} reference="2Y percentile: <20 calm · 20-60 normal · 60-80 elevated · 80-95 high · 95+ extreme" note={`${vvixState(w?.VVIX_PERCENTILE_2Y, w?.VVIX_DIRECTION).note}${finite(w?.VVIX_PERCENTILE_2Y) ? ` ${plain(w?.VVIX_PERCENTILE_2Y, 0)}th percentile.` : ""}`} marker={position(w?.VVIX_PERCENTILE_2Y, 0, 100)} />
          <MetricStat label="S&P 500 tail-risk pricing (SKEW)" value={`${signed(w?.SKEW_LIVE_PROXY, 1)} vol pts`} state={skewState(w?.SKEW_OFFICIAL_PERCENTILE_2Y, w?.SKEW_DIRECTION)} reference="Live proxy = 25-delta SPX put IV minus call IV · higher/widening = more downside hedging" note={`${skewState(w?.SKEW_OFFICIAL_PERCENTILE_2Y, w?.SKEW_DIRECTION).note}${finite(w?.SKEW_OFFICIAL_CLOSE) ? ` Official SKEW close ${plain(w?.SKEW_OFFICIAL_CLOSE, 1)}.` : ""}${finite(w?.SKEW_OFFICIAL_PERCENTILE_2Y) ? ` ${plain(w?.SKEW_OFFICIAL_PERCENTILE_2Y, 0)}th percentile over 2Y.` : ""}`} marker={position(w?.SKEW_OFFICIAL_PERCENTILE_2Y, 0, 100)} />
          <MetricStat label="NYSE advance/decline volume" value={signed(w?.NYUD, 1)} state={adVolumeState(w?.NYUD)} reference="<0 declining volume leads · 0 balanced · >0 advancing volume leads" marker={null} />
          <MetricStat label="Nasdaq advance/decline volume" value={signed(w?.NAUD, 1)} state={adVolumeState(w?.NAUD)} reference="<0 declining volume leads · 0 balanced · >0 advancing volume leads" marker={null} />
          <MetricStat label="NYSE down/up volume ratio" value={`${plain(w?.nyse_down_up_ratio, 2)}x`} state={ratioState(w?.nyse_down_up_ratio)} reference="1.00x = exact arithmetic balance · >1 down volume leads · <1 up volume leads" marker={position(w?.nyse_down_up_ratio, 0, 3.5)} />
          <MetricStat label="Nasdaq down/up volume ratio" value={`${plain(w?.nasdaq_down_up_ratio, 2)}x`} state={ratioState(w?.nasdaq_down_up_ratio)} reference="1.00x = exact arithmetic balance · >1 down volume leads · <1 up volume leads" marker={position(w?.nasdaq_down_up_ratio, 0, 3.5)} />
        </div>
        <div className="notice"><Radio size={14} /> {familyEntries.length ? familyEntries.map(([name, on]) => `${familyNames[name] || name}: ${on ? "TURN" : "not yet"}`).join(" · ") : "Awaiting family-level turn data."}{contextEntries.length ? ` · Context: ${contextEntries.map(([name, on]) => `${contextNames[name] || name}: ${on ? "SUPPORTIVE" : "not yet"}`).join(" · ")}` : ""} · Snapshot {washoutTime}</div>
      </> : <div className="notice">RE-ENTRY market-internals feed is temporarily unavailable. No alternate legacy decision is substituted.</div>}
    </section>

    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">ALL 11 SECTORS</span><h2>Sector Daily Moves &amp; Repair</h2></div><span className="pill">{sectors.length}/11 loaded</span></div>
      <p className="section-intro">Today&apos;s movement first, with pullback and repair context beside it. The default view ranks the strongest sectors today from top to bottom.</p>
      <div className="sort-bar" aria-label="Sort sectors"><span>Sort by</span><SortButton active={sectorSort === "today"} direction={sectorDirection} onClick={() => toggleSectorSort("today")}>Today</SortButton><SortButton active={sectorSort === "drawdown"} direction={sectorDirection} onClick={() => toggleSectorSort("drawdown")}>Below 20D high</SortButton><SortButton active={sectorSort === "status"} direction={sectorDirection} onClick={() => toggleSectorSort("status")}>Repair status</SortButton></div>
      <div className="sector-table movement-table">
        <div className="sector-table-head sector-move-head"><span>Sector</span><span>Today</span><span>Below 20D high</span><span>Subsectors 3%+ down</span><span>Status</span></div>
        {sectors.map((row) => <div className="sector-table-row sector-move-row" key={row.symbol}><div><b>{row.label}</b><small>{row.symbol}</small></div><strong className={numeric(row.today, 0) > 0 ? "good-text" : numeric(row.today, 0) < 0 ? "bad-text" : "muted"}>{pct(row.today)}</strong><span>{pct(row.drawdown)}</span><span>{levelPct(row.damageShare, 0)}</span><span className={row.repairing ? "good-text" : "muted"}>{row.repairing ? "Repairing" : "No broad repair"}</span></div>)}
      </div>
      <div className="notice">Sector 5-day return is not currently published by the validated close snapshot, so it is intentionally not shown rather than inferred.</div>
    </section>

    <details className="card section-card">
      <summary className="section-heading" style={{ cursor: "pointer", listStyle: "none" }}>
        <div><span className="kicker">ALL SUBSECTORS</span><h2>Subsector Daily Moves &amp; Repair</h2></div>
        <div className="eyebrow-row"><span className="pill">{subsectors.length} tracked</span><ChevronDown size={18} /></div>
      </summary>
      <p className="section-intro">Today&apos;s movement first, with the 5-day move and recent pullback immediately beside it. Expand only when you want the full subsector table.</p>
      <div className="sort-bar" aria-label="Sort subsectors"><span>Sort by</span><SortButton active={subsectorSort === "today"} direction={subsectorDirection} onClick={() => toggleSubsectorSort("today")}>Today</SortButton><SortButton active={subsectorSort === "fiveDay"} direction={subsectorDirection} onClick={() => toggleSubsectorSort("fiveDay")}>5D</SortButton><SortButton active={subsectorSort === "drawdown"} direction={subsectorDirection} onClick={() => toggleSubsectorSort("drawdown")}>Below 20D high</SortButton><SortButton active={subsectorSort === "status"} direction={subsectorDirection} onClick={() => toggleSubsectorSort("status")}>Status</SortButton></div>
      <div className="subsector-head"><span>Subsector</span><span>Today</span><span>5D</span><span>Below 20D high</span><span>Status</span><span></span></div>
      <div className="internal-list">
        {subsectors.map(({ symbol, x, state, today }) => <details key={symbol} className="internal-row movement-row"><summary><div className="name-wrap"><span className="state-dot" data-state={state.dot} /><div><b>{x.label} <span>({symbol})</span></b><small>{sectorNames[x.parent_sector] || x.parent_sector}</small></div></div><div className="movement-metrics"><strong className={numeric(today, 0) > 0 ? "good-text" : numeric(today, 0) < 0 ? "bad-text" : "muted"}>{pct(today)}</strong><span>{pct(x.return_5d)}</span><span>{pct(x.drawdown_20d)}</span><b className={state.cls}>{state.label}</b><ChevronRight size={17} /></div></summary><div className="detail-grid"><span>Today <b>{pct(today)}</b></span><span>5D return <b>{pct(x.return_5d)}</b></span><span>Below 20D high <b>{pct(x.drawdown_20d)}</b></span><span>Below 60D high <b>{pct(x.drawdown_60d)}</b></span><span>vs SPY 20D <b>{pct(x.relative_strength_20d_vs_spy)}</b></span><span>vs {x.parent_sector} 20D <b>{pct(x.relative_strength_20d_vs_parent)}</b></span></div><p className="detail-copy">{x.repairing ? `${x.label} is repairing after a meaningful reset. This is constructive context, not an independent re-entry trigger.` : state.label === "NEUTRAL" ? `${x.label} is not materially damaged on the 20-day measure and is not currently in repair mode.` : `${x.label} remains in a reset or correction. The engine tracks whether this weakness begins to stabilize and broaden into repair.`}</p></details>)}
      </div>
    </details>
  </>;
}
