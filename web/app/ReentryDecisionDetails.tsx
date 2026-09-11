import { CircleAlert } from "lucide-react";
import type { HistoricalContextMetric, WashoutSnapshot } from "../lib/reentry";

const finite = (value?: number | null) => typeof value === "number" && Number.isFinite(value);
const plain = (value?: number | null, digits = 1) => finite(value) ? Number(value).toFixed(digits) : "UNAVAILABLE";
const signed = (value?: number | null, digits = 1) => finite(value) ? `${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(digits)}` : "UNAVAILABLE";
const percentile = (value?: number | null) => finite(value) ? `${Math.round(Number(value))}th percentile` : "Percentile unavailable";

function spxaState(value?: number | null) {
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) < 10) return "EXTREME OVERSOLD";
  if (Number(value) < 30) return "OVERSOLD";
  if (Number(value) < 50) return "WEAK";
  if (Number(value) < 70) return "NORMAL";
  return "STRONG";
}

function mmfdState(value?: number | null, supplied?: string | null) {
  if (supplied) return supplied.replaceAll("_", " ");
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) < 15) return "EXTREME OVERSOLD";
  if (Number(value) < 30) return "OVERSOLD";
  if (Number(value) < 50) return "WEAK";
  if (Number(value) <= 70) return "NORMAL";
  if (Number(value) <= 85) return "STRONG";
  return "EXTREME OVERBOUGHT";
}

function momentumState(value?: number | null) {
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) <= -100) return "STRETCHED NEGATIVE";
  if (Number(value) < 0) return "NEGATIVE";
  if (Number(value) < 100) return "POSITIVE";
  return "STRETCHED POSITIVE";
}

function nasiState(value?: number | null) {
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) < 10) return "EXTREME OVERSOLD";
  if (Number(value) < 20) return "VERY OVERSOLD";
  if (Number(value) < 30) return "OVERSOLD";
  if (Number(value) > 90) return "EXTREME OVERBOUGHT";
  if (Number(value) > 80) return "VERY OVERBOUGHT";
  if (Number(value) > 70) return "OVERBOUGHT";
  return "NORMAL";
}

function percentileState(value?: number | null, highLabel = "ELEVATED") {
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) >= 95) return "EXTREME";
  if (Number(value) >= 80) return "STRETCHED";
  if (Number(value) >= 60) return highLabel;
  return "NORMAL";
}

function signState(value?: number | null) {
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) > 0) return "ADVANCING VOLUME LEADS";
  if (Number(value) < 0) return "DECLINING VOLUME LEADS";
  return "BALANCED";
}

function ratioState(value?: number | null) {
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) > 1) return "DOWN VOLUME LEADS";
  if (Number(value) < 1) return "UP VOLUME LEADS";
  return "BALANCED";
}

function stateClass(value: string) {
  const v = value.toUpperCase();
  if (v.includes("EXTREME") || v.includes("OVERSOLD") || v.includes("DECLINING") || v.includes("DOWN VOLUME") || v.includes("SELLING")) return "bad-text";
  if (v.includes("STRETCHED") || v.includes("WEAK") || v.includes("ELEVATED") || v === "NEGATIVE") return "warn";
  if (v.includes("STRONG") || v.includes("ADVANCING") || v.includes("UP VOLUME") || v.includes("BUYING") || v === "POSITIVE") return "good-text";
  return "muted";
}

function directionClass(value?: string | null) {
  const v = (value || "").toUpperCase();
  if (["RISING", "WIDENING", "DETERIORATING"].includes(v)) return "bad-text";
  if (["FALLING", "NARROWING", "IMPROVING", "EASING", "RELIEF"].includes(v)) return "good-text";
  return "muted";
}

function historyBenchmark(metric: HistoricalContextMetric | undefined, fallback: string) {
  if (!metric) return fallback;
  if (metric.reliable && finite(metric.percentile)) return `${percentile(metric.percentile)} of validated captured history · ${metric.state || "NORMAL"}`;
  return `History building: ${metric.session_count ?? 0}/${metric.minimum_reliable_sessions ?? 20} market sessions · ${fallback}`;
}

function historyDetail(metric: HistoricalContextMetric | undefined) {
  if (!metric) return undefined;
  if (metric.reliable && finite(metric.percentile)) {
    return `${metric.methodology || "Empirical captured history"} · ${metric.history_start_date || "-"} to ${metric.history_end_date || "-"}`;
  }
  return `Percentile withheld until the reliability gate is met. ${metric.methodology || "Captured history is still accumulating."}`;
}

