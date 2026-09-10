import { readFile } from "node:fs/promises";
import path from "node:path";

export type Signal = "RE-ENTER" | "WAIT" | "NO RE-ENTRY SETUP";

export interface SubsectorProxy {
  label: string;
  parent_sector: string;
  drawdown_20d: number;
  drawdown_60d: number;
  return_1d: number;
  return_5d: number;
  relative_strength_20d_vs_spy: number;
  relative_strength_20d_vs_parent: number;
  relative_strength_60d_vs_parent: number;
  repairing: boolean;
}

export interface InsightKeyGroup {
  label: string;
  symbol: string;
  parent_sector: string;
  state: string;
  stance: string;
  interpretation: string;
  why_it_matters: string;
}

export interface OutperformanceCandidate {
  rank: number;
  symbol: string;
  label: string;
  parent_sector?: string | null;
  predicted_median_excess_vs_spy: number;
  neighbor_positive_excess_rate: number;
  neighbors: number;
}

export interface OutperformanceIntelligence {
  status: "INACTIVE" | "NO_HIGH_CONFIDENCE_EDGE" | "HIGH_CONFIDENCE_CANDIDATES";
  label: string;
  as_of?: string | null;
  candidate_count: number;
  candidates: OutperformanceCandidate[];
  gate: {
    minimum_predicted_median_excess_vs_spy: number;
    minimum_neighbor_positive_excess_rate: number;
  };
  interpretation: string;
  methodology: string;
}

export interface ReentrySnapshot {
  engine_version: string;
  as_of: string;
  signal: Signal;
  signal_interpretation: string;
  market_damage: string;
  internal_reset: string;
  selling_pressure: string;
  analog_decision: string;
  factor_leadership_state: string[];
  data_freshness?: { same_day_complete?: boolean; target_session?: string };
  current_inputs: {
    spy_drawdown_20d: number;
    spy_return_5d: number;
    pct_sp500_above_50dma: number;
    pct_sp500_above_200dma: number;
    breadth_1d_change: number;
    breadth_3d_change: number;
    vix_5d_change: number;
    vix_vix3m_ratio: number;
  };
  signal_snapshot?: {
    sectors?: Record<string, {
      drawdown_20d: number;
      drawdown_60d: number;
      relative_strength_20d_vs_spy: number;
      relative_strength_60d_vs_spy: number;
    }>;
    factors?: Record<string, {
      drawdown_20d: number;
      drawdown_60d: number;
      relative_strength_20d_vs_spy: number;
      relative_strength_60d_vs_spy: number;
    }>;
  };
  subsector_intelligence?: {
    aggregate?: {
      damage_share_2pct?: number;
      damage_share_3pct?: number;
      repair_share?: number;
    };
    by_sector?: Record<string, {
      damage_share_2pct?: number;
      damage_share_3pct?: number;
      repair_share?: number;
      members?: Record<string, SubsectorProxy>;
    }>;
    proxies?: Record<string, SubsectorProxy>;
  };
  outperformance_intelligence?: OutperformanceIntelligence;
  market_insights?: {
    headline?: string;
    supporting_reentry?: string[];
    holding_back?: string[];
    key_groups?: InsightKeyGroup[];
    signal?: string;
    internal_reset?: string;
    selling_pressure?: string;
    analog_decision?: string;
  };
  historical_validation: {
    final_independent_reentry_episodes: number;
    SPY_5D_median_after_signal: number;
    SPY_10D_median_after_signal: number;
    SPY_30D_median_after_signal: number;
    SPY_60D_median_after_signal: number;
    QQQ_5D_median_after_signal: number;
    QQQ_10D_median_after_signal: number;
    QQQ_30D_median_after_signal: number;
    QQQ_60D_median_after_signal: number;
  };
  forward_analog_outcomes?: Record<string, unknown>;
}

export interface ReentryEpisode {
  episode_start: string;
  favorable_through: string;
  active: boolean;
  ended_on?: string | null;
  entry_closes: {
    SPY: number;
    QQQ: number;
  };
  definition?: string;
  price_definition?: string;
}

