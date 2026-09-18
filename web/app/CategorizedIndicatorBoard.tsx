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
const boolState = (value: unknown) => value === true ? "ACTIVE" : value === false ? "NOT ACTIVE" : "UNAVAILABLE";
const boolDir = (_value: unknown) => "—";
const clean = (value: unknown) => typeof value === "string" && value ? value.replaceAll("_", " ") : "UNAVAILABLE";
const pcState = (value: unknown) => typeof value !== "number" || !Number.isFinite(value) ? "UNAVAILABLE" : value >= 0.90 ? "HIGH FEAR" : value >= 0.70 ? "FEAR" : value >= 0.50 ? "NORMAL" : "COMPLACENT";

function row(name: string, value: string, state: string, direction: string, freshness: string, role: string, reference?: string): IndicatorRow {
  return { name, reference, value, state, direction, freshness, role };
}

function stateClass(state: string) {
  const s = state.toUpperCase();
  if (s.includes("NOT ACTIVE")) return "neutral";
  if (s.includes("ON") || s.includes("SUPPORT") || s.includes("NORMALIZED") || s.includes("RISING") || s.includes("BROADENING") || s.includes("ACTIVE") || s.includes("DEPLOY")) return "good";
  if (s.includes("OVERSOLD") || s.includes("WASH") || s.includes("FEAR") || s.includes("WEAK") || s.includes("DEFENSIVE") || s.includes("FALL") || s.includes("DOWN") || s.includes("WIDEN") || s.includes("SELLING") || s.includes("HEAVY")) return "warn";
  return "neutral";
}

