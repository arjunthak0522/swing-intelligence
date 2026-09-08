import { readFile } from "node:fs/promises";
import path from "node:path";

export interface HistoricalEpisodeMetricSummary {
  n: number;
  median: number | null;
  mean: number | null;
  positive_rate: number | null;
  p25: number | null;
  p75: number | null;
  min: number | null;
  max: number | null;
}

export interface HistoricalEpisodeRow {
  start: string;
  last_favorable: string;
  next_state_date: string | null;
  next_state: string | null;
  active_at_sample_end: boolean;
  reenter_sessions: number;
  setup_source: string;
  analog_at_start: string;
  SPY_entry_close: number;
  SPY_last_favorable_close: number;
  SPY_return_during_episode: number;
  SPY_max_gain_during_episode: number;
  SPY_max_adverse_during_episode: number;
  QQQ_entry_close: number;
  QQQ_last_favorable_close: number;
  QQQ_return_during_episode: number;
  QQQ_max_gain_during_episode: number;
  QQQ_max_adverse_during_episode: number;
}

interface EpisodeSummary {
  completed_episode_count: number;
  active_at_sample_end_count: number;
  episode_length_sessions: HistoricalEpisodeMetricSummary;
  SPY: {
    return_during_episode: HistoricalEpisodeMetricSummary;
    max_gain_during_episode: HistoricalEpisodeMetricSummary;
    max_adverse_during_episode: HistoricalEpisodeMetricSummary;
  };
  QQQ: {
    return_during_episode: HistoricalEpisodeMetricSummary;
    max_gain_during_episode: HistoricalEpisodeMetricSummary;
    max_adverse_during_episode: HistoricalEpisodeMetricSummary;
  };
}

interface FixedHorizonStat {
  median: number;
  n: number;
}

export interface HistoricalEpisodeEvidence {
  schema_version: string;
  canonical_engine_commit: string;
  canonical_sample_end: string;
  frozen_reconstruction_generated_at: string;
  continuous_episode_count: number;
  continuous_episode_definition: string;
  return_definition: string;
  continuous_episode_summary: EpisodeSummary;
  continuous_episodes: HistoricalEpisodeRow[];
  archived_entry_timing_validation: {
    source: string;
    validation_event_count: number;
    event_definition: string;
    fixed_horizon: {
      SPY: Record<"5D" | "10D" | "30D" | "60D", FixedHorizonStat>;
      QQQ: Record<"5D" | "10D" | "30D" | "60D", FixedHorizonStat>;
    };
  };
  reconstruction_diagnostic: {
    current_cooldown_event_count: number;
    archived_cooldown_event_count: number;
    status: string;
    note: string;
  };
}

export async function getHistoricalEpisodeEvidence(): Promise<HistoricalEpisodeEvidence | null> {
  const candidates = [
    path.join(process.cwd(), "public", "reentry", "historical_episodes.json"),
    path.join(process.cwd(), "web", "public", "reentry", "historical_episodes.json"),
  ];
  for (const file of candidates) {
    try {
      const raw = await readFile(file, "utf-8");
      return JSON.parse(raw) as HistoricalEpisodeEvidence;
    } catch {
      // Try the other supported Vercel root layout.
    }
  }
  return null;
}
