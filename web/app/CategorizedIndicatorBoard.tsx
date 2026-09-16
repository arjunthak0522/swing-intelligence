import { Clock3 } from "lucide-react";
import type { WashoutSnapshot } from "../lib/reentry";

type AnyRecord = Record<string, any>;

type IndicatorRow = {
  name: string;
  value: string;
  state: string;
  direction: string;
  freshness: string;
  role: string;
};

type Category = {
  title: string;
  description: string;
  rows: IndicatorRow[];
};

const fmt = (value: unknown, digits = 2) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "UNAVAILABLE";

const pctPoint = (value: unknown, digits = 1) =>
  typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(digits)}%` : "UNAVAILABLE";

const pctChange = (value: unknown, digits = 2) =>
  typeof value === "number" && Number.isFinite(value) ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%` : "UNAVAILABLE";

const boolState = (value: unknown) => value === true ? "ON" : value === false ? "OFF" : "UNAVAILABLE";
const boolDir = (value: unknown) => value === true ? "ACTIVE" : value === false ? "INACTIVE" : "UNAVAILABLE";
const clean = (value: unknown) => typeof value === "string" && value ? value.replaceAll("_", " ") : "UNAVAILABLE";

function row(name: string, value: string, state: string, direction: string, freshness: string, role: string): IndicatorRow {
  return { name, value, state, direction, freshness, role };
}

function stateClass(state: string) {
  const s = state.toUpperCase();
  if (s.includes("ON") || s.includes("SUPPORT") || s.includes("NORMALIZED") || s.includes("RISING") || s.includes("BROADENING")) return "good";
  if (s.includes("OVERSOLD") || s.includes("WASH") || s.includes("FEAR") || s.includes("WEAK") || s.includes("DEFENSIVE") || s.includes("FALL") || s.includes("DOWN") || s.includes("WIDEN")) return "warn";
  return "neutral";
}

