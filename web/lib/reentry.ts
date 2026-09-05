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

export interface InsightItem {
  title: string;
  symbol?: string;
  state?: string;
  detail: string;
  why_it_matters?: string;
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
  data_freshness?: { same_day_complete?: boolean };
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
  market_insights?: {
    headline?: string;
    supporting_reentry?: InsightItem[];
    holding_back?: InsightItem[];
    sectors?: InsightItem[];
    subsectors?: InsightItem[];
    factors?: InsightItem[];
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

export const pct = (value?: number, digits = 1) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`
    : "-";

export async function getLatestSnapshot(): Promise<ReentrySnapshot | null> {
  const base = process.env.REENTRY_API_BASE_URL;
  if (!base) return null;

  const response = await fetch(`${base}?resource=latest`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`RE-ENTRY API returned ${response.status}`);
  return response.json();
}
