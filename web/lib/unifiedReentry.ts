export type UnifiedDecisionState = "WAIT" | "WATCH" | "GO_EARLY";
export type MarketPhase = "LIVE_PROVISIONAL" | "CLOSE_SETTLING" | "MARKET_CLOSED_FINAL";
export type DataQualityStatus = "OK" | "PARTIAL" | "DEGRADED";

export interface MarketPriceContext {
  price: number | null;
  previous_close: number | null;
  change_pct: number | null;
  timestamp_et: string | null;
  source: string;
  decision_input: false;
}

export interface UnifiedEngineSnapshot {
  engine_version: string;
  primary_engine: true;
  oversold_gate: boolean;
  fast_family_count: number;
  context_support_count: number;
  context_support: {
    MMFD_IMPROVING: boolean;
    NASI_TURNING_UP: boolean;
    VVIX_EASING: boolean;
    SKEW_NARROWING: boolean;
  };
  state: UnifiedDecisionState;
  decision: UnifiedDecisionState;
  logic: string;
  market_phase: MarketPhase;
  timestamp_et: string;
  market_date: string;
  data_quality_status?: DataQualityStatus;
  actionable?: boolean;
}

export interface UnifiedDataQuality {
  status: DataQualityStatus;
  actionable: boolean;
  issues: string[];
  warnings: string[];
  fast_source_availability: Record<string, boolean>;
  context_source_availability: Record<string, boolean>;
  mmfd_coverage_pct: number | null;
  note: string;
}

export interface UnifiedProspectiveHistory {
  snapshot_count: number;
  market_days: number;
  state_transitions: number;
  go_early_snapshots: number;
  watch_snapshots: number;
}

export interface UnifiedSnapshot {
  snapshot_version?: string;
  snapshot_generated_at_et?: string;
  generated_at_utc?: string;
  research_only?: boolean;
  daily_context_state?: string;
  turn_family_count?: number;
  families?: {
    fast_breadth_turn?: boolean;
    momentum_turn?: boolean;
    net_volume_turn?: boolean;
    down_up_ratio_relief?: boolean;
  };
  values?: {
    market_date?: string;
    timestamp_et?: string;
    SPXA20R?: number | null;
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
    MMFD?: number | null;
    MMFD_STATE?: string | null;
    VVIX?: number | null;
    VVIX_PRIOR_CLOSE?: number | null;
    VVIX_DIRECTION?: string | null;
    VVIX_STATE?: string | null;
    VVIX_PERCENTILE_2Y?: number | null;
    SKEW_LIVE_PROXY?: number | null;
    SKEW_LIVE_PROXY_RATIO?: number | null;
    SKEW_DIRECTION?: string | null;
    SKEW_OFFICIAL_CLOSE?: number | null;
    SKEW_OFFICIAL_PERCENTILE_2Y?: number | null;
  };
  nasi_plus?: {
    formula_version?: string;
    bootstrap_start_date?: string;
    completed_daily_observations?: number;
    prior_completed_rsi?: number | null;
  };
  mmfd_live?: {
    formula_version?: string;
    universe_size?: number;
    valid_5d_observations?: number;
    coverage_pct?: number;
    state?: string;
    timestamp_et?: string;
  };
  vvix_live?: {
    value?: number;
    prior_close?: number;
    direction_vs_prior_close?: string;
    historical_percentile_2y?: number;
    completed_history_sessions?: number;
    state?: string;
    timestamp_et?: string;
  };
  skew_live?: {
    live_proxy_vol_points?: number;
    live_proxy_ratio?: number;
    direction_vs_prior_snapshot?: string;
    official_skew_latest_close?: number;
    official_skew_date?: string;
    official_skew_percentile_2y?: number;
    source_mode?: string;
    timestamp_et?: string;
  };
  unified_engine?: UnifiedEngineSnapshot;
  data_quality?: UnifiedDataQuality;
  prospective_history?: UnifiedProspectiveHistory;
  market_prices?: Record<string, MarketPriceContext>;
  market_price_errors?: string[];
  sources?: Record<string, {
    provider?: string;
    timestamp?: string | null;
    source_mode?: string;
    coverage_pct?: number | null;
    official_date?: string | null;
    bootstrap_start_date?: string | null;
    completed_daily_observations?: number | null;
    history_sessions?: number | null;
    provisional?: boolean;
  }>;
  errors?: Record<string, string>;
}

const DEFAULT_UNIFIED_URL =
  "https://raw.githubusercontent.com/arjunthak0522/swing-intelligence/intraday-signal-research/data/reentry/exhaustion_intraday_current.json";

export async function getUnifiedSnapshot(): Promise<UnifiedSnapshot | null> {
  const url = process.env.REENTRY_UNIFIED_SNAPSHOT_URL || DEFAULT_UNIFIED_URL;
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json", "User-Agent": "RE-ENTRY-unified-dashboard" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    const snapshot = (await response.json()) as UnifiedSnapshot;
    if (!snapshot?.unified_engine?.engine_version) return null;
    return snapshot;
  } catch {
    return null;
  }
}

export function pct(value?: number | null, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
    : "-";
}

export function num(value?: number | null, digits = 1): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "-";
}

export function phaseLabel(phase?: string | null): string {
  if (phase === "LIVE_PROVISIONAL") return "LIVE - PROVISIONAL";
  if (phase === "CLOSE_SETTLING") return "CLOSE SETTLING";
  if (phase === "MARKET_CLOSED_FINAL") return "MARKET CLOSED - FINAL";
  return "STATUS UNAVAILABLE";
}

export function decisionLabel(state?: string | null): string {
  return state === "GO_EARLY" ? "GO EARLY" : state || "UNAVAILABLE";
}
