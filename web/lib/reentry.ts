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

export const pct = (value?: number | null, digits = 1) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
    : "-";

function parsePythonJson(raw: string): ReentrySnapshot {
  const strictJson = raw
    .replace(/\bNaN\b/g, "null")
    .replace(/-?\bInfinity\b/g, "null");
  return JSON.parse(strictJson) as ReentrySnapshot;
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
