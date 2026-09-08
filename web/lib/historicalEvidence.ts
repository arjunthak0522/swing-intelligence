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

export async function getHistoricalEpisodeEvidence(): Promise<CanonicalHistoricalEvidence | null> {
  const relative = path.join("reentry", "validation", "canonical_historical_evidence_2026-09-04.json");
  const candidates = [
    path.join(process.cwd(), "public", relative),
    path.join(process.cwd(), "web", "public", relative),
  ];

  for (const file of candidates) {
    try {
      const raw = await readFile(file, "utf-8");
      return JSON.parse(raw) as CanonicalHistoricalEvidence;
    } catch {
      // Support both repository-root and web-root Vercel layouts.
    }
  }
  return null;
}
