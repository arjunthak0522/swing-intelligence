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
  if (Number(value) < 45) return "WEAK";
  if (Number(value) <= 70) return "NORMAL";
  if (Number(value) <= 90) return "STRONG";
  return "EXTREME OVERBOUGHT";
}
function mmfdState(value?: number | null, supplied?: string | null) {
  if (supplied) return supplied.replaceAll("_", " ");
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) < 15) return "EXTREME OVERSOLD";
  if (Number(value) < 30) return "OVERSOLD";
  if (Number(value) <= 70) return "NORMAL";
  if (Number(value) <= 85) return "STRONG";
  return "EXTREME OVERBOUGHT";
}
function momentumState(value?: number | null) {
  if (!finite(value)) return "UNAVAILABLE";
  const v = Number(value);
  if (v <= -150) return "EXTREME NEGATIVE";
  if (v <= -100) return "STRETCHED NEGATIVE";
  if (v < -50) return "WEAK NEGATIVE";
  if (v <= 50) return "NORMAL";
  if (v < 100) return "STRONG POSITIVE";
  if (v < 150) return "STRETCHED POSITIVE";
  return "EXTREME POSITIVE";
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
function volumeBreadthState(value?: number | null) {
  if (!finite(value)) return "UNAVAILABLE";
  const v = Number(value), a = Math.abs(v), side = v >= 0 ? "BUYING" : "SELLING";
  if (a < 250) return "NORMAL / BALANCED";
  if (a < 1000) return `MODERATE ${side}`;
  if (a < 2500) return `STRONG ${side}`;
  return `EXTREME ${side}`;
}
function ratioState(value?: number | null) {
  if (!finite(value)) return "UNAVAILABLE";
  const v = Number(value);
  if (v >= 9) return "EXTREME SELLING";
  if (v >= 4) return "HEAVY SELLING";
  if (v >= 2) return "ELEVATED SELLING";
  if (v <= 1/9) return "EXTREME BUYING";
  if (v <= .25) return "HEAVY BUYING";
  if (v < .5) return "ELEVATED BUYING";
  return "NORMAL / MIXED";
}
function vvixState(value?: number | null, pct?: number | null) {
  if (finite(pct) && Number(pct) >= 95) return "EXTREME STRESS";
  if (!finite(value)) return "UNAVAILABLE";
  const v = Number(value);
  if (v < 70) return "EXTREME COMPLACENCY";
  if (v < 80) return "CALM";
  if (v <= 100) return "NORMAL";
  if (v <= 120) return "ELEVATED STRESS";
  return "EXTREME STRESS";
}
function liveSkewState(ratio?: number | null) {
  if (!finite(ratio)) return "UNAVAILABLE";
  const r = Number(ratio);
  if (r >= 1.20) return "EXTREME DOWNSIDE SKEW";
  if (r >= 1.10) return "STRETCHED DOWNSIDE SKEW";
  if (r > 1.05) return "ELEVATED DOWNSIDE SKEW";
  if (r < .95) return "UPSIDE SKEW";
  return "NORMAL / BALANCED";
}
function officialSkewState(value?: number | null, pct?: number | null) {
  if (finite(pct) && Number(pct) >= 95) return "EXTREME TAIL RISK";
  if (!finite(value)) return "UNAVAILABLE";
  const v = Number(value);
  if (v >= 150) return "EXTREME TAIL RISK";
  if (v >= 140) return "HIGH TAIL RISK";
  if (v >= 125) return "ELEVATED TAIL RISK";
  if (v >= 110) return "NORMAL";
  return "LOW TAIL RISK";
}
function percentileState(value?: number | null, highLabel = "ELEVATED") {
  if (!finite(value)) return "UNAVAILABLE";
  if (Number(value) >= 95) return "EXTREME";
  if (Number(value) >= 80) return "STRETCHED";
  if (Number(value) >= 60) return highLabel;
  return "NORMAL";
}
function stateClass(value: string) {
  const v = value.toUpperCase();
  if (v.includes("EXTREME")) return "extreme-text";
  if (v.includes("BUYING") || v.includes("STRONG") || v.includes("CALM") || v.includes("LOW TAIL") || v === "NORMAL" || v.includes("NORMAL /")) return "good-text";
  if (v.includes("SELLING") || v.includes("HIGH TAIL")) return "bad-text";
  if (v.includes("OVERSOLD") || v.includes("STRETCHED") || v.includes("HEAVY") || v.includes("ELEVATED") || v.includes("WEAK")) return "warn";
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
  return `Working benchmark · ${fallback} · percentile history ${metric.session_count ?? 0}/${metric.minimum_reliable_sessions ?? 20} sessions`;
}
function historyDetail(metric: HistoricalContextMetric | undefined) {
  if (!metric) return undefined;
  if (metric.reliable && finite(metric.percentile)) return `${metric.methodology || "Empirical captured history"} · ${metric.history_start_date || "-"} to ${metric.history_end_date || "-"}`;
  return `Percentile withheld until the reliability gate is met. ${metric.methodology || "Captured history is still accumulating."}`;
}
function historyState(metric: HistoricalContextMetric | undefined, fallback: string) {
  return metric?.reliable && metric.state ? metric.state : fallback;
}

function MetricCard({ name, symbol, value, benchmark, state, direction, directionTone, interpretation, detail }: {
  name: string; symbol: string; value: string; benchmark: string; state: string; direction?: string | null; directionTone?: string; interpretation: string; detail?: string;
}) {
  const dir = direction?.replaceAll("_", " ") || "DIRECTION UNAVAILABLE";
  const tone = stateClass(state);
  return <div className="indicator-card" data-tone={tone}>
    <div className="indicator-title"><div><b>{name}</b><small>{symbol}</small></div><span className="indicator-dot" /></div>
    <strong className="indicator-value">{value}</strong>
    <div className="indicator-badges"><span className={tone}>{state}</span><span className={directionTone || directionClass(direction)}>{dir}</span></div>
    <div className="indicator-reference"><b>BENCHMARK</b>{benchmark}</div>
    {detail ? <div className="indicator-detail">{detail}</div> : null}
    <p>{interpretation}</p>
  </div>;
}

export default function ReentryDecisionDetails({ washout }: { washout: WashoutSnapshot }) {
  const u = washout.unified_engine;
  const w = washout.values;
  if (!u || !w) return <section className="card section-card"><div className="notice"><CircleAlert size={16} /> RE-ENTRY ENGINE UNAVAILABLE</div></section>;
  const fast = u.fast_families || { FAST_BREADTH_TURN: washout.families?.fast_breadth_turn ?? false, MOMENTUM_TURN: washout.families?.momentum_turn ?? false, NET_VOLUME_TURN: washout.families?.net_volume_turn ?? false, DOWN_UP_RATIO_RELIEF: washout.families?.down_up_ratio_relief ?? false };
  const context = u.context_support || {};
  const fastRows = [
    ["Fast breadth", fast.FAST_BREADTH_TURN, "NO BREADTH TURN"],
    ["Breadth momentum", fast.MOMENTUM_TURN, "NO MOMENTUM TURN"],
    ["Advance/decline volume", fast.NET_VOLUME_TURN, "NO VOLUME TURN"],
    ["Selling intensity relief", fast.DOWN_UP_RATIO_RELIEF, "NO RELIEF"],
  ] as const;
  const contextRows = [
    ["MMFD improving", context.MMFD_IMPROVING, "NOT IMPROVING"],
    ["NASI+ turning upward", context.NASI_TURNING_UP, "NOT TURNING UP"],
    ["VVIX easing", context.VVIX_EASING, "NOT EASING"],
    ["SKEW narrowing", context.SKEW_NARROWING, "NOT NARROWING"],
  ] as const;
  const vvix = washout.vvix_live, skew = washout.skew_live, mmfd = washout.mmfd_live, hist = washout.historical_context?.metrics || {};
  const vvixChange = finite(vvix?.change_points_vs_prior_close) ? vvix?.change_points_vs_prior_close : finite(w.VVIX) && finite(w.VVIX_PRIOR_CLOSE) ? Number(w.VVIX)-Number(w.VVIX_PRIOR_CLOSE) : null;
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
      body{background:radial-gradient(circle at 18% -8%,rgba(47,118,80,.10),transparent 28%),radial-gradient(circle at 91% 4%,rgba(163,116,42,.07),transparent 24%),var(--bg)}
      .card{box-shadow:0 16px 42px rgba(28,40,32,.065);border-color:#d8d4c9}.hero{position:relative;overflow:hidden;background:linear-gradient(135deg,#fbfaf7 0%,#f7faf7 58%,#eef5f0 100%);border-color:rgba(47,118,80,.24);box-shadow:0 22px 60px rgba(33,78,52,.10)}.hero:before{content:"";position:absolute;width:320px;height:320px;border-radius:50%;right:-135px;top:-170px;background:radial-gradient(circle,rgba(47,118,80,.15),rgba(47,118,80,0) 68%);pointer-events:none}.hero:after{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,var(--green),#72b189 48%,transparent)}
      .signal.good{background:linear-gradient(95deg,#205e3e,#3c8d60 65%,#61a77a);-webkit-background-clip:text;background-clip:text;color:transparent;text-shadow:0 8px 30px rgba(47,118,80,.10)}.decision-summary{position:relative;border-left:0;padding:20px 20px 18px;border-radius:17px;background:rgba(255,255,255,.56);box-shadow:inset 0 0 0 1px rgba(47,118,80,.12),0 8px 24px rgba(31,55,39,.05);backdrop-filter:blur(4px)}.decision-tags span{padding:8px 9px;border-radius:10px;background:rgba(47,118,80,.055);border:1px solid rgba(47,118,80,.10)}.topbar .brand{position:relative}.topbar .brand:after{content:"";display:block;width:26px;height:3px;border-radius:99px;margin-top:4px;background:linear-gradient(90deg,var(--green),#89b99a)}
      .family-section{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:14px 0 20px}.family-panel{border:1px solid var(--line);border-radius:16px;padding:14px;background:linear-gradient(180deg,rgba(255,255,255,.58),rgba(255,255,255,.24));box-shadow:0 9px 24px rgba(30,42,33,.035)}.family-panel h3{margin:0 0 10px;font-size:13px}.family-row{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--line);font-size:11px}.family-row:first-of-type{border-top:0}.family-row b{font-size:8px;letter-spacing:.045em;border-radius:999px;padding:5px 7px;border:1px solid var(--line);background:rgba(255,255,255,.55)}
      .indicator-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.indicator-card{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:16px;padding:16px;background:linear-gradient(180deg,rgba(255,255,255,.66),rgba(255,255,255,.30));box-shadow:0 8px 24px rgba(31,44,35,.035);transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}.indicator-card:hover{transform:translateY(-2px);box-shadow:0 14px 32px rgba(31,44,35,.07)}.indicator-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#aaa}.indicator-card[data-tone="good-text"]:before{background:var(--green)}.indicator-card[data-tone="warn"]:before{background:var(--amber)}.indicator-card[data-tone="bad-text"]:before{background:var(--red)}.indicator-card[data-tone="extreme-text"]:before{background:linear-gradient(var(--red),var(--amber))}.indicator-title{display:flex;justify-content:space-between;gap:10px}.indicator-title b{font-size:11px}.indicator-title small{display:block;color:var(--muted);font-size:9px;margin-top:2px}.indicator-dot{width:8px;height:8px;border-radius:50%;background:#bbb;box-shadow:0 0 0 4px rgba(0,0,0,.025)}.indicator-card[data-tone="good-text"] .indicator-dot{background:var(--green)}.indicator-card[data-tone="warn"] .indicator-dot{background:var(--amber)}.indicator-card[data-tone="bad-text"] .indicator-dot{background:var(--red)}.indicator-card[data-tone="extreme-text"] .indicator-dot{background:#c46a35}.indicator-value{display:block;font-size:26px;margin:10px 0 8px;letter-spacing:-.035em;font-variant-numeric:tabular-nums}.indicator-badges{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}.indicator-badges span{border:1px solid currentColor;border-radius:999px;padding:4px 7px;font-size:8px;font-weight:900;letter-spacing:.045em;background:rgba(255,255,255,.45)}.indicator-reference{font-size:9px;line-height:1.48;color:#50554e;padding:9px 10px;border-radius:9px;background:#f0eee8}.indicator-reference b{display:block;margin-bottom:2px;font-size:7px;letter-spacing:.12em;color:var(--muted)}.indicator-detail{font-size:9px;line-height:1.45;color:var(--muted);margin-top:6px}.indicator-card p{font-size:10px;line-height:1.5;margin:9px 0 0}.engine-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.engine-meta span{font-size:9px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 8px;background:rgba(255,255,255,.45)}.extreme-text{color:#b75f34}.warn{color:var(--amber)}
      @media(max-width:900px){.indicator-grid{grid-template-columns:1fr 1fr}}@media(max-width:680px){.family-section,.indicator-grid{grid-template-columns:1fr}.decision-summary{padding:16px}}
    `}</style>
    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">REVERSAL EVIDENCE</span><h2>What has actually turned?</h2></div></div>
      <div className="family-section">
        <div className="family-panel"><h3>Fast reversal families · {u.fast_family_count ?? 0}/4</h3>{fastRows.map(([name,on,off]) => <div className="family-row" key={name}><span>{name}</span><b className={on ? "good-text" : "muted"}>{on ? "TURNED" : off}</b></div>)}</div>
        <div className="family-panel"><h3>Context support · {u.context_support_count ?? 0}/4</h3>{contextRows.map(([name,on,off]) => <div className="family-row" key={name}><span>{name}</span><b className={on ? "good-text" : "muted"}>{on ? "CONFIRMED" : off}</b></div>)}</div>
      </div>
      <div className="engine-meta"><span>Oversold setup: {u.oversold_gate ? "YES" : "NO"}</span><span>Data quality: {u.data_quality_status || washout.data_quality?.status || "UNAVAILABLE"}</span><span>Snapshot: {snapshotTime}</span></div>
    </section>

    <section className="card section-card">
      <div className="section-heading"><div><span className="kicker">INDICATOR DETAIL</span><h2>Current level vs. intelligent benchmark</h2></div></div>
      <p className="section-intro">Every indicator now carries an explicit reference scale and a current-state label. Where long point-in-time history is still accumulating, the card says when a working heuristic is being used.</p>
      <div className="indicator-grid">
        <MetricCard name="S&P 500 above 20-day average" symbol="SPXA20R" value={`${plain(w.SPXA20R,1)}%`} benchmark="<10 extreme oversold · 10–30 oversold · 30–45 weak · 45–70 normal · 70–90 strong · >90 extreme overbought" state={spxaState(w.SPXA20R)} direction={fast.FAST_BREADTH_TURN ? "IMPROVING" : "NO BREADTH TURN"} interpretation="Shows how much of the S&P 500 remains above its short-term trend." />
        <MetricCard name="U.S. stocks above 5-day average" symbol="MMFD" value={`${plain(w.MMFD,1)}%`} benchmark="<15 extreme oversold · 15–30 oversold · 30–70 normal zone centered near 50 · 70–85 strong · >85 extreme overbought" state={mmfdState(w.MMFD,w.MMFD_STATE)} direction={context.MMFD_IMPROVING ? "IMPROVING" : "NOT IMPROVING"} detail={`Universe ${mmfd?.universe_size ?? "-"} · valid ${mmfd?.valid_5d_observations ?? "-"} · coverage ${finite(mmfd?.coverage_pct) ? `${plain(mmfd?.coverage_pct,1)}%` : "UNAVAILABLE"}`} interpretation="Percent of eligible U.S.-listed non-ETF equities above their own 5-day moving average." />
        <MetricCard name="NYSE breadth momentum" symbol="NYMO" value={signed(w.NYMO,1)} benchmark={historyBenchmark(hist.NYMO,"0 neutral · ±50 normal band · ±100 stretched · ±150 classic extended/extreme reference")} state={historyState(hist.NYMO,momentumState(w.NYMO))} direction={fast.MOMENTUM_TURN ? "IMPROVING" : "NO MOMENTUM TURN"} detail={historyDetail(hist.NYMO)} interpretation="McClellan-style breadth acceleration. The fixed scale is a working reference; captured percentiles supersede it once reliable." />
        <MetricCard name="Nasdaq breadth momentum" symbol="NAMO" value={signed(w.NAMO,1)} benchmark={historyBenchmark(hist.NAMO,"0 neutral · ±50 normal band · ±100 stretched · ±150 extended/extreme reference")} state={historyState(hist.NAMO,momentumState(w.NAMO))} direction={fast.MOMENTUM_TURN ? "IMPROVING" : "NO MOMENTUM TURN"} detail={historyDetail(hist.NAMO)} interpretation="Nasdaq breadth acceleration with the same severity framework and a reliability-gated empirical percentile." />
        <MetricCard name="Nasdaq summation RSI" symbol="NASI+" value={plain(w.NASI_RSI,1)} benchmark="<30 oversold · <20 very oversold · <10 extreme · 30–70 normal · >70 overbought · >90 extreme" state={nasiState(w.NASI_RSI)} direction={w.NASI_DIRECTION} directionTone={w.NASI_DIRECTION === "FALLING" ? "bad-text" : w.NASI_DIRECTION === "RISING" ? "good-text" : undefined} detail={finite(w.NASI_EMA10) ? `EMA10 ${plain(w.NASI_EMA10,1)}` : undefined} interpretation="Internally calculated NASI+ breadth state. Direction is versus the prior completed RSI." />
        <MetricCard name="NYSE advance/decline volume" symbol="NYUD" value={signed(w.NYUD,1)} benchmark={historyBenchmark(hist.NYUD,"0 balance · working feed scale: |value| <250 normal, 250–1,000 moderate, 1,000–2,500 strong, >2,500 extreme")} state={historyState(hist.NYUD,volumeBreadthState(w.NYUD))} direction={fast.NET_VOLUME_TURN ? "IMPROVING" : "NO VOLUME TURN"} detail={historyDetail(hist.NYUD)} interpretation="Time-matched percentile is preferred because cumulative A/D volume naturally grows through the session." />
        <MetricCard name="Nasdaq advance/decline volume" symbol="NAUD" value={signed(w.NAUD,1)} benchmark={historyBenchmark(hist.NAUD,"0 balance · working feed scale: |value| <250 normal, 250–1,000 moderate, 1,000–2,500 strong, >2,500 extreme")} state={historyState(hist.NAUD,volumeBreadthState(w.NAUD))} direction={fast.NET_VOLUME_TURN ? "IMPROVING" : "NO VOLUME TURN"} detail={historyDetail(hist.NAUD)} interpretation="Positive means advancing volume leads; severity is labeled even before the empirical percentile history is mature." />
        <MetricCard name="NYSE down/up volume ratio" symbol="NYSE D/U" value={finite(w.nyse_down_up_ratio) ? `${plain(w.nyse_down_up_ratio,2)}x` : "UNAVAILABLE"} benchmark={historyBenchmark(hist.nyse_down_up_ratio,"1.0x balance · 2x elevated selling · 4x heavy · 9x classic washout extreme; inverse bands flag buying dominance")} state={historyState(hist.nyse_down_up_ratio,ratioState(w.nyse_down_up_ratio))} direction={fast.DOWN_UP_RATIO_RELIEF ? "RELIEF" : "NO RELIEF"} detail={historyDetail(hist.nyse_down_up_ratio)} interpretation="The 9:1 area is treated as genuine selling-climax territory; lower ratios show relief or buying dominance." />
        <MetricCard name="Nasdaq down/up volume ratio" symbol="NASDAQ D/U" value={finite(w.nasdaq_down_up_ratio) ? `${plain(w.nasdaq_down_up_ratio,2)}x` : "UNAVAILABLE"} benchmark={historyBenchmark(hist.nasdaq_down_up_ratio,"1.0x balance · 2x elevated selling · 4x heavy · 9x classic washout extreme; inverse bands flag buying dominance")} state={historyState(hist.nasdaq_down_up_ratio,ratioState(w.nasdaq_down_up_ratio))} direction={fast.DOWN_UP_RATIO_RELIEF ? "RELIEF" : "NO RELIEF"} detail={historyDetail(hist.nasdaq_down_up_ratio)} interpretation="Below 1 means up volume exceeds down volume; above 1 means selling volume leads." />
        <MetricCard name="Volatility of VIX" symbol="VVIX" value={plain(w.VVIX,1)} benchmark={`Working level scale: <70 extreme complacency · 70–80 calm · 80–100 normal · 100–120 elevated · >120 extreme stress · 2Y ${percentile(vvixPct)}`} state={vvix?.state || w.VVIX_STATE || vvixState(w.VVIX,vvixPct)} direction={vvix?.direction_vs_prior_close || w.VVIX_DIRECTION} detail={`Prior close ${plain(vvix?.prior_close ?? w.VVIX_PRIOR_CLOSE,1)} · change ${signed(vvixChange,1)} pts`} interpretation="Cboe VVIX measures expected volatility of VIX; the historical percentile remains the preferred severity check." />
        <MetricCard name="Live SPX downside skew proxy" symbol="25Δ PUT IV / CALL IV" value={finite(liveSkew) ? `${plain(liveSkew,2)} vol pts` : "UNAVAILABLE"} benchmark="Working ratio scale: 0.95–1.05 balanced · 1.05–1.10 elevated downside skew · 1.10–1.20 stretched · >1.20 extreme" state={liveSkewState(liveSkewRatio)} direction={skew?.direction_vs_prior_snapshot || w.SKEW_DIRECTION || "NO CHANGE SIGNAL"} detail={`Ratio ${finite(liveSkewRatio) ? plain(liveSkewRatio,2) : "UNAVAILABLE"} · source ${liveSkewMode}`} interpretation="Current SPX downside option demand. This proxy remains separate from official daily Cboe SKEW." />
        <MetricCard name="Official Cboe SKEW" symbol="SKEW" value={plain(officialSkew,1)} benchmark={`100 ≈ normal-distribution baseline · 125–140 elevated · 140–150 high · >150 extreme · 2Y ${percentile(officialSkewPct)}`} state={officialSkewState(officialSkew,officialSkewPct)} direction={skew?.official_skew_direction} detail={`Latest official date ${officialDate}`} interpretation="Official daily tail-risk index. Cboe notes that higher SKEW corresponds to greater priced tail risk." />
      </div>
    </section>
  </>;
}