function historyState(metric: HistoricalContextMetric | undefined, fallback: string) {
  return metric?.reliable && metric.state ? metric.state : fallback;
}

function MetricCard({ name, symbol, value, benchmark, state, direction, interpretation, detail }: {
  name: string;
  symbol: string;
  value: string;
  benchmark: string;
  state: string;
  direction?: string | null;
  interpretation: string;
  detail?: string;
}) {
  const dir = direction?.replaceAll("_", " ") || "DIRECTION UNAVAILABLE";
  return <div className="indicator-card">
    <div className="indicator-title"><div><b>{name}</b><small>{symbol}</small></div></div>
    <strong className="indicator-value">{value}</strong>
    <div className="indicator-badges"><span className={stateClass(state)}>{state}</span><span className={directionClass(direction)}>{dir}</span></div>
    <div className="indicator-reference">{benchmark}</div>
    {detail ? <div className="indicator-detail">{detail}</div> : null}
    <p>{interpretation}</p>
  </div>;
}

export default function ReentryDecisionDetails({ washout }: { washout: WashoutSnapshot }) {
  const u = washout.unified_engine;
  const w = washout.values;
  if (!u || !w) return <section className="card section-card"><div className="notice"><CircleAlert size={16} /> RE-ENTRY ENGINE UNAVAILABLE</div></section>;

  const fast = u.fast_families || {
    FAST_BREADTH_TURN: washout.families?.fast_breadth_turn ?? false,
    MOMENTUM_TURN: washout.families?.momentum_turn ?? false,
    NET_VOLUME_TURN: washout.families?.net_volume_turn ?? false,
    DOWN_UP_RATIO_RELIEF: washout.families?.down_up_ratio_relief ?? false,
  };
  const context = u.context_support || {};
  const fastRows = [
    ["Fast breadth", fast.FAST_BREADTH_TURN],
    ["Breadth momentum", fast.MOMENTUM_TURN],
    ["Advance/decline volume", fast.NET_VOLUME_TURN],
    ["Selling intensity relief", fast.DOWN_UP_RATIO_RELIEF],
  ] as const;
  const contextRows = [
    ["MMFD improving", context.MMFD_IMPROVING],
    ["NASI+ turning upward", context.NASI_TURNING_UP],
    ["VVIX easing", context.VVIX_EASING],
    ["SKEW narrowing", context.SKEW_NARROWING],
  ] as const;
  const vvix = washout.vvix_live;
  const skew = washout.skew_live;
  const mmfd = washout.mmfd_live;
  const hist = washout.historical_context?.metrics || {};
  const vvixChange = finite(vvix?.change_points_vs_prior_close)
    ? vvix?.change_points_vs_prior_close
    : finite(w.VVIX) && finite(w.VVIX_PRIOR_CLOSE) ? Number(w.VVIX) - Number(w.VVIX_PRIOR_CLOSE) : null;
  const vvixPct = vvix?.historical_percentile_2y ?? w.VVIX_PERCENTILE_2Y;
  const officialSkewPct = skew?.official_skew_percentile_2y ?? w.SKEW_OFFICIAL_PERCENTILE_2Y;
  const officialSkew = skew?.official_skew_latest_close ?? w.SKEW_OFFICIAL_CLOSE;
  const officialDate = skew?.official_skew_date || "date unavailable";
  const liveSkew = skew?.live_proxy_vol_points ?? w.SKEW_LIVE_PROXY;
  const liveSkewRatio = skew?.live_proxy_ratio ?? w.SKEW_LIVE_PROXY_RATIO;
  const liveSkewMode = skew?.source_mode || "SOURCE MODE UNAVAILABLE";
  const snapshotTime = u.timestamp_et || washout.snapshot_generated_at_et || w.timestamp_et || "UNAVAILABLE";

  return <>
    <style>{`
      .family-section{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:14px 0 20px}.family-panel{border:1px solid var(--line);border-radius:14px;padding:14px;background:rgba(255,255,255,.3)}.family-panel h3{margin:0 0 10px;font-size:13px}.family-row{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 0;border-top:1px solid var(--line);font-size:11px}.family-row:first-of-type{border-top:0}.family-row b{font-size:9px;letter-spacing:.04em}.indicator-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.indicator-card{border:1px solid var(--line);border-radius:14px;padding:15px;background:rgba(255,255,255,.32)}.indicator-title{display:flex;justify-content:space-between;gap:10px}.indicator-title b{font-size:11px}.indicator-title small{display:block;color:var(--muted);font-size:9px;margin-top:2px}.indicator-value{display:block;font-size:24px;margin:10px 0 7px}.indicator-badges{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:9px}.indicator-badges span{border:1px solid var(--line);border-radius:999px;padding:4px 7px;font-size:8px;font-weight:900;letter-spacing:.05em}.indicator-reference,.indicator-detail{font-size:9px;line-height:1.45;color:var(--muted)}.indicator-detail{margin-top:4px;color:#454840}.indicator-card p{font-size:10px;line-height:1.5;margin:8px 0 0}.engine-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.engine-meta span{font-size:9px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 8px}.warn{color:var(--amber)}@media(max-width:900px){.indicator-grid{grid-template-columns:1fr 1fr}}@media(max-width:680px){.family-section,.indicator-grid{grid-template-columns:1fr}}
    `}</style>
    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">REVERSAL EVIDENCE</span><h2>What has actually turned?</h2></div></div>
      <div className="family-section">
        <div className="family-panel"><h3>Fast reversal families - {u.fast_family_count ?? 0}/4</h3>{fastRows.map(([name, on]) => <div className="family-row" key={name}><span>{name}</span><b className={on ? "good-text" : "muted"}>{on ? "TURNED" : "NOT YET"}</b></div>)}</div>
        <div className="family-panel"><h3>Context support - {u.context_support_count ?? 0}/4</h3>{contextRows.map(([name, on]) => <div className="family-row" key={name}><span>{name}</span><b className={on ? "good-text" : "muted"}>{on ? "YES" : "NO"}</b></div>)}</div>
      </div>
      <div className="engine-meta"><span>Oversold setup: {u.oversold_gate ? "YES" : "NO"}</span><span>Data quality: {u.data_quality_status || washout.data_quality?.status || "UNAVAILABLE"}</span><span>Snapshot: {snapshotTime}</span></div>
    </section>

    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">INDICATOR DETAIL</span><h2>Level, benchmark and direction</h2></div></div>
      <p className="section-intro">Each card separates current level from direction. Percentiles are published only after the canonical history reaches its reliability gate.</p>
      <div className="indicator-grid">
        <MetricCard name="S&P 500 above 20-day average" symbol="SPXA20R" value={`${plain(w.SPXA20R,1)}%`} benchmark="Structural reference: below 30 oversold; deeper readings are increasingly stretched." state={spxaState(w.SPXA20R)} direction={fast.FAST_BREADTH_TURN ? "IMPROVING" : "NOT YET"} interpretation="Shows how much of the S&P 500 remains above its short-term trend." />
        <MetricCard name="U.S. stocks above 5-day average" symbol="MMFD" value={`${plain(w.MMFD,1)}%`} benchmark="Reference scale: <15 extreme, <30 oversold, ~50 neutral, >70 strong, >85 extreme." state={mmfdState(w.MMFD, w.MMFD_STATE)} direction={context.MMFD_IMPROVING ? "IMPROVING" : "NOT IMPROVING"} detail={`Universe ${mmfd?.universe_size ?? "-"} · valid ${mmfd?.valid_5d_observations ?? "-"} · coverage ${finite(mmfd?.coverage_pct) ? `${plain(mmfd?.coverage_pct,1)}%` : "UNAVAILABLE"}`} interpretation="Percent of eligible U.S.-listed non-ETF equities above their own 5-day moving average." />
        <MetricCard name="NYSE breadth momentum" symbol="NYMO" value={signed(w.NYMO,1)} benchmark={historyBenchmark(hist.NYMO, "0 neutral · ±100 structural stretch reference")} state={historyState(hist.NYMO, momentumState(w.NYMO))} direction={fast.MOMENTUM_TURN ? "IMPROVING" : "NOT YET"} detail={historyDetail(hist.NYMO)} interpretation="Breadth momentum context now carries an explicit reliability-gated historical benchmark instead of an unexplained raw number." />
        <MetricCard name="Nasdaq breadth momentum" symbol="NAMO" value={signed(w.NAMO,1)} benchmark={historyBenchmark(hist.NAMO, "0 neutral · ±100 structural stretch reference")} state={historyState(hist.NAMO, momentumState(w.NAMO))} direction={fast.MOMENTUM_TURN ? "IMPROVING" : "NOT YET"} detail={historyDetail(hist.NAMO)} interpretation="Historical percentile activates only after enough independent sessions have been captured." />
        <MetricCard name="Nasdaq summation RSI" symbol="NASI+" value={plain(w.NASI_RSI,1)} benchmark="<30 oversold · <20 very oversold · <10 extreme · >70 overbought · >80 very · >90 extreme." state={nasiState(w.NASI_RSI)} direction={w.NASI_DIRECTION} detail={finite(w.NASI_EMA10) ? `EMA10 ${plain(w.NASI_EMA10,1)}` : undefined} interpretation="Internally calculated NASI+ breadth state. Direction is versus the prior completed RSI." />
        <MetricCard name="NYSE advance/decline volume" symbol="NYUD" value={signed(w.NYUD,1)} benchmark={historyBenchmark(hist.NYUD, "0 is arithmetic balance")} state={historyState(hist.NYUD, signState(w.NYUD))} direction={fast.NET_VOLUME_TURN ? "IMPROVING" : "NOT YET"} detail={historyDetail(hist.NYUD)} interpretation="The benchmark uses time-matched intraday history so a morning cumulative-volume reading is not compared with a closing reading." />
        <MetricCard name="Nasdaq advance/decline volume" symbol="NAUD" value={signed(w.NAUD,1)} benchmark={historyBenchmark(hist.NAUD, "0 is arithmetic balance")} state={historyState(hist.NAUD, signState(w.NAUD))} direction={fast.NET_VOLUME_TURN ? "IMPROVING" : "NOT YET"} detail={historyDetail(hist.NAUD)} interpretation="Positive means advancing volume leads; negative means declining volume leads, with percentile context gated by independent sessions." />
        <MetricCard name="NYSE down/up volume ratio" symbol="NYSE D/U" value={finite(w.nyse_down_up_ratio) ? `${plain(w.nyse_down_up_ratio,2)}x` : "UNAVAILABLE"} benchmark={historyBenchmark(hist.nyse_down_up_ratio, "1.00x is arithmetic balance")} state={historyState(hist.nyse_down_up_ratio, ratioState(w.nyse_down_up_ratio))} direction={fast.DOWN_UP_RATIO_RELIEF ? "RELIEF" : "NOT YET"} detail={historyDetail(hist.nyse_down_up_ratio)} interpretation="Selling-pressure percentile uses time-matched intraday history and is withheld until the sample is reliable." />
        <MetricCard name="Nasdaq down/up volume ratio" symbol="NASDAQ D/U" value={finite(w.nasdaq_down_up_ratio) ? `${plain(w.nasdaq_down_up_ratio,2)}x` : "UNAVAILABLE"} benchmark={historyBenchmark(hist.nasdaq_down_up_ratio, "1.00x is arithmetic balance")} state={historyState(hist.nasdaq_down_up_ratio, ratioState(w.nasdaq_down_up_ratio))} direction={fast.DOWN_UP_RATIO_RELIEF ? "RELIEF" : "NOT YET"} detail={historyDetail(hist.nasdaq_down_up_ratio)} interpretation="Below 1 means up volume exceeds down volume; above 1 means selling volume leads." />
        <MetricCard name="Volatility of VIX" symbol="VVIX" value={plain(w.VVIX,1)} benchmark={`2-year history: ${percentile(vvixPct)}`} state={vvix?.state || w.VVIX_STATE || percentileState(vvixPct, "ELEVATED STRESS")} direction={vvix?.direction_vs_prior_close || w.VVIX_DIRECTION} detail={`Prior close ${plain(vvix?.prior_close ?? w.VVIX_PRIOR_CLOSE,1)} · change ${signed(vvixChange,1)} pts`} interpretation="Shows both the level of volatility stress and whether that stress is easing or worsening." />
        <MetricCard name="Live SPX downside skew proxy" symbol="25Δ PUT IV - 25Δ CALL IV" value={finite(liveSkew) ? `${plain(liveSkew,2)} vol pts` : "UNAVAILABLE"} benchmark="Live proxy is separate from official Cboe SKEW. No percentile is shown until a validated live-proxy history exists." state={liveSkewMode === "LIVE_SPX_OPTIONS" ? "LIVE PROXY" : "UNAVAILABLE"} direction={skew?.direction_vs_prior_snapshot || w.SKEW_DIRECTION} detail={`Ratio ${finite(liveSkewRatio) ? plain(liveSkewRatio,2) : "UNAVAILABLE"} · source ${liveSkewMode}`} interpretation="Approximates current SPX downside option demand. It is never substituted with the official daily SKEW close." />
        <MetricCard name="Official Cboe SKEW" symbol="SKEW" value={plain(officialSkew,1)} benchmark={`2-year history: ${percentile(officialSkewPct)}`} state={percentileState(officialSkewPct, "ELEVATED TAIL RISK")} direction={skew?.official_skew_direction} detail={`Latest official date ${officialDate}`} interpretation="Official daily tail-risk index, shown separately from the live SPX options skew proxy." />
      </div>
    </section>
  </>;
}