export default function CategorizedIndicatorBoard({ washout }: { washout: WashoutSnapshot }) {
  const w = washout as WashoutSnapshot & AnyRecord;
  const u = (w.unified_engine || {}) as AnyRecord;
  const v = (w.values || {}) as AnyRecord;
  const lead = ((w.leading_indicators || u.leading_indicators || {}) as AnyRecord).indicators || {};
  const secondary = (w.secondary_confirmation || u.secondary_confirmation || {}) as AnyRecord;
  const sf = secondary.families || {};
  const t2108 = (w.t2108_context || secondary?.breadth_context?.t2108 || {}) as AnyRecord;
  const prices = (w.market_prices || {}) as AnyRecord;
  const nasi = (w.nasi_plus || {}) as AnyRecord;
  const vvix = (w.vvix_live || {}) as AnyRecord;
  const skew = (w.skew_live || {}) as AnyRecord;
  const fastNow = (u.fast_families_current_snapshot || w.families || {}) as AnyRecord;
  const fastRecent = (u.fast_families || {}) as AnyRecord;
  const context = (u.context_support || {}) as AnyRecord;
  const extension = (u.extension_signals || {}) as AnyRecord;
  const shortBreadth = (lead.nasdaq_short_breadth || {}) as AnyRecord;
  const mcVelocity = (lead.mcclellan_velocity || {}) as AnyRecord;
  const zweig = (lead.zweig_breadth_thrust || {}) as AnyRecord;
  const credit = (lead.credit_risk_turn || {}) as AnyRecord;
  const risk = (sf.risk_appetite || {}) as AnyRecord;
  const vol = (sf.vol_structure || {}) as AnyRecord;
  const thrust = (sf.breadth_thrust || {}) as AnyRecord;
  const options = (sf.options_sentiment || {}) as AnyRecord;

  const advanceShare = typeof thrust.nasdaq_advance_share === "number"
    ? thrust.nasdaq_advance_share * 100
    : (typeof nasi.live_advances === "number" && typeof nasi.live_declines === "number" && nasi.live_advances + nasi.live_declines > 0
      ? (nasi.live_advances / (nasi.live_advances + nasi.live_declines)) * 100
      : null);

  const categories: Category[] = [
    {
      title: "CORE OVERSOLD / SETUP",
      description: "Measures whether enough market damage exists for a re-entry setup to matter.",
      rows: [
        row("S&P 500 above 20DMA (SPXA20R)", pctPoint(v.SPXA20R), v.SPXA20R != null && v.SPXA20R <= 30 ? "OVERSOLD" : "NORMAL", "—", "INTRADAY / DELAYED", "DECISION INPUT"),
        row("MMFD breadth", pctPoint(v.MMFD), clean(v.MMFD_STATE || w.mmfd_live?.state), "—", w.mmfd_live?.timestamp_et ? "INTRADAY" : "UNAVAILABLE", "DECISION INPUT"),
        row("NASI+ RSI", fmt(v.NASI_RSI), v.NASI_RSI != null && v.NASI_RSI < 30 ? "OVERSOLD" : "NORMAL", clean(v.NASI_DIRECTION), "INTRADAY / PROVISIONAL", "DECISION INPUT"),
        row("NASI+ EMA4", fmt(v.NASI_EMA4), "REFERENCE", "—", "INTRADAY / PROVISIONAL", "SETUP CONTEXT"),
        row("NASI+ EMA10", fmt(v.NASI_EMA10), "REFERENCE", "—", "INTRADAY / PROVISIONAL", "SETUP CONTEXT"),
        row("T2108-style NYSE breadth", pctPoint(t2108.value ?? v.T2108), clean(t2108.state), clean(t2108.direction), clean(t2108.freshness_state || t2108.freshness_type), "CONTEXT ONLY"),
        row("Nasdaq short breadth — above 5DMA", pctPoint(shortBreadth.above_5dma_pct), clean(shortBreadth.state), clean(shortBreadth.direction), clean(shortBreadth.freshness_state || shortBreadth.freshness_type), "LEADING CONTEXT"),
        row("Nasdaq short breadth — above 10DMA", pctPoint(shortBreadth.above_10dma_pct), clean(shortBreadth.state), clean(shortBreadth.direction), clean(shortBreadth.freshness_state || shortBreadth.freshness_type), "LEADING CONTEXT"),
      ],
    },
    {
      title: "FAST REVERSAL / TRIGGER",
      description: "Short-horizon reversal families that can qualify GO EARLY after the oversold gate is active.",
      rows: [
        row("Fast Breadth Turn", boolState(fastNow.FAST_BREADTH_TURN ?? fastNow.fast_breadth_turn), boolState(fastNow.FAST_BREADTH_TURN ?? fastNow.fast_breadth_turn), boolDir(fastNow.FAST_BREADTH_TURN ?? fastNow.fast_breadth_turn), "CURRENT SNAPSHOT", "DERIVED TRIGGER"),
        row("Momentum Turn", boolState(fastNow.MOMENTUM_TURN ?? fastNow.momentum_turn), boolState(fastNow.MOMENTUM_TURN ?? fastNow.momentum_turn), boolDir(fastNow.MOMENTUM_TURN ?? fastNow.momentum_turn), "CURRENT SNAPSHOT", "DERIVED TRIGGER"),
        row("Net Volume Turn", boolState(fastNow.NET_VOLUME_TURN ?? fastNow.net_volume_turn), boolState(fastNow.NET_VOLUME_TURN ?? fastNow.net_volume_turn), boolDir(fastNow.NET_VOLUME_TURN ?? fastNow.net_volume_turn), "CURRENT SNAPSHOT", "DERIVED TRIGGER"),
        row("Down/Up Ratio Relief", boolState(fastNow.DOWN_UP_RATIO_RELIEF ?? fastNow.down_up_ratio_relief), boolState(fastNow.DOWN_UP_RATIO_RELIEF ?? fastNow.down_up_ratio_relief), boolDir(fastNow.DOWN_UP_RATIO_RELIEF ?? fastNow.down_up_ratio_relief), "CURRENT SNAPSHOT", "DERIVED TRIGGER"),
        row("Current fast-family count", `${u.confirmation_components?.current_fast_family_count ?? w.turn_family_count ?? 0}/4`, "CURRENT", "—", "CURRENT SNAPSHOT", "TRIGGER SUMMARY"),
        row("30-minute remembered fast families", `${u.fast_family_count ?? Object.values(fastRecent).filter(Boolean).length}/4`, "MEMORY", "—", "30-MINUTE MEMORY", "TRIGGER SUMMARY"),
      ],
    },
    {
      title: "BREADTH & PARTICIPATION",
      description: "Shows how broadly stocks are participating and whether breadth momentum is repairing.",
      rows: [
        row("Nasdaq advances", fmt(v.NAADV ?? nasi.live_advances, 0), "BREADTH", "—", "INTRADAY / DELAYED", "CONTEXT"),
        row("Nasdaq declines", fmt(v.NADEC ?? nasi.live_declines, 0), "BREADTH", "—", "INTRADAY / DELAYED", "CONTEXT"),
        row("Nasdaq advance share", pctPoint(advanceShare), clean(thrust.state), "—", clean(thrust.freshness_state || thrust.freshness_type), "SECONDARY CONFIRMATION"),
        row("NYMO", fmt(v.NYMO), "MOMENTUM", "—", "PRIOR CLOSE WHEN LIVE FEED UNAVAILABLE", "FAST-FAMILY INPUT"),
        row("NAMO", fmt(v.NAMO), "MOMENTUM", "—", "PRIOR CLOSE WHEN LIVE FEED UNAVAILABLE", "FAST-FAMILY INPUT"),
        row("Nasdaq McClellan Oscillator", fmt(nasi.mcclellan_oscillator), "BREADTH MOMENTUM", clean(v.NASI_DIRECTION), "INTRADAY / PROVISIONAL", "CONTEXT"),
        row("Nasdaq Summation Index", fmt(nasi.summation_index), "BREADTH TREND", clean(v.NASI_DIRECTION), "INTRADAY / PROVISIONAL", "CONTEXT"),
        row("McClellan Velocity", fmt(mcVelocity.change_1_session), clean(mcVelocity.state), clean(mcVelocity.direction), clean(mcVelocity.freshness_state || mcVelocity.freshness_type), "LEADING CONTEXT"),
        row("Breadth Participation Thrust", pctPoint(advanceShare), clean(thrust.state), "—", clean(thrust.freshness_state || thrust.freshness_type), "SECONDARY CONFIRMATION"),
        row("Zweig Breadth Thrust", zweig.triggered === true ? "TRIGGERED" : zweig.triggered === false ? "NOT TRIGGERED" : "UNAVAILABLE", clean(zweig.state), clean(zweig.direction), clean(zweig.freshness_state || zweig.freshness_type), "LEADING CONTEXT"),
      ],
    },
    {
      title: "VOLUME / SELLING PRESSURE",
      description: "Tracks whether downside volume is dominating and whether that pressure is beginning to ease.",
      rows: [
        row("NYSE Up/Down volume (NYUD)", fmt(v.NYUD), "VOLUME", "—", "INTRADAY / DELAYED", "FAST-FAMILY INPUT"),
        row("Nasdaq Up/Down volume (NAUD)", fmt(v.NAUD), "VOLUME", "—", "INTRADAY / DELAYED", "FAST-FAMILY INPUT"),
        row("NYSE Down/Up volume ratio", fmt(v.nyse_down_up_ratio), "SELLING PRESSURE", "—", "INTRADAY / DELAYED", "FAST-FAMILY INPUT"),
        row("Nasdaq Down/Up volume ratio", fmt(v.nasdaq_down_up_ratio), "SELLING PRESSURE", "—", "INTRADAY / DELAYED", "FAST-FAMILY INPUT"),
      ],
    },
    {
      title: "VOLATILITY & TAIL RISK",
      description: "Measures fear intensity, volatility stress and demand for downside protection.",
      rows: [
        row("VIX", fmt(prices?.["^VIX"]?.price), pctChange(prices?.["^VIX"]?.change_pct), "—", clean(prices?.["^VIX"]?.timestamp_et ? "5-MINUTE CONTEXT" : "UNAVAILABLE"), "MARKET CONTEXT"),
        row("VVIX", fmt(vvix.value ?? v.VVIX), clean(vvix.state || v.VVIX_STATE), clean(vvix.direction_vs_prior_close || v.VVIX_DIRECTION), vvix.timestamp_et ? "INTRADAY" : "UNAVAILABLE", "CONTEXT SUPPORT INPUT"),
        row("VVIX recent percentile", pctPoint(vvix.historical_percentile_2m ?? v.VVIX_PERCENTILE_2M), "PERCENTILE", clean(vvix.direction_vs_prior_close || v.VVIX_DIRECTION), "COMPLETED-HISTORY CONTEXT", "CONTEXT"),
        row("Live SKEW proxy ratio", fmt(skew.live_proxy_ratio ?? v.SKEW_LIVE_PROXY_RATIO, 3), "TAIL RISK", clean(skew.direction_vs_prior_snapshot || v.SKEW_DIRECTION), clean(skew.freshness_state || skew.source_mode), "CONTEXT SUPPORT INPUT"),
        row("Live SKEW vol spread", fmt(skew.live_proxy_vol_points ?? v.SKEW_LIVE_PROXY), "TAIL RISK", clean(skew.direction_vs_prior_snapshot || v.SKEW_DIRECTION), clean(skew.freshness_state || skew.source_mode), "CONTEXT"),
        row("Official SKEW", fmt(skew.official_skew_latest_close ?? v.SKEW_OFFICIAL_CLOSE), "OFFICIAL CLOSE", clean(skew.official_skew_direction), "PRIOR CLOSE", "CONTEXT"),
        row("VIX term structure", fmt(vol.current_ratio, 3), clean(vol.state), vol.supportive === true ? "SUPPORTIVE" : vol.supportive === false ? "NOT SUPPORTIVE" : "UNAVAILABLE", clean(vol.freshness_state || vol.freshness_type), "SECONDARY CONFIRMATION"),
      ],
    },
    {
      title: "OPTIONS / SENTIMENT",
      description: "Shows whether options positioning reflects complacency, fear or high fear.",
      rows: [
        row("Equity Put/Call", fmt(options.equity_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY"),
        row("Total Put/Call", fmt(options.total_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY"),
        row("Index Put/Call", fmt(options.index_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY"),
      ],
    },
    {
      title: "RISK APPETITE / CROSS-ASSET",
      description: "Checks whether investors are broadening risk beyond the largest stocks and into credit/smaller companies.",
      rows: [
        row("Risk-Appetite Broadening", `${risk.supportive_components ?? 0}/3 supportive`, clean(risk.state), risk.supportive === true ? "SUPPORTIVE" : "NOT SUPPORTIVE", clean(risk.freshness_state || risk.freshness_type), "SECONDARY CONFIRMATION"),
        row("Equal weight vs SPY (RSP/SPY)", fmt(risk.RSP_SPY, 4), risk.components?.equal_weight_broadening === true ? "CONFIRMING" : "NOT CONFIRMING", clean(risk.RSP_SPY_5d_change != null ? pctChange(risk.RSP_SPY_5d_change) : null), clean(risk.freshness_state || risk.freshness_type), "RISK-APPETITE COMPONENT"),
        row("Small caps vs SPY (IWM/SPY)", fmt(risk.IWM_SPY, 4), risk.components?.small_caps_confirming === true ? "CONFIRMING" : "NOT CONFIRMING", clean(risk.IWM_SPY_5d_change != null ? pctChange(risk.IWM_SPY_5d_change) : null), clean(risk.freshness_state || risk.freshness_type), "RISK-APPETITE COMPONENT"),
        row("High yield vs IG credit (HYG/LQD)", fmt(risk.HYG_LQD, 4), risk.components?.credit_risk_appetite === true ? "CONFIRMING" : "NOT CONFIRMING", clean(risk.HYG_LQD_5d_change != null ? pctChange(risk.HYG_LQD_5d_change) : null), clean(risk.freshness_state || risk.freshness_type), "RISK-APPETITE COMPONENT"),
        row("Credit-Risk Turn", fmt(credit.hyg_lqd_ratio, 4), clean(credit.state), clean(credit.direction), clean(credit.freshness_state || credit.freshness_type), "LEADING CONTEXT"),
      ],
    },
    {
      title: "CONTEXT-SUPPORT TURNS",
      description: "Independent context turns that can help qualify an early re-entry when paired with a fast reversal family.",
      rows: [
        row("MMFD Improving", boolState(context.MMFD_IMPROVING), boolState(context.MMFD_IMPROVING), boolDir(context.MMFD_IMPROVING), "CURRENT SNAPSHOT", "DERIVED CONTEXT INPUT"),
        row("NASI Turning Up", boolState(context.NASI_TURNING_UP), boolState(context.NASI_TURNING_UP), boolDir(context.NASI_TURNING_UP), "CURRENT SNAPSHOT", "DERIVED CONTEXT INPUT"),
        row("VVIX Easing", boolState(context.VVIX_EASING), boolState(context.VVIX_EASING), boolDir(context.VVIX_EASING), "CURRENT SNAPSHOT", "DERIVED CONTEXT INPUT"),
        row("SKEW Narrowing", boolState(context.SKEW_NARROWING), boolState(context.SKEW_NARROWING), boolDir(context.SKEW_NARROWING), "CURRENT SNAPSHOT", "DERIVED CONTEXT INPUT"),
        row("Context-support count", `${u.context_support_count ?? Object.values(context).filter(Boolean).length}/4`, "SUMMARY", "—", "CURRENT SNAPSHOT", "CONTEXT SUMMARY"),
      ],
    },
    {
      title: "EXTENSION / OVERHEAT",
      description: "Descriptive extension flags; they do not override the re-entry trigger.",
      rows: [
        row("MMFD Strong", boolState(extension.MMFD_STRONG), boolState(extension.MMFD_STRONG), boolDir(extension.MMFD_STRONG), "CURRENT SNAPSHOT", "CONTEXT ONLY"),
        row("SPXA20R Strong", boolState(extension.SPXA20R_STRONG), boolState(extension.SPXA20R_STRONG), boolDir(extension.SPXA20R_STRONG), "CURRENT SNAPSHOT", "CONTEXT ONLY"),
        row("NASI Overbought", boolState(extension.NASI_OVERBOUGHT), boolState(extension.NASI_OVERBOUGHT), boolDir(extension.NASI_OVERBOUGHT), "CURRENT SNAPSHOT", "CONTEXT ONLY"),
      ],
    },
    {
      title: "MARKET / PRICE CONTEXT",
      description: "Price context only; these quotes do not create or revoke the RE-ENTRY decision.",
      rows: [
        row("SPY", fmt(prices?.SPY?.price), pctChange(prices?.SPY?.change_pct), "—", prices?.SPY?.timestamp_et ? "5-MINUTE CONTEXT" : "UNAVAILABLE", "MARKET CONTEXT"),
        row("QQQ", fmt(prices?.QQQ?.price), pctChange(prices?.QQQ?.change_pct), "—", prices?.QQQ?.timestamp_et ? "5-MINUTE CONTEXT" : "UNAVAILABLE", "MARKET CONTEXT"),
        row("Market phase", clean(u.market_phase), clean(u.market_phase), "—", u.timestamp_et ? "CANONICAL SNAPSHOT" : "UNAVAILABLE", "ENGINE CONTEXT"),
      ],
    },
    {
      title: "ENGINE STATE",
      description: "Canonical decision and persistent opportunity-window state.",
      rows: [
        row("Cash action", clean(u.deployment_signal || u.decision), clean(u.deployment_signal || u.decision), "—", u.timestamp_et ? "CANONICAL SNAPSHOT" : "UNAVAILABLE", "PRIMARY ENGINE"),
        row("GO EARLY", clean(u.state), clean(u.state), "—", u.timestamp_et ? "CANONICAL SNAPSHOT" : "UNAVAILABLE", "PRIMARY ENGINE"),
        row("Re-entry Window", u.reentry_window_active === true ? "ACTIVE" : u.reentry_window_active === false ? "INACTIVE" : "UNAVAILABLE", u.reentry_window_active === true ? "ACTIVE" : "INACTIVE", "—", "PERSISTENT CONTEXT", "CONTEXT ONLY"),
        row("Window age", u.reentry_window_age_sessions != null ? `${u.reentry_window_age_sessions} sessions` : "UNAVAILABLE", clean(u.reentry_window_research_status), "—", "PERSISTENT CONTEXT", "CONTEXT ONLY"),
        row("Recovery stage", clean(u.recovery_stage), clean(u.recovery_stage), "—", "CANONICAL SNAPSHOT", "DESCRIPTIVE CONTEXT"),
        row("Confirmation strength", clean(u.confirmation_strength), clean(u.confirmation_strength), "—", "CANONICAL SNAPSHOT", "DESCRIPTIVE CONTEXT"),
        row("Trigger time", clean(u.go_triggered_at_et), u.go_latched_for_session === true ? "LATCHED" : "NOT LATCHED", "—", "SAME-SESSION", "PRIMARY ENGINE"),
      ],
    },
  ];

  return <section className="card section-card categorized-board">
    <div className="section-heading">
      <div><span className="kicker">COMPLETE LIVE INDICATOR BOARD</span><h2>Every indicator, one category</h2></div>
      <span className="freshness"><Clock3 size={14}/> {clean(u.timestamp_et || w.snapshot_generated_at_et || v.timestamp_et)}</span>
    </div>
    <p className="section-intro">Each indicator appears under one primary category with its current value, state, direction, freshness and decision role. Missing data stays visible as UNAVAILABLE rather than disappearing.</p>
    <div className="indicator-category-stack">
      {categories.map((category) => <div className="indicator-category" key={category.title}>
        <div className="indicator-category-head"><div><span>{category.title}</span><p>{category.description}</p></div></div>
        <div className="indicator-table" role="table" aria-label={category.title}>
          <div className="indicator-table-row indicator-table-header" role="row">
            <span>Indicator</span><span>Value</span><span>State</span><span>Direction</span><span>Freshness</span><span>Decision role</span>
          </div>
          {category.rows.map((item) => <div className="indicator-table-row" role="row" key={`${category.title}-${item.name}`}>
            <strong>{item.name}</strong>
            <span className="indicator-table-value">{item.value}</span>
            <span className={`status-pill ${stateClass(item.state)}`}>{item.state}</span>
            <span>{item.direction}</span>
            <span>{item.freshness}</span>
            <span className="indicator-role">{item.role}</span>
          </div>)}
        </div>
      </div>)}
    </div>
  </section>;
}
