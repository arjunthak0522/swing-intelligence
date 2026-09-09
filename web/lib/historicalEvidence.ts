import { readFile } from "node:fs/promises";
import path from "node:path";

export interface HorizonMetric {
  n: number;
  median_return: number;
  mean_return: number;
  positive_rate: number;
  p25_return: number;
  p75_return: number;
  median_mae: number;
  p10_mae: number;
  median_mfe: number;
  false_start_rate_return_lt_minus_2pct: number;
}

export interface HistoricalEpisodeRow {
  start: string;
  favorable_through: string;
  next_state_date: string | null;
  next_state: string | null;
  reenter_sessions: number;
  signal_source: string;
  analog_at_start: string;
  SPY_start_close: number;
  SPY_favorable_through_close: number;
  SPY_episode_return: number;
  SPY_max_gain_during_episode: number;
  SPY_max_adverse_during_episode: number;
  QQQ_start_close: number;
  QQQ_favorable_through_close: number;
  QQQ_episode_return: number;
  QQQ_max_gain_during_episode: number;
  QQQ_max_adverse_during_episode: number;
  [key: string]: string | number | null;
}

export interface HistoricalEpisodeLedger {
  provenance: {
    classification: "RECONSTRUCTED" | string;
    engine_commit: string;
    rebuild_date: string;
    data_note: string;
  };
  definition: string;
  forward_return_definition: string;
  episode_count: number;
  completed_episode_count: number;
  active_episode_count: number;
  summary: {
    SPY_episode_return: EpisodeSummaryMetric;
    QQQ_episode_return: EpisodeSummaryMetric;
    duration_sessions: EpisodeSummaryMetric;
  };
  episodes: HistoricalEpisodeRow[];
}

export interface EpisodeSummaryMetric {
  n: number;
  mean: number | null;
  median: number | null;
  positive_rate: number | null;
  p25: number | null;
  p75: number | null;
}

export interface CanonicalHistoricalEvidence {
  provenance: {
    source: string;
    workflow_run_id: number;
    artifact_id: number;
    engine_commit: string;
    sample_start: string;
    sample_end: string;
    status: string;
    note: string;
  };
  retail_validation_summary: {
    final_independent_reentry_episodes: number;
    incremental_early_internal_episodes: number;
    incremental_subsector_candidate_episodes: number;
    result: string;
    subsector_direct_promotion: string;
    SPY_5D_median_after_signal: number;
    SPY_10D_median_after_signal: number;
    SPY_30D_median_after_signal: number;
    SPY_60D_median_after_signal: number;
    QQQ_5D_median_after_signal: number;
    QQQ_10D_median_after_signal: number;
    QQQ_30D_median_after_signal: number;
    QQQ_60D_median_after_signal: number;
    important_limit: string;
  };
  final_policy_validation: {
    count: number;
    SPY: Record<string, HorizonMetric>;
    QQQ: Record<string, HorizonMetric>;
  };
  latest_policy_rows: Array<{
    date: string;
    final_policy_signal: string;
    SPY?: number;
    QQQ?: number;
  }>;
}

async function readJson<T>(relative: string): Promise<T | null> {
  const candidates = [
    path.join(process.cwd(), "public", relative),
    path.join(process.cwd(), "web", "public", relative),
  ];
  for (const file of candidates) {
    try {
      return JSON.parse(await readFile(file, "utf-8")) as T;
    } catch {
      // Support both repository-root and web-root Vercel layouts.
    }
  }
  return null;
}

export async function getHistoricalEpisodeEvidence(): Promise<CanonicalHistoricalEvidence | null> {
  return readJson<CanonicalHistoricalEvidence>(path.join("reentry", "validation", "canonical_historical_evidence_2026-09-04.json"));
}

export async function getHistoricalEpisodeLedger(): Promise<HistoricalEpisodeLedger | null> {
  return readJson<HistoricalEpisodeLedger>(path.join("reentry", "validation", "historical_episode_ledger_2026-09-09.json"));
}