export interface IntradayQuote {
  symbol: string;
  price: number | null;
  previous_close: number | null;
  change_pct: number | null;
  timestamp: string | null;
  market_state: string | null;
}

export interface IntradaySnapshot {
  generated_at: string;
  status: "LIVE" | "PARTIAL" | "DEGRADED";
  official_signal_authoritative: false;
  interpretation: string;
  summary: {
    sectors_positive_share: number | null;
    subsectors_positive_share: number | null;
    factors_positive_share: number | null;
    tracked_quotes: number;
    expected_quotes: number;
  };
  quotes: Record<string, IntradayQuote>;
  errors: string[];
}

export interface WashoutSnapshot {
  state?: string;
  candidate_action?: string;
  turn_family_count?: number;
  generated_at_utc?: string;
  daily_context_state?: string;
  families?: Record<string, boolean>;
  values?: {
    market_date?: string | null;
    timestamp_et?: string | null;
    SPXA20R?: number | null;
    MMFD?: number | null;
    MMFD_STATE?: string | null;
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
  mmfd_live?: { coverage_pct?: number | null };
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
}

export const pct = (value?: number | null, digits = 1) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
    : "-";

function normalizeInsightList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item === "string") return item.trim() ? [item] : [];
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    const title = typeof row.title === "string" ? row.title.trim() : "";
    const detail = typeof row.detail === "string" ? row.detail.trim() : "";
    const text = title && detail ? `${title}: ${detail}` : detail || title;
    return text ? [text] : [];
  });
}

function parsePythonJson(raw: string): ReentrySnapshot {
  const strictJson = raw
    .replace(/\bNaN\b/g, "null")
    .replace(/-?\bInfinity\b/g, "null");
  const parsed = JSON.parse(strictJson) as ReentrySnapshot;
  const insights = parsed.market_insights as unknown;
  if (insights && typeof insights === "object") {
    const row = insights as Record<string, unknown>;
    parsed.market_insights = {
      ...(row as ReentrySnapshot["market_insights"]),
      supporting_reentry: normalizeInsightList(row.supporting_reentry),
      holding_back: normalizeInsightList(row.holding_back),
    };
  }
  return parsed;
}

async function readPublicReentryFile<T>(filename: string): Promise<T | null> {
  const candidates = [
    path.join(process.cwd(), "public", "reentry", filename),
    path.join(process.cwd(), "web", "public", "reentry", filename),
  ];
  for (const file of candidates) {
    try {
      const raw = await readFile(file, "utf-8");
      return JSON.parse(raw) as T;
    } catch {
      // Try the next supported Vercel root layout.
    }
  }
  return null;
}

export async function getLatestSnapshot(): Promise<ReentrySnapshot | null> {
  const candidates = [
    path.join(process.cwd(), "public", "reentry", "latest.json"),
    path.join(process.cwd(), "web", "public", "reentry", "latest.json"),
  ];
  for (const file of candidates) {
    try {
      const raw = await readFile(file, "utf-8");
      return parsePythonJson(raw);
    } catch {
      // Try the next supported Vercel root layout.
    }
  }
  return null;
}

export async function getLatestEpisode(): Promise<ReentryEpisode | null> {
  return readPublicReentryFile<ReentryEpisode>("episode.json");
}

const INTRADAY_URL = "https://gexrdfzxmlnaawzmtlrk.supabase.co/functions/v1/reentry-intraday";
const WASHOUT_URL = "https://raw.githubusercontent.com/arjunthak0522/swing-intelligence/intraday-signal-research/data/reentry/exhaustion_intraday_current.json";

export async function getIntradaySnapshot(): Promise<IntradaySnapshot | null> {
  try {
    const response = await fetch(INTRADAY_URL, {
      headers: { Accept: "application/json" },
      next: { revalidate: 60 },
    });
    if (!response.ok) return null;
    return (await response.json()) as IntradaySnapshot;
  } catch {
    return null;
  }
}

export async function getWashoutSnapshot(): Promise<WashoutSnapshot | null> {
  try {
    const response = await fetch(WASHOUT_URL, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as WashoutSnapshot;
  } catch {
    return null;
  }
}
