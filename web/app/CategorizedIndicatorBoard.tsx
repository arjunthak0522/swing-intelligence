import { Clock3 } from "lucide-react";
import type { WashoutSnapshot } from "../lib/reentry";

type AnyRecord = Record<string, any>;

type IndicatorRow = {
  name: string;
  reference?: string;
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

function row(name: string, value: string, state: string, direction: string, freshness: string, role: string, reference?: string): IndicatorRow {
  return { name, reference, value, state, direction, freshness, role };
}

function stateClass(state: string) {
  const s = state.toUpperCase();
  if (s.includes("ON") || s.includes("SUPPORT") || s.includes("NORMALIZED") || s.includes("RISING") || s.includes("BROADENING") || s.includes("ACTIVE")) return "good";
  if (s.includes("OVERSOLD") || s.includes("WASH") || s.includes("FEAR") || s.includes("WEAK") || s.includes("DEFENSIVE") || s.includes("FALL") || s.includes("DOWN") || s.includes("WIDEN") || s.includes("SELLING")) return "warn";
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
      title: "CORE SETUP",
      description: "Is the market stretched enough for a re-entry setup to matter?",
      rows: [
        row("S&P 500 Above 20-Day Average", pctPoint(v.SPXA20R), v.SPXA20R != null && v.SPXA20R <= 30 ? "OVERSOLD" : "NORMAL", "—", "INTRADAY / DELAYED", "DECISION INPUT", "SPXA20R"),
        row("Market Breadth Above 5-Day Average", pctPoint(v.MMFD), clean(v.MMFD_STATE || w.mmfd_live?.state), "—", w.mmfd_live?.timestamp_et ? "INTRADAY" : "UNAVAILABLE", "DECISION INPUT", "MMFD"),
        row("Nasdaq Summation Momentum", fmt(v.NASI_RSI), v.NASI_RSI != null && v.NASI_RSI < 30 ? "OVERSOLD" : "NORMAL", clean(v.NASI_DIRECTION), "INTRADAY / PROVISIONAL", "DECISION INPUT", "NASI+ RSI"),
        row("Nasdaq Summation Fast Trend", fmt(v.NASI_EMA4), "REFERENCE", "—", "INTRADAY / PROVISIONAL", "SETUP CONTEXT", "NASI+ EMA4"),
        row("Nasdaq Summation Slow Trend", fmt(v.NASI_EMA10), "REFERENCE", "—", "INTRADAY / PROVISIONAL", "SETUP CONTEXT", "NASI+ EMA10"),
        row("NYSE Stocks Above 40-Day Average", pctPoint(t2108.value ?? v.T2108), clean(t2108.state), clean(t2108.direction), clean(t2108.freshness_state || t2108.freshness_type), "CONTEXT ONLY", "T2108-style breadth"),
        row("Nasdaq Stocks Above 5-Day Average", pctPoint(shortBreadth.above_5dma_pct), clean(shortBreadth.state), clean(shortBreadth.direction), clean(shortBreadth.freshness_state || shortBreadth.freshness_type), "LEADING CONTEXT", "Short-term Nasdaq breadth"),
        row("Nasdaq Stocks Above 10-Day Average", pctPoint(shortBreadth.above_10dma_pct), clean(shortBreadth.state), clean(shortBreadth.direction), clean(shortBreadth.freshness_state || shortBreadth.freshness_type), "LEADING CONTEXT", "Short-term Nasdaq breadth"),
      ],
    },
    {
      title: "REVERSAL TRIGGERS",
      description: "Are the first signs of an actual turn appearing?",
      rows: [
        row("Fast Breadth Turn", boolState(fastNow.FAST_BREADTH_TURN ?? fastNow.fast_breadth_turn), boolState(fastNow.FAST_BREADTH_TURN ?? fastNow.fast_breadth_turn), boolDir(fastNow.FAST_BREADTH_TURN ?? fastNow.fast_breadth_turn), "CURRENT SNAPSHOT", "DERIVED TRIGGER"),
        row("Momentum Turn", boolState(fastNow.MOMENTUM_TURN ?? fastNow.momentum_turn), boolState(fastNow.MOMENTUM_TURN ?? fastNow.momentum_turn), boolDir(fastNow.MOMENTUM_TURN ?? fastNow.momentum_turn), "CURRENT SNAPSHOT", "DERIVED TRIGGER"),
        row("Net Volume Turn", boolState(fastNow.NET_VOLUME_TURN ?? fastNow.net_volume_turn), boolState(fastNow.NET_VOLUME_TURN ?? fastNow.net_volume_turn), boolDir(fastNow.NET_VOLUME_TURN ?? fastNow.net_volume_turn), "CURRENT SNAPSHOT", "DERIVED TRIGGER"),
        row("Downside Volume Relief", boolState(fastNow.DOWN_UP_RATIO_RELIEF ?? fastNow.down_up_ratio_relief), boolState(fastNow.DOWN_UP_RATIO_RELIEF ?? fastNow.down_up_ratio_relief), boolDir(fastNow.DOWN_UP_RATIO_RELIEF ?? fastNow.down_up_ratio_relief), "CURRENT SNAPSHOT", "DERIVED TRIGGER", "Down/Up Ratio Relief"),
        row("Current Reversal Families", `${u.confirmation_components?.current_fast_family_count ?? w.turn_family_count ?? 0}/4`, "CURRENT", "—", "CURRENT SNAPSHOT", "TRIGGER SUMMARY"),
        row("Recent Reversal Families", `${u.fast_family_count ?? Object.values(fastRecent).filter(Boolean).length}/4`, "MEMORY", "—", "30-MINUTE MEMORY", "TRIGGER SUMMARY"),
      ],
    },
    {
      title: "BREADTH & PARTICIPATION",
      description: "Is the move broadening across stocks, or still narrow and fragile?",
      rows: [
        row("Nasdaq Advances", fmt(v.NAADV ?? nasi.live_advances, 0), "BREADTH", "—", "INTRADAY / DELAYED", "CONTEXT"),
        row("Nasdaq Declines", fmt(v.NADEC ?? nasi.live_declines, 0), "BREADTH", "—", "INTRADAY / DELAYED", "CONTEXT"),
        row("Nasdaq Advance Share", pctPoint(advanceShare), clean(thrust.state), "—", clean(thrust.freshness_state || thrust.freshness_type), "SECONDARY CONFIRMATION"),
        row("NYSE Breadth Momentum", fmt(v.NYMO), "MOMENTUM", "—", "PRIOR CLOSE WHEN LIVE FEED UNAVAILABLE", "FAST-FAMILY INPUT", "NYMO"),
        row("Nasdaq Breadth Momentum", fmt(v.NAMO), "MOMENTUM", "—", "PRIOR CLOSE WHEN LIVE FEED UNAVAILABLE", "FAST-FAMILY INPUT", "NAMO"),
        row("Nasdaq McClellan Oscillator", fmt(nasi.mcclellan_oscillator), "BREADTH MOMENTUM", clean(v.NASI_DIRECTION), "INTRADAY / PROVISIONAL", "CONTEXT"),
        row("Nasdaq Summation Index", fmt(nasi.summation_index), "BREADTH TREND", clean(v.NASI_DIRECTION), "INTRADAY / PROVISIONAL", "CONTEXT"),
        row("McClellan Momentum Velocity", fmt(mcVelocity.change_1_session), clean(mcVelocity.state), clean(mcVelocity.direction), clean(mcVelocity.freshness_state || mcVelocity.freshness_type), "LEADING CONTEXT", "McClellan Velocity"),
        row("Breadth Participation Thrust", pctPoint(advanceShare), clean(thrust.state), "—", clean(thrust.freshness_state || thrust.freshness_type), "SECONDARY CONFIRMATION"),
        row("Zweig Breadth Thrust", zweig.triggered === true ? "TRIGGERED" : zweig.triggered === false ? "NOT TRIGGERED" : "UNAVAILABLE", clean(zweig.state), clean(zweig.direction), clean(zweig.freshness_state || zweig.freshness_type), "LEADING CONTEXT"),
      ],
    },
    {
      title: "SELLING PRESSURE",
      description: "Is downside volume still dominating, or starting to release?",
      rows: [
        row("NYSE Up/Down Volume", fmt(v.NYUD), "VOLUME", "—", "INTRADAY / DELAYED", "FAST-FAMILY INPUT", "NYUD"),
        row("Nasdaq Up/Down Volume", fmt(v.NAUD), "VOLUME", "—", "INTRADAY / DELAYED", "FAST-FAMILY INPUT", "NAUD"),
        row("NYSE Down/Up Volume Ratio", fmt(v.nyse_down_up_ratio), "SELLING PRESSURE", "—", "INTRADAY / DELAYED", "FAST-FAMILY INPUT"),
        row("Nasdaq Down/Up Volume Ratio", fmt(v.nasdaq_down_up_ratio), "SELLING PRESSURE", "—", "INTRADAY / DELAYED", "FAST-FAMILY INPUT"),
      ],
    },
    {
      title: "VOLATILITY & TAIL RISK",
      description: "Is fear calming down, or getting more expensive?",
      rows: [
        row("Market Volatility", fmt(prices?.["^VIX"]?.price), pctChange(prices?.["^VIX"]?.change_pct), "—", prices?.["^VIX"]?.timestamp_et ? "5-MINUTE CONTEXT" : "UNAVAILABLE", "MARKET CONTEXT", "VIX"),
        row("Volatility of Volatility", fmt(vvix.value ?? v.VVIX), clean(vvix.state || v.VVIX_STATE), clean(vvix.direction_vs_prior_close || v.VVIX_DIRECTION), vvix.timestamp_et ? "INTRADAY" : "UNAVAILABLE", "CONTEXT SUPPORT INPUT", "VVIX"),
        row("VVIX Recent Percentile", pctPoint(vvix.historical_percentile_2m ?? v.VVIX_PERCENTILE_2M), "PERCENTILE", clean(vvix.direction_vs_prior_close || v.VVIX_DIRECTION), "COMPLETED-HISTORY CONTEXT", "CONTEXT"),
        row("Live Downside Skew Ratio", fmt(skew.live_proxy_ratio ?? v.SKEW_LIVE_PROXY_RATIO, 3), "TAIL RISK", clean(skew.direction_vs_prior_snapshot || v.SKEW_DIRECTION), clean(skew.freshness_state || skew.source_mode), "CONTEXT SUPPORT INPUT", "SKEW proxy"),
        row("Live Downside Skew Spread", fmt(skew.live_proxy_vol_points ?? v.SKEW_LIVE_PROXY), "TAIL RISK", clean(skew.direction_vs_prior_snapshot || v.SKEW_DIRECTION), clean(skew.freshness_state || skew.source_mode), "CONTEXT", "SKEW vol spread"),
        row("Official Cboe SKEW", fmt(skew.official_skew_latest_close ?? v.SKEW_OFFICIAL_CLOSE), "OFFICIAL CLOSE", clean(skew.official_skew_direction), "PRIOR CLOSE", "CONTEXT", "SKEW"),
        row("VIX Term Structure", fmt(vol.current_ratio, 3), clean(vol.state), vol.supportive === true ? "SUPPORTIVE" : vol.supportive === false ? "NOT SUPPORTIVE" : "UNAVAILABLE", clean(vol.freshness_state || vol.freshness_type), "SECONDARY CONFIRMATION", "VIX / VIX3M"),
      ],
    },
    {
      title: "OPTIONS SENTIMENT",
      description: "How much fear is showing up in options positioning?",
      rows: [
        row("Equity Put/Call", fmt(options.equity_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY"),
        row("Total Put/Call", fmt(options.total_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY"),
        row("Index Put/Call", fmt(options.index_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY"),
      ],
    },
    {
      title: "RISK APPETITE",
      description: "Are investors moving back into broader and riskier assets?",
      rows: [
        row("Risk-Appetite Broadening", `${risk.supportive_components ?? 0}/3 supportive`, clean(risk.state), risk.supportive === true ? "SUPPORTIVE" : "NOT SUPPORTIVE", clean(risk.freshness_state || risk.freshness_type), "SECONDARY CONFIRMATION"),
        row("Equal Weight vs S&P 500", fmt(risk.RSP_SPY, 4), risk.components?.equal_weight_broadening === true ? "CONFIRMING" : "NOT CONFIRMING", risk.RSP_SPY_5d_change != null ? pctChange(risk.RSP_SPY_5d_change) : "UNAVAILABLE", clean(risk.freshness_state || risk.freshness_type), "RISK-APPETITE COMPONENT", "RSP / SPY"),
        row("Small Caps vs S&P 500", fmt(risk.IWM_SPY, 4), risk.components?.small_caps_confirming === true ? "CONFIRMING" : "NOT CONFIRMING", risk.IWM_SPY_5d_change != null ? pctChange(risk.IWM_SPY_5d_change) : "UNAVAILABLE", clean(risk.freshness_state || risk.freshness_type), "RISK-APPETITE COMPONENT", "IWM / SPY"),
        row("High Yield vs Investment Grade", fmt(risk.HYG_LQD, 4), risk.components?.credit_risk_appetite === true ? "CONFIRMING" : "NOT CONFIRMING", risk.HYG_LQD_5d_change != null ? pctChange(risk.HYG_LQD_5d_change) : "UNAVAILABLE", clean(risk.freshness_state || risk.freshness_type), "RISK-APPETITE COMPONENT", "HYG / LQD"),
        row("Credit-Risk Turn", fmt(credit.hyg_lqd_ratio, 4), clean(credit.state), clean(credit.direction), clean(credit.freshness_state || credit.freshness_type), "LEADING CONTEXT", "HYG / LQD"),
      ],
    },
    {
      title: "CONTEXT TURNS",
      description: "Extra signs that the oversold setup is beginning to repair.",
      rows: [
        row("MMFD Improving", boolState(context.MMFD_IMPROVING), boolState(context.MMFD_IMPROVING), boolDir(context.MMFD_IMPROVING), "CURRENT SNAPSHOT", "DERIVED CONTEXT INPUT"),
        row("NASI Turning Up", boolState(context.NASI_TURNING_UP), boolState(context.NASI_TURNING_UP), boolDir(context.NASI_TURNING_UP), "CURRENT SNAPSHOT", "DERIVED CONTEXT INPUT"),
        row("VVIX Easing", boolState(context.VVIX_EASING), boolState(context.VVIX_EASING), boolDir(context.VVIX_EASING), "CURRENT SNAPSHOT", "DERIVED CONTEXT INPUT"),
        row("SKEW Narrowing", boolState(context.SKEW_NARROWING), boolState(context.SKEW_NARROWING), boolDir(context.SKEW_NARROWING), "CURRENT SNAPSHOT", "DERIVED CONTEXT INPUT"),
        row("Supportive Context Signals", `${u.context_support_count ?? Object.values(context).filter(Boolean).length}/4`, "SUMMARY", "—", "CURRENT SNAPSHOT", "CONTEXT SUMMARY"),
      ],
    },
    {
      title: "EXTENSION / OVERHEAT",
      description: "Is the rebound becoming stretched again?",
      rows: [
        row("MMFD Strong", boolState(extension.MMFD_STRONG), boolState(extension.MMFD_STRONG), boolDir(extension.MMFD_STRONG), "CURRENT SNAPSHOT", "CONTEXT ONLY"),
        row("SPXA20R Strong", boolState(extension.SPXA20R_STRONG), boolState(extension.SPXA20R_STRONG), boolDir(extension.SPXA20R_STRONG), "CURRENT SNAPSHOT", "CONTEXT ONLY"),
        row("NASI Overbought", boolState(extension.NASI_OVERBOUGHT), boolState(extension.NASI_OVERBOUGHT), boolDir(extension.NASI_OVERBOUGHT), "CURRENT SNAPSHOT", "CONTEXT ONLY"),
      ],
    },
    {
      title: "MARKET CONTEXT",
      description: "Where SPY and QQQ are trading right now.",
      rows: [
        row("S&P 500 ETF", fmt(prices?.SPY?.price), pctChange(prices?.SPY?.change_pct), "—", prices?.SPY?.timestamp_et ? "5-MINUTE CONTEXT" : "UNAVAILABLE", "MARKET CONTEXT", "SPY"),
        row("Nasdaq-100 ETF", fmt(prices?.QQQ?.price), pctChange(prices?.QQQ?.change_pct), "—", prices?.QQQ?.timestamp_et ? "5-MINUTE CONTEXT" : "UNAVAILABLE", "MARKET CONTEXT", "QQQ"),
        row("Market Phase", clean(u.market_phase), clean(u.market_phase), "—", u.timestamp_et ? "CANONICAL SNAPSHOT" : "UNAVAILABLE", "ENGINE CONTEXT"),
      ],
    },
    {
      title: "ENGINE STATE",
      description: "The actual RE-ENTRY decision and where the recovery currently stands.",
      rows: [
        row("Cash Action", clean(u.deployment_signal || u.decision), clean(u.deployment_signal || u.decision), "—", u.timestamp_et ? "CANONICAL SNAPSHOT" : "UNAVAILABLE", "PRIMARY ENGINE"),
        row("Early Re-Entry State", clean(u.state), clean(u.state), "—", u.timestamp_et ? "CANONICAL SNAPSHOT" : "UNAVAILABLE", "PRIMARY ENGINE", "GO EARLY"),
        row("Re-Entry Window", u.reentry_window_active === true ? "ACTIVE" : u.reentry_window_active === false ? "INACTIVE" : "UNAVAILABLE", u.reentry_window_active === true ? "ACTIVE" : "INACTIVE", "—", "PERSISTENT CONTEXT", "CONTEXT ONLY"),
        row("Window Age", u.reentry_window_age_sessions != null ? `${u.reentry_window_age_sessions} sessions` : "UNAVAILABLE", clean(u.reentry_window_research_status), "—", "PERSISTENT CONTEXT", "CONTEXT ONLY"),
        row("Recovery Stage", clean(u.recovery_stage), clean(u.recovery_stage), "—", "CANONICAL SNAPSHOT", "DESCRIPTIVE CONTEXT"),
        row("Confirmation Strength", clean(u.confirmation_strength), clean(u.confirmation_strength), "—", "CANONICAL SNAPSHOT", "DESCRIPTIVE CONTEXT"),
        row("Trigger Time", clean(u.go_triggered_at_et), u.go_latched_for_session === true ? "LATCHED" : "NOT LATCHED", "—", "SAME-SESSION", "PRIMARY ENGINE"),
      ],
    },
  ];

  return <section className="card section-card categorized-board">
    <div className="section-heading indicator-board-heading">
      <div>
        <span className="kicker">LIVE MARKET INTERNALS</span>
        <h2>What is the market telling us?</h2>
        <p className="indicator-board-deck">Every indicator is here, but organized by the question it answers.</p>
      </div>
      <span className="freshness"><Clock3 size={14}/> {clean(u.timestamp_et || w.snapshot_generated_at_et || v.timestamp_et)}</span>
    </div>

    <div className="indicator-category-stack">
      {categories.map((category) => <section className="indicator-category" key={category.title}>
        <div className="indicator-category-head">
          <span>{category.title}</span>
          <p>{category.description}</p>
        </div>
        <div className="indicator-card-grid">
          {category.rows.map((item) => <article className="indicator-readout" key={`${category.title}-${item.name}`}>
            <div className="indicator-readout-top">
              <div className="indicator-name-wrap">
                <strong>{item.name}</strong>
                {item.reference ? <small>{item.reference}</small> : null}
              </div>
              <span className={`status-pill ${stateClass(item.state)}`}>{item.state}</span>
            </div>
            <div className="indicator-reading">{item.value}</div>
            {item.direction !== "—" && item.direction !== "UNAVAILABLE" ? <div className="indicator-direction">{item.direction}</div> : null}
            <div className="indicator-meta"><span>{item.freshness}</span><span>{item.role}</span></div>
          </article>)}
        </div>
      </section>)}
    </div>
  </section>;
}
