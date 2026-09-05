import type { ReentrySnapshot } from "./reentry";

export const sampleSnapshot: ReentrySnapshot = {
  engine_version: "reentry_engine_1",
  as_of: "2026-09-04",
  signal: "WAIT",
  signal_interpretation: "Internal repair is developing, but historical evidence does not yet support putting cash back to work.",
  market_damage: "LIGHT",
  internal_reset: "DEVELOPING",
  selling_pressure: "STABILIZING",
  analog_decision: "NO",
  factor_leadership_state: ["NO MATERIAL FACTOR RESET"],
  data_freshness: { same_day_complete: true },
  current_inputs: {
    spy_drawdown_20d: -0.009885843574844344,
    spy_return_5d: 0.0010918567905857657,
    pct_sp500_above_50dma: 0.47105788423153694,
    pct_sp500_above_200dma: 0.6407185628742516,
    breadth_1d_change: -0.03992015968063867,
    breadth_3d_change: 0.005988023952095856,
    vix_5d_change: 0.006930006930006893,
    vix_vix3m_ratio: 0.825099375354912
  },
  signal_snapshot: {
    sectors: {
      XLK: { drawdown_20d: -0.024, drawdown_60d: -0.067, relative_strength_20d_vs_spy: -0.012, relative_strength_60d_vs_spy: -0.031 },
      XLF: { drawdown_20d: -0.028, drawdown_60d: -0.043, relative_strength_20d_vs_spy: -0.018, relative_strength_60d_vs_spy: -0.014 },
      XLI: { drawdown_20d: -0.060, drawdown_60d: -0.077, relative_strength_20d_vs_spy: -0.051, relative_strength_60d_vs_spy: -0.042 },
      XLV: { drawdown_20d: -0.031, drawdown_60d: -0.049, relative_strength_20d_vs_spy: -0.021, relative_strength_60d_vs_spy: -0.019 },
      XLY: { drawdown_20d: -0.040, drawdown_60d: -0.063, relative_strength_20d_vs_spy: -0.028, relative_strength_60d_vs_spy: -0.027 },
      XLRE: { drawdown_20d: -0.027, drawdown_60d: -0.045, relative_strength_20d_vs_spy: -0.016, relative_strength_60d_vs_spy: -0.018 }
    }
  },
  subsector_intelligence: {
    aggregate: { damage_share_2pct: 0.733, damage_share_3pct: 0.60, repair_share: 0.1667 },
    by_sector: {
      XLK: { damage_share_3pct: 0.667, repair_share: 0.333 },
      XLF: { damage_share_3pct: 0.50, repair_share: 0.25 },
      XLRE: { damage_share_3pct: 0.333, repair_share: 0.333 }
    },
    proxies: {
      SMH: { label: "Semiconductors", parent_sector: "XLK", drawdown_20d: -0.0456, drawdown_60d: -0.1523, return_1d: 0.0261, return_5d: 0.0251, relative_strength_20d_vs_spy: -0.0230, relative_strength_20d_vs_parent: -0.0233, relative_strength_60d_vs_parent: -0.0684, repairing: true },
      IGV: { label: "Software", parent_sector: "XLK", drawdown_20d: -0.052, drawdown_60d: -0.081, return_1d: 0.008, return_5d: -0.003, relative_strength_20d_vs_spy: -0.038, relative_strength_20d_vs_parent: -0.026, relative_strength_60d_vs_parent: -0.031, repairing: false },
      HACK: { label: "Cybersecurity", parent_sector: "XLK", drawdown_20d: -0.091, drawdown_60d: -0.125, return_1d: 0.012, return_5d: -0.005, relative_strength_20d_vs_spy: -0.070, relative_strength_20d_vs_parent: -0.058, relative_strength_60d_vs_parent: -0.061, repairing: false },
      ITA: { label: "Aerospace & Defense", parent_sector: "XLI", drawdown_20d: -0.109, drawdown_60d: -0.132, return_1d: 0.006, return_5d: -0.010, relative_strength_20d_vs_spy: -0.094, relative_strength_20d_vs_parent: -0.041, relative_strength_60d_vs_parent: -0.045, repairing: false },
      ITB: { label: "Homebuilders", parent_sector: "XLY", drawdown_20d: -0.066, drawdown_60d: -0.082, return_1d: 0.015, return_5d: 0.004, relative_strength_20d_vs_spy: -0.052, relative_strength_20d_vs_parent: -0.024, relative_strength_60d_vs_parent: -0.031, repairing: false }
    }
  },
  market_insights: {
    headline: "Repair is beginning beneath the index, but historical analogs are not yet favorable enough for re-entry.",
    supporting_reentry: [
      { title: "Semiconductors", symbol: "SMH", state: "REPAIRING", detail: "Semis are repairing after a meaningful reset.", why_it_matters: "Damaged leadership beginning to recover is constructive early re-entry evidence." },
      { title: "Selling pressure", state: "STABILIZING", detail: "Aggregate selling pressure has stopped worsening." }
    ],
    holding_back: [
      { title: "Historical analogs", state: "NO", detail: "Closest historical setups remain insufficiently favorable." },
      { title: "Repair breadth", detail: "Repair is present, but still too narrow across damaged groups." }
    ],
    sectors: [],
    subsectors: [],
    factors: []
  },
  historical_validation: {
    final_independent_reentry_episodes: 189,
    SPY_5D_median_after_signal: 0.00297,
    SPY_10D_median_after_signal: 0.00920,
    SPY_30D_median_after_signal: 0.02466,
    SPY_60D_median_after_signal: 0.03846,
    QQQ_5D_median_after_signal: 0.00420,
    QQQ_10D_median_after_signal: 0.01228,
    QQQ_30D_median_after_signal: 0.02608,
    QQQ_60D_median_after_signal: 0.05318
  }
};