function decisionBadge(role: string) {
  if (["DECISION INPUT", "FAST-FAMILY INPUT", "CONTEXT SUPPORT INPUT"].includes(role)) return { label: "ENGINE INPUT", tone: "engine" };
  if (["DERIVED TRIGGER", "DERIVED CONTEXT INPUT"].includes(role)) return { label: "ENGINE SIGNAL", tone: "engine" };
  if (["TRIGGER SUMMARY", "CONTEXT SUMMARY", "PRIMARY ENGINE"].includes(role)) return { label: "ENGINE OUTPUT", tone: "engine" };
  return { label: "CONTEXT ONLY", tone: "context" };
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
  const ndxSkew = (lead.ndx_single_stock_skew || {}) as AnyRecord;
  const risk = (sf.risk_appetite || {}) as AnyRecord;
  const vol = (sf.vol_structure || {}) as AnyRecord;
  const thrust = (sf.breadth_thrust || {}) as AnyRecord;
  const options = (sf.options_sentiment || {}) as AnyRecord;
  const equityPcName = options.reading_mode === "INTRADAY_CBOE" ? "Equity Put/Call — Intraday" : "Equity Put/Call — Prior Official Close";

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
        row("Nasdaq-100 Single-Stock Downside Skew", fmt(ndxSkew.three_day_average ?? ndxSkew.raw_average, 3), clean(ndxSkew.state), clean(ndxSkew.direction), clean(ndxSkew.freshness_state || ndxSkew.freshness_type), "LEADING CONTEXT", "1M normalized put/call skew proxy · 3D avg"),
        row("VIX Term Structure", fmt(vol.current_ratio, 3), clean(vol.state), vol.supportive === true ? "SUPPORTIVE" : vol.supportive === false ? "NOT SUPPORTIVE" : "UNAVAILABLE", clean(vol.freshness_state || vol.freshness_type), "SECONDARY CONFIRMATION", "VIX / VIX3M"),
      ],
    },
    {
      title: "OPTIONS SENTIMENT",
      description: "How much fear is showing up in options positioning?",
      rows: [
        row(equityPcName, fmt(options.equity_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY", options.reading_mode === "INTRADAY_CBOE" ? "Cboe current statistics" : "Final daily · T+1"),
        row("Total Put/Call", fmt(options.total_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY"),
        row("Index Put/Call", fmt(options.index_put_call), clean(options.state), clean(options.signal_behavior), clean(options.freshness_state || options.freshness_type), "SENTIMENT OVERLAY"),
        ...(options.reading_mode === "INTRADAY_CBOE" && typeof options.official_daily_equity_put_call === "number" ? [row("Official Daily Equity Put/Call", fmt(options.official_daily_equity_put_call), pcState(options.official_daily_equity_put_call), "—", options.official_daily_observation_date ? `PRIOR CLOSE ${options.official_daily_observation_date} · T+1` : "PRIOR CLOSE · T+1", "SENTIMENT OVERLAY", "CPCE · finalized daily")] : []),
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

  const meanings: Record<string, string> = {
    "S&P 500 Above 20-Day Average": "Shows how many S&P 500 stocks are above their short-term trend. Below 30% is broad enough damage to activate the oversold setup gate.",
    "Market Breadth Above 5-Day Average": "Shows how many stocks are holding above a very short-term trend. Below 30% is a direct RE-ENTRY oversold condition.",
    "Nasdaq Summation Momentum": "Measures how stretched Nasdaq breadth momentum is. Very low readings identify a washed-out internal backdrop.",
    "Nasdaq Summation Fast Trend": "The faster breadth trend used to understand whether Nasdaq internals are starting to turn before the slower trend catches up.",
    "Nasdaq Summation Slow Trend": "The slower breadth trend that provides a steadier reference for whether Nasdaq participation is improving or deteriorating.",
    "NYSE Stocks Above 40-Day Average": t2108.meaning || "Shows how many NYSE stocks remain above their intermediate-term trend. Low readings mean weakness is broad, not isolated to a few stocks.",
    "Nasdaq Stocks Above 5-Day Average": shortBreadth.meaning || "Shows how many Nasdaq stocks have reclaimed their 5-day average. It reacts quickly to an early internal recovery.",
    "Nasdaq Stocks Above 10-Day Average": shortBreadth.meaning || "Shows how many Nasdaq stocks have reclaimed their 10-day average. It is steadier than the 5-day measure and helps confirm participation repair.",
    "Fast Breadth Turn": "Flags a fresh improvement in very short-term breadth after a washout. It is one of the four fast reversal families that can help trigger DEPLOY.",
    "Momentum Turn": "Flags improving NYSE or Nasdaq breadth momentum versus the prior snapshot. It is one of the four fast reversal families.",
    "Net Volume Turn": "Flags improving up/down volume after selling pressure. It looks for buying volume to start repairing before price fully recovers.",
    "Downside Volume Relief": "Flags a meaningful drop in the down/up volume ratio. It looks for selling pressure to release quickly after a washout.",
    "Current Reversal Families": "Counts how many of the four fast reversal families are firing right now.",
    "Recent Reversal Families": "Counts fast reversal families seen within the engine's 30-minute memory window, which is used by the live trigger.",
    "Nasdaq Advances": "Number of Nasdaq stocks trading higher. More advances relative to declines means participation is broadening.",
    "Nasdaq Declines": "Number of Nasdaq stocks trading lower. A large decline count shows weakness is spread across the market.",
    "Nasdaq Advance Share": "The share of Nasdaq issues advancing. Higher participation makes a rebound healthier; low participation means the tape remains defensive.",
    "NYSE Breadth Momentum": "NYMO measures NYSE breadth momentum. The engine watches whether it improves as one input to the Momentum Turn family.",
    "Nasdaq Breadth Momentum": "NAMO measures Nasdaq breadth momentum. The engine watches whether it improves as one input to the Momentum Turn family.",
    "Nasdaq McClellan Oscillator": "Tracks the balance and momentum of Nasdaq advances versus declines. Negative readings show weak internal momentum.",
    "Nasdaq Summation Index": "A slower cumulative breadth trend. It helps describe whether internal participation is broadly improving or deteriorating.",
    "McClellan Momentum Velocity": mcVelocity.meaning || "Measures how quickly Nasdaq breadth momentum is changing, helping expose an early turn before slower breadth measures confirm.",
    "Breadth Participation Thrust": thrust.meaning || "Checks whether advancing stocks are suddenly dominating enough to show broad participation in a rebound.",
    "Zweig Breadth Thrust": zweig.meaning || "Looks for a rapid shift from broad selling to broad participation, a classic sign that market internals have changed character.",
    "NYSE Up/Down Volume": "Compares buying volume with selling volume on the NYSE. Improvement feeds the engine's Net Volume Turn family.",
    "Nasdaq Up/Down Volume": "Compares buying volume with selling volume on Nasdaq. Improvement feeds the engine's Net Volume Turn family.",
    "NYSE Down/Up Volume Ratio": "Shows how strongly downside volume is dominating NYSE volume. A sharp drop from the prior reading can trigger Downside Volume Relief.",
    "Nasdaq Down/Up Volume Ratio": "Shows how strongly downside volume is dominating Nasdaq volume. A sharp drop from the prior reading can trigger Downside Volume Relief.",
    "Market Volatility": "VIX is the market's near-term volatility gauge. It provides fear context but does not directly change the RE-ENTRY decision.",
    "Volatility of Volatility": "VVIX measures stress inside the volatility market itself. Falling VVIX can become an engine context turn showing fear is easing.",
    "VVIX Recent Percentile": "Places today's VVIX reading against its recent history so you can tell whether volatility-of-volatility is unusually high or low.",
    "Live Downside Skew Ratio": "Measures how expensive downside SPX protection is relative to upside protection. Narrowing can become an engine context turn.",
    "Live Downside Skew Spread": "Shows the volatility-point premium investors are paying for downside SPX protection versus upside protection.",
    "Official Cboe SKEW": "Cboe's official tail-risk gauge. Higher readings imply more demand for protection against unusually large downside moves.",
    "Nasdaq-100 Single-Stock Downside Skew": ndxSkew.meaning || "Measures the downside-versus-upside implied-volatility premium across individual Nasdaq-100 stocks. Lower readings mean flatter single-stock skew and less demand for downside hedging. This is a free-data proxy, not Goldman's proprietary series.",
    "VIX Term Structure": vol.meaning || "Compares near-term VIX with longer-dated volatility. A normalized curve suggests stress is less acute, but this does not change DEPLOY.",
    "Equity Put/Call — Intraday": options.meaning || "Current same-session Cboe equity put/call activity. It is intraday and delayed, not the finalized daily CPCE close.",
    "Equity Put/Call — Prior Official Close": options.meaning || "The most recent finalized daily equity put/call reading that was actually available for this session. Final daily CPCE is enforced T+1.",
    "Official Daily Equity Put/Call": "The finalized daily CPCE reading from the prior trading session. A close stamped D is intentionally not usable until D+1, preventing look-ahead.",
    "Total Put/Call": options.meaning || "Combines put and call activity across the options market to show the overall level of defensive positioning.",
    "Index Put/Call": options.meaning || "Shows defensive positioning in index options, which are often used by institutions for portfolio hedging.",
    "Risk-Appetite Broadening": risk.meaning || "Checks whether investors are moving beyond mega-cap leaders into equal-weight stocks, small caps and credit risk.",
    "Equal Weight vs S&P 500": "Compares equal-weight S&P performance with cap-weighted SPY. Improvement suggests the rally is broadening beyond the largest stocks.",
    "Small Caps vs S&P 500": "Compares small caps with SPY. Improvement suggests investors are becoming more willing to own economically sensitive risk.",
    "High Yield vs Investment Grade": "Compares high-yield credit with investment-grade bonds. Improvement suggests credit investors are becoming more comfortable with risk.",
    "Credit-Risk Turn": credit.meaning || "Tracks whether high-yield credit is beginning to outperform investment grade, an early cross-asset sign of improving risk appetite.",
    "MMFD Improving": "Becomes active when MMFD breadth improves versus the prior snapshot. It is one of four context turns that can help qualify an early DEPLOY.",
    "NASI Turning Up": "Becomes active when Nasdaq breadth momentum starts rising. It is one of four engine context turns.",
    "VVIX Easing": "Becomes active when volatility-of-volatility falls, signaling that fear is beginning to calm. It can help qualify an early DEPLOY.",
    "SKEW Narrowing": "Becomes active when downside tail-risk pricing narrows, signaling less demand for crash protection. It can help qualify an early DEPLOY.",
    "Supportive Context Signals": "Counts how many of the four engine context turns are currently supportive.",
    "MMFD Strong": "Flags broad short-term participation after a rebound. It describes extension and does not revoke or create a DEPLOY signal.",
    "SPXA20R Strong": "Flags broad S&P 500 participation above the 20-day average. It describes an extended recovery rather than a re-entry trigger.",
    "NASI Overbought": "Flags strong or overbought Nasdaq breadth momentum. It describes extension and does not alter the trigger.",
    "S&P 500 ETF": "Current SPY price context so the internal signal can be viewed alongside the market's actual move.",
    "Nasdaq-100 ETF": "Current QQQ price context so the internal signal can be viewed alongside the market's actual move.",
    "Market Phase": "Shows whether the snapshot is live/provisional, settling after the close, or final for the session.",
    "Cash Action": "The canonical RE-ENTRY output: HOLD CASH, WATCH or DEPLOY.",
    "Early Re-Entry State": "The engine's tactical state. GO EARLY means the reversal threshold qualified after an oversold reset.",
    "Re-Entry Window": "Persistent context showing that a prior DEPLOY opened a historically favorable re-entry opportunity. It does not create a new signal.",
    "Window Age": "How many observed market sessions have passed since the RE-ENTRY window opened.",
    "Recovery Stage": "Describes how far the rebound has progressed after DEPLOY. It is descriptive and cannot change the trigger.",
    "Confirmation Strength": "Summarizes how broad current confirmation is after DEPLOY. It is descriptive, not a separate decision rule.",
    "Trigger Time": "Shows when GO EARLY first qualified during the session. Once triggered, the same-day DEPLOY decision remains latched through the close.",
  };

  const oversoldCount = [
    typeof v.SPXA20R === "number" && v.SPXA20R < 30,
    typeof v.MMFD === "number" && v.MMFD < 30,
    typeof v.NASI_RSI === "number" && v.NASI_RSI < 30,
  ].filter(Boolean).length;
  const currentFastCount = Number(u.confirmation_components?.current_fast_family_count ?? w.turn_family_count ?? 0);
  const contextCount = Number(u.context_support_count ?? Object.values(context).filter(Boolean).length);
  const extensionCount = Number(u.extension_signal_count ?? Object.values(extension).filter(Boolean).length);

  function categoryState(title: string) {
    switch (title) {
      case "CORE SETUP": return { label: `${oversoldCount}/3 OVERSOLD`, tone: oversoldCount ? "warn" : "neutral" };
      case "REVERSAL TRIGGERS": return { label: `${currentFastCount}/4 ACTIVE`, tone: currentFastCount >= 2 ? "good" : currentFastCount ? "neutral" : "warn" };
      case "BREADTH & PARTICIPATION": return { label: advanceShare != null && advanceShare >= 50 ? "BROADENING" : "WEAK", tone: advanceShare != null && advanceShare >= 50 ? "good" : "warn" };
      case "SELLING PRESSURE": {
        const worst = Math.max(Number(v.nyse_down_up_ratio || 0), Number(v.nasdaq_down_up_ratio || 0));
        return { label: worst >= 2 ? "HEAVY" : worst >= 1 ? "ELEVATED" : "EASING", tone: worst >= 1 ? "warn" : "good" };
      }
      case "VOLATILITY & TAIL RISK": {
        const rising = clean(vvix.direction_vs_prior_close || v.VVIX_DIRECTION) === "RISING" || clean(skew.direction_vs_prior_snapshot || v.SKEW_DIRECTION) === "WIDENING";
        return { label: rising ? "RISING STRESS" : "STABLE / EASING", tone: rising ? "warn" : "good" };
      }
      case "OPTIONS SENTIMENT": return { label: clean(options.state), tone: stateClass(clean(options.state)) };
      case "RISK APPETITE": return { label: clean(risk.state), tone: risk.supportive === true ? "good" : "neutral" };
      case "CONTEXT TURNS": return { label: `${contextCount}/4 SUPPORTIVE`, tone: contextCount >= 2 ? "good" : contextCount ? "neutral" : "warn" };
      case "EXTENSION / OVERHEAT": return { label: `${extensionCount}/3 EXTENDED`, tone: extensionCount >= 2 ? "warn" : "neutral" };
      case "MARKET CONTEXT": return { label: "PRICE CONTEXT", tone: "neutral" };
      case "ENGINE STATE": return { label: clean(u.deployment_signal || u.decision), tone: stateClass(clean(u.deployment_signal || u.decision)) };
      default: return { label: "CURRENT", tone: "neutral" };
    }
  }

  return <section className="card section-card categorized-board">
    <div className="section-heading indicator-board-heading">
      <div>
        <span className="kicker">LIVE MARKET INTERNALS</span>
        <h2>What is the market telling us?</h2>
        <p className="indicator-board-deck">Every indicator is translated into plain English and clearly marked by whether it can affect RE-ENTRY.</p>
      </div>
      <span className="freshness"><Clock3 size={14}/> {clean(u.timestamp_et || w.snapshot_generated_at_et || v.timestamp_et)}</span>
    </div>

    <div className="indicator-role-legend" aria-label="Indicator decision roles">
      <div><span className="decision-badge engine">ENGINE</span><p>Inputs, signals or outputs that participate in WATCH / DEPLOY.</p></div>
      <div><span className="decision-badge context">CONTEXT ONLY</span><p>Helps explain the market, but cannot change the RE-ENTRY signal.</p></div>
    </div>

    <div className="indicator-category-stack">
      {categories.map((category) => {
        const summary = categoryState(category.title);
        return <section className="indicator-category" key={category.title}>
          <div className="indicator-category-head">
            <div><span>{category.title}</span><p>{category.description}</p></div>
            <strong className={`category-state ${summary.tone}`}>{summary.label}</strong>
          </div>
          <div className="indicator-card-grid">
            {category.rows.map((item) => {
              const badge = decisionBadge(item.role);
              return <article className={`indicator-readout ${badge.tone}`} key={`${category.title}-${item.name}`}>
                <div className="indicator-readout-top">
                  <div className="indicator-name-wrap">
                    <strong>{item.name}</strong>
                    {item.reference ? <small>{item.reference}</small> : null}
                  </div>
                  <span className={`status-pill ${stateClass(item.state)}`}>{item.state}</span>
                </div>
                <div className="indicator-reading">{item.value}</div>
                {item.direction !== "—" && item.direction !== "UNAVAILABLE" ? <div className="indicator-direction">{item.direction}</div> : null}
                <p className="indicator-meaning"><b>What it means:</b> {meanings[item.name] || "Provides additional market context for interpreting the current RE-ENTRY environment."}</p>
                <div className="indicator-decision-row">
                  <span className={`decision-badge ${badge.tone}`}>{badge.label}</span>
                  <span className="indicator-technical-role">{item.role}</span>
                </div>
                <div className="indicator-meta"><span>{item.freshness}</span></div>
              </article>;
            })}
          </div>
        </section>;
      })}
    </div>
  </section>;
}
