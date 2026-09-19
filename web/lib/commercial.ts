import type { WashoutSnapshot } from "./reentry";

const CANONICAL_EDGE_URL = "https://gexrdfzxmlnaawzmtlrk.supabase.co/functions/v1/reentry-intraday";

type CommercialEngine = NonNullable<WashoutSnapshot["unified_engine"]> & {
  deployment_signal?: string;
  deployment_reason?: string;
  recovery_stage?: string;
  recovery_stage_reason?: string;
  market_condition?: string;
  market_condition_reason?: string;
  confirmation_strength?: string;
  go_triggered_at_et?: string | null;
};

export type CommercialState = {
  label: "HOLD CASH" | "WATCH" | "BUY VOO";
  action: string;
  summary: string;
  recovery: string;
  timestamp: string | null;
  why: string[];
  rawDecision: string;
};

export async function getCanonicalCommercialSnapshot(): Promise<WashoutSnapshot | null> {
  try {
    const response = await fetch(CANONICAL_EDGE_URL, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    const body = await response.json() as { canonical_snapshot?: WashoutSnapshot | null };
    return body.canonical_snapshot ?? null;
  } catch {
    return null;
  }
}

function readableRecovery(value?: string) {
  if (value === "EARLY") return "Early recovery";
  if (value === "DEVELOPING") return "Recovery developing";
  if (value === "BROAD_CONFIRMATION") return "Broad recovery";
  return "Recovery status developing";
}

export function deriveCommercialState(snapshot: WashoutSnapshot | null): CommercialState {
  const engine = snapshot?.unified_engine as CommercialEngine | undefined;
  if (!engine) {
    return {
      label: "HOLD CASH",
      action: "Live signal unavailable. Do not treat this as a current model reading.",
      summary: "BTFD could not load the canonical market state.",
      recovery: "Signal unavailable",
      timestamp: null,
      why: ["The canonical signal feed is unavailable."],
      rawDecision: "UNAVAILABLE",
    };
  }

  const raw = engine.deployment_signal || engine.decision || "HOLD_CASH";
  const isBuy = raw === "DEPLOY" || raw === "GO_EARLY";
  const isWatch = raw === "WATCH";
  const label: CommercialState["label"] = isBuy ? "BUY VOO" : isWatch ? "WATCH" : "HOLD CASH";

  const context = engine.context_support || {};
  const why: string[] = [];
  if (engine.oversold_gate) why.push("The market reached a meaningful oversold setup.");
  if ((engine.fast_family_count || 0) > 0) why.push("A fast reversal has appeared.");
  if (context.MMFD_IMPROVING || context.NASI_TURNING_UP) why.push("Stock participation is beginning to improve.");
  if (context.VVIX_EASING || context.SKEW_NARROWING) why.push("Market stress is easing.");
  if (why.length < 3 && isBuy) why.push("The engine's qualifying re-entry rule has fired.");
  if (why.length < 3 && isWatch) why.push("More reversal evidence is still required before buying.");
  if (why.length < 3 && !isBuy && !isWatch) why.push("The model has not yet seen a qualifying re-entry setup.");

  return {
    label,
    action: isBuy
      ? "Move your designated sidelined re-entry allocation from SGOV into VOO."
      : "Stay in SGOV.",
    summary: isBuy
      ? "Enough reversal evidence has appeared after the pullback that the model no longer favors continuing to wait in the cash sleeve."
      : isWatch
        ? "Recovery evidence is building, but the model has not reached its buy threshold."
        : "The model has not seen enough evidence of a re-entry opportunity yet.",
    recovery: readableRecovery(engine.recovery_stage),
    timestamp: engine.go_triggered_at_et || engine.timestamp_et || null,
    why: why.slice(0, 5),
    rawDecision: raw,
  };
}

export function formatEastern(value: string | null) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}
