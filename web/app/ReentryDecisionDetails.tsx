import { CircleAlert } from "lucide-react";
import type { HistoricalContextMetric, WashoutSnapshot } from "../lib/reentry";

const finite=(v?:number|null)=>typeof v==="number"&&Number.isFinite(v);
const plain=(v?:number|null,d=1)=>finite(v)?Number(v).toFixed(d):"UNAVAILABLE";
const signed=(v?:number|null,d=1)=>finite(v)?`${Number(v)>0?"+":""}${Number(v).toFixed(d)}`:"UNAVAILABLE";
const percentile=(v?:number|null)=>finite(v)?`${Math.round(Number(v))}th percentile`:"Percentile unavailable";
const fresh=(kind:string,value?:string|null)=>`${kind} · ${value||"time unavailable"}`;

function spxaState(v?:number|null){
  if(!finite(v))return"UNAVAILABLE";
  const x=Number(v);
  if(x<10)return"EXTREME WASHOUT";
  if(x<30)return"OVERSOLD";
  if(x<50)return"WEAK";
  if(x<70)return"NORMAL / HEALTHY";
  if(x<=90)return"STRONG";
  return"EXTREME BREADTH";
}
function mmfdState(v?:number|null,s?:string|null){
  if(s)return s.replaceAll("_"," ");
  if(!finite(v))return"UNAVAILABLE";
  const x=Number(v);
  if(x<15)return"EXTREME WASHOUT";
  if(x<30)return"OVERSOLD";
  if(x<50)return"WEAK / REPAIRING";
  if(x<70)return"HEALTHY";
  if(x<=85)return"STRONG";
  return"EXTREME BREADTH";
}
function momentumState(v?:number|null){
  if(!finite(v))return"UNAVAILABLE";
  const x=Number(v);
  if(x<=-100)return"OVERSOLD";
  if(x<0)return"NEGATIVE";
  if(x<=100)return"POSITIVE";
  return"OVERBOUGHT";
}
function nasiState(v?:number|null){
  if(!finite(v))return"UNAVAILABLE";
  const x=Number(v);
  if(x<10)return"EXTREME OVERSOLD";
  if(x<20)return"VERY OVERSOLD";
  if(x<30)return"OVERSOLD";
  if(x>90)return"EXTREME OVERBOUGHT";
  if(x>80)return"VERY OVERBOUGHT";
  if(x>70)return"OVERBOUGHT";
  return"NORMAL";
}
function volumeBreadthState(v?:number|null){
  if(!finite(v))return"UNAVAILABLE";
  const x=Number(v);
  if(x>0)return"BUYING VOLUME LEADS";
  if(x<0)return"SELLING VOLUME LEADS";
  return"BALANCED";
}
function ratioState(v?:number|null){
  if(!finite(v))return"UNAVAILABLE";
  const x=Number(v);
  if(x>=9)return"EXTREME SELLING";
  if(x>=4)return"HEAVY SELLING";
  if(x>=2)return"ELEVATED SELLING";
  if(x<=1/9)return"EXTREME BUYING";
  if(x<=.25)return"HEAVY BUYING";
  if(x<.5)return"ELEVATED BUYING";
  return"NORMAL / MIXED";
}
function vvixState(v?:number|null){
  if(!finite(v))return"UNAVAILABLE";
  const x=Number(v);
  if(x<70)return"EXTREME COMPLACENCY";
  if(x<80)return"CALM";
  if(x<=100)return"NORMAL";
  if(x<=120)return"ELEVATED STRESS";
  return"EXTREME STRESS";
}
function liveSkewState(r?:number|null){
  if(!finite(r))return"UNAVAILABLE";
  const x=Number(r);
  if(x>=1.20)return"EXTREME DOWNSIDE PROTECTION";
  if(x>=1.10)return"STRETCHED DOWNSIDE PROTECTION";
  if(x>1.05)return"ELEVATED DOWNSIDE PROTECTION";
  if(x<.95)return"UPSIDE-LEANING OPTIONS";
  return"NORMAL / BALANCED";
}
function officialSkewState(v?:number|null,p?:number|null){
  if(finite(p)&&Number(p)>=95)return"EXTREME TAIL RISK";
  if(!finite(v))return"UNAVAILABLE";
  const x=Number(v);
  if(x>=150)return"EXTREME TAIL RISK";
  if(x>=140)return"HIGH TAIL RISK";
  if(x>=125)return"ELEVATED TAIL RISK";
  if(x>=110)return"NORMAL";
  return"LOW TAIL RISK";
}
function stateClass(value:string){
  const v=value.toUpperCase();
  if(v.includes("EXTREME"))return"extreme-text";
  if(v.includes("BUYING")||v.includes("STRONG")||v.includes("HEALTHY")||v.includes("CALM")||v.includes("LOW TAIL")||v==="NORMAL"||v.includes("NORMAL /"))return"good-text";
  if(v.includes("SELLING")||v.includes("HIGH TAIL"))return"bad-text";
  if(v.includes("OVERSOLD")||v.includes("STRETCHED")||v.includes("HEAVY")||v.includes("ELEVATED")||v.includes("WEAK"))return"warn";
  return"muted";
}
function directionClass(value?:string|null){
  const v=(value||"").toUpperCase();
  if(["RISING","WIDENING","DETERIORATING"].includes(v))return"bad-text";
  if(["FALLING","NARROWING","IMPROVING","EASING","RELIEF"].includes(v))return"good-text";
  return"muted";
}
function historyBenchmark(m:HistoricalContextMetric|undefined,fallback:string){
  if(!m)return fallback;
  if(m.reliable&&finite(m.percentile))return`${percentile(m.percentile)} of validated captured history · ${m.state||"NORMAL"} · ${fallback}`;
  return`${fallback} · percentile history ${m.session_count??0}/${m.minimum_reliable_sessions??20} sessions`;
}
function historyDetail(m:HistoricalContextMetric|undefined){
  if(!m)return undefined;
  if(m.reliable&&finite(m.percentile))return`${m.methodology||"Empirical captured history"} · ${m.history_start_date||"-"} to ${m.history_end_date||"-"}`;
  return`Percentile withheld until the reliability gate is met. ${m.methodology||"Captured history is still accumulating."}`;
}
function historyState(m:HistoricalContextMetric|undefined,fallback:string){return m?.reliable&&m.state?m.state:fallback;}

function spxaMeaning(v?:number|null,improving?:boolean){
  if(!finite(v))return"S&P 500 short-term breadth is unavailable.";
  const x=Number(v),state=spxaState(v).toLowerCase();
  const move=improving?"A fast breadth turn is active, so participation is beginning to repair.":"No fast breadth turn is active yet, so the washout has not broadened into clear confirmation.";
  return`${x.toFixed(1)}% of S&P 500 stocks are above their 20-day average - ${state}. ${x<30?"This is a genuine oversold breadth backdrop and keeps the re-entry setup alive.":x<50?"Breadth remains below the 50% majority line, so participation is still weak.":x>=70?"Participation is broad, which is confirmation rather than a washout setup.":"A majority of stocks are above trend, which is a healthier breadth backdrop."} ${move}`;
}
function mmfdMeaning(v?:number|null,improving?:boolean){
  if(!finite(v))return"U.S. 5-day breadth is unavailable.";
  const x=Number(v),state=mmfdState(v).toLowerCase();
  const move=improving?"It is improving, which is early confirmation that the bounce is spreading.":"It is not currently improving, so short-term participation is not adding confirmation.";
  return`${x.toFixed(1)}% of the tracked U.S. equity universe is above its 5-day average - ${state}. ${x<30?"Short-term breadth is washed out.":x<50?"Breadth has repaired off the lows but remains below the 50% majority line.":x<70?"A majority of stocks are back above their very short-term trend.":"Short-term participation is broad."} ${move}`;
}
function momentumMeaning(label:string,v?:number|null,improving?:boolean){
  if(!finite(v))return`${label} is unavailable.`;
  const x=Number(v),state=momentumState(v).toLowerCase();
  const move=improving?"The reversal family is improving, which is useful early evidence before full normalization.":"No momentum turn is active right now, so breadth momentum is not confirming the recovery.";
  return`${label} is ${x.toFixed(1)} - ${state}. The established technician anchors are -100 oversold, 0 centerline, and +100 overbought. ${x<=-100?"Breadth momentum is stretched enough to support an exhaustion setup.":x<0?"Momentum is still below the centerline, so breadth remains net weak.":"Momentum is above the centerline, indicating positive breadth pressure."} ${move}`;
}
function nasiMeaning(v?:number|null,direction?:string|null){
  if(!finite(v))return"Nasdaq breadth momentum strength is unavailable.";
  const x=Number(v),state=nasiState(v).toLowerCase(),d=(direction||"").toUpperCase();
  const move=d==="RISING"?"It is rising, which supports a more durable Nasdaq breadth recovery.":d==="FALLING"?"It is falling, so the slower Nasdaq breadth trend is not confirming the recovery yet.":"It is not showing a clear directional turn.";
  return`${x.toFixed(1)} places this derived Nasdaq breadth-momentum reading in the ${state} zone under the RE-ENTRY momentum interpretation framework. ${x<30?"The slower Nasdaq breadth structure is still deeply stretched.":x>70?"The slower breadth structure is extended rather than washed out.":"The slower breadth structure is in its middle range."} ${move}`;
}
function volumeMeaning(label:string,v?:number|null,improving?:boolean){
  if(!finite(v))return`${label} is unavailable.`;
  const x=Number(v),side=x>0?"advancing":"declining";
  const move=improving?"The net-volume reversal family is improving, so volume participation is supporting the rebound.":"No net-volume turn is active, so volume breadth is not confirming the rebound right now.";
  return`${label} is ${signed(v,1)}, so ${side} volume is leading. Zero is the defensible balance line. Because raw feed scale varies, magnitude is judged by captured historical percentiles when available rather than fixed universal 'extreme' numbers. ${move}`;
}
function ratioMeaning(label:string,v?:number|null,relief?:boolean){
  if(!finite(v))return`${label} is unavailable.`;
  const x=Number(v),side=x>1?"selling":"buying";
  const move=relief?"Selling-intensity relief is active, which is constructive for re-entry.":"No selling-intensity relief is active yet.";
  return`${label} is ${x.toFixed(2)}x. 1.0x is balance; above 1 means ${side} volume dominates. Classic 2x/4x/9x selling landmarks identify increasingly severe pressure, with 9x a washout-style extreme. ${move}`;
}
function vvixMeaning(v?:number|null,direction?:string|null,pct2m?:number|null){
  if(!finite(v))return"Volatility-of-volatility is unavailable, so stress inside the volatility market cannot be assessed.";
  const x=Number(v),state=vvixState(v).toLowerCase(),d=(direction||"").toUpperCase();
  const move=d==="FALLING"?"The reading is falling, so volatility anxiety is easing and supporting recovery confirmation.":d==="RISING"?"The reading is rising, so volatility anxiety is increasing and not confirming the recovery yet.":"The reading is broadly stable.";
  const recent=finite(pct2m)?` It is at roughly the ${Math.round(Number(pct2m))}th percentile of the last 40 completed sessions.`:"";
  return`${x.toFixed(1)} is in the ${state} zone under RE-ENTRY's working absolute bands.${recent} ${move}`;
}
function liveSkewMeaning(r?:number|null,direction?:string|null){
  if(!finite(r))return"Live S&P 500 downside-protection pricing is unavailable, so immediate hedging pressure cannot be assessed.";
  const x=Number(r),d=(direction||"").toUpperCase(),state=liveSkewState(r).toLowerCase();
  const move=d==="NARROWING"?"The ratio is narrowing, so immediate crash fear is easing and supporting the recovery.":d==="WIDENING"?"The ratio is widening, so investors are becoming more defensive and this is not confirming the recovery yet.":"The ratio is not showing a meaningful directional change.";
  return`${x.toFixed(2)}x puts the live S&P 500 downside-protection premium in the ${state} zone under RE-ENTRY proxy bands. ${x>=1.20?"Downside protection is extremely expensive versus comparable calls, showing stretched fear and a potential contrarian setup.":x>1.05?"Downside protection is more expensive than upside exposure, showing elevated hedging demand.":"Put and call implied volatility are broadly balanced."} ${move}`;
}
function officialSkewMeaning(v?:number|null,p?:number|null,direction?:string|null){
  if(!finite(v))return"Official Cboe tail-risk pricing is unavailable.";
  const x=Number(v),state=officialSkewState(v,p).toLowerCase(),d=(direction||"").toUpperCase();
  const pctText=finite(p)?` It sits near the ${Math.round(Number(p))}th percentile of the last two years.`:"";
  const move=d==="FALLING"?"Tail-risk pricing is easing, which is more useful for recovery confirmation.":d==="RISING"?"Tail-risk pricing is increasing, so fear is not easing yet.":"There is no strong directional change in the latest official reading.";
  return`${x.toFixed(1)} is ${state} under RE-ENTRY's interpretation bands around the Cboe index.${pctText} High tail-risk pricing is fear context, not a standalone buy signal. ${move}`;
}

function MetricCard({name,symbol,value,benchmark,state,direction,directionTone,interpretation,detail,behavior,behaviorExplanation,freshness}:{name:string;symbol:string;value:string;benchmark:string;state:string;direction?:string|null;directionTone?:string;interpretation:string;detail?:string;behavior:string;behaviorExplanation:string;freshness:string}){
 const dir=direction?.replaceAll("_"," ")||"DIRECTION UNAVAILABLE",tone=stateClass(state);
 return <div className="indicator-card" data-tone={tone}>
   <div className="indicator-title"><div><b>{name}</b><small>{symbol}</small></div><span className="indicator-dot"/></div>
   <strong className="indicator-value">{value}</strong>
   <div className="indicator-badges"><span className={tone}>{state}</span><span className={directionTone||directionClass(direction)}>{dir}</span><span className="behavior-badge">{behavior}</span></div>
   <div className="indicator-freshness">{freshness}</div>
   <p className="plain-explain"><b>CURRENT READ + RE-ENTRY CONTEXT</b>{interpretation}</p>
   <p className="plain-explain behavior-copy"><b>WHY IT MATTERS FOR RE-ENTRY</b>{behaviorExplanation}</p>
   <div className="indicator-reference"><b>LEVELS / NORMAL / EXTREMES</b>{benchmark}</div>
   {detail?<div className="indicator-detail">{detail}</div>:null}
 </div>;
}

export default function ReentryDecisionDetails({washout}:{washout:WashoutSnapshot}){
 const u=washout.unified_engine;
 const w=washout.values as any;
 if(!u||!w)return <section className="card section-card"><div className="notice"><CircleAlert size={16}/> RE-ENTRY ENGINE UNAVAILABLE</div></section>;
 const fast=u.fast_families||{FAST_BREADTH_TURN:washout.families?.fast_breadth_turn??false,MOMENTUM_TURN:washout.families?.momentum_turn??false,NET_VOLUME_TURN:washout.families?.net_volume_turn??false,DOWN_UP_RATIO_RELIEF:washout.families?.down_up_ratio_relief??false};
 const context=u.context_support||{};
 const fastRows=[["Fast breadth",fast.FAST_BREADTH_TURN,"NO BREADTH TURN","Are more stocks starting to recover quickly after the selloff?"],["Breadth momentum",fast.MOMENTUM_TURN,"NO MOMENTUM TURN","Is the overall pace of improving stocks getting stronger rather than weaker?"],["Advance/decline volume",fast.NET_VOLUME_TURN,"NO VOLUME TURN","Is more trading volume flowing into advancing stocks than declining stocks?"],["Selling intensity relief",fast.DOWN_UP_RATIO_RELIEF,"NO RELIEF","Is heavy selling pressure easing enough to suggest sellers are losing control?"]] as const;
 const contextRows=[["Short-term market breadth improving",context.MMFD_IMPROVING,"NOT IMPROVING","Are more U.S. stocks getting back above their very short-term trend?"],["Nasdaq breadth trend turning upward",context.NASI_TURNING_UP,"NOT TURNING UP","Is broader Nasdaq participation beginning to turn up from a weak level?"],["Volatility-of-volatility easing",context.VVIX_EASING,"NOT EASING","Is fear inside the volatility market itself starting to calm down?"],["Downside tail-risk pricing narrowing",context.SKEW_NARROWING,"NOT NARROWING","Is demand for crash protection becoming less extreme?"]] as const;
 const vvix=washout.vvix_live as any,skew=washout.skew_live as any,mmfd=washout.mmfd_live as any,hist=washout.historical_context?.metrics||{};
 const vvixChange=finite(vvix?.change_points_vs_prior_close)?vvix?.change_points_vs_prior_close:finite(w.VVIX)&&finite(w.VVIX_PRIOR_CLOSE)?Number(w.VVIX)-Number(w.VVIX_PRIOR_CLOSE):null;
 const vvixPct2m=vvix?.historical_percentile_2m??w.VVIX_PERCENTILE_2M;
 const officialSkewPct=skew?.official_skew_percentile_2y??w.SKEW_OFFICIAL_PERCENTILE_2Y;
 const officialSkew=skew?.official_skew_latest_close??w.SKEW_OFFICIAL_CLOSE;
 const officialDate=skew?.official_skew_date||"date unavailable";
 const liveSkew=skew?.live_proxy_vol_points??w.SKEW_LIVE_PROXY;
 const liveSkewRatio=skew?.live_proxy_ratio??w.SKEW_LIVE_PROXY_RATIO;
 const liveSkewDirection=skew?.direction_vs_prior_snapshot||w.SKEW_DIRECTION||"NO CHANGE SIGNAL";
 const liveSkewMode=skew?.source_mode||"SOURCE MODE UNAVAILABLE";
 const snapshotTime=u.timestamp_et||washout.snapshot_generated_at_et||w.timestamp_et||"UNAVAILABLE";
 const marketDate=(u as any).market_date||w.market_date||"prior completed session";
 return <><style>{`
 body{background:radial-gradient(circle at 18% -8%,rgba(47,118,80,.10),transparent 28%),radial-gradient(circle at 91% 4%,rgba(163,116,42,.07),transparent 24%),var(--bg)}.card{box-shadow:0 16px 42px rgba(28,40,32,.065);border-color:#d8d4c9}.family-section{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:14px 0 20px}.family-panel{border:1px solid var(--line);border-radius:16px;padding:14px;background:linear-gradient(180deg,rgba(255,255,255,.58),rgba(255,255,255,.24));box-shadow:0 9px 24px rgba(30,42,33,.035)}.family-panel h3{margin:0 0 10px;font-size:13px}.family-row{display:grid;grid-template-columns:1fr auto;gap:4px 12px;padding:10px 0;border-top:1px solid var(--line);font-size:11px}.family-row:first-of-type{border-top:0}.family-row b{font-size:8px;letter-spacing:.045em;border-radius:999px;padding:5px 7px;border:1px solid var(--line);background:rgba(255,255,255,.55);align-self:start}.family-copy{grid-column:1/2;font-size:9px;line-height:1.4;color:var(--muted)}
 .indicator-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.indicator-card{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:16px;padding:16px;background:linear-gradient(180deg,rgba(255,255,255,.66),rgba(255,255,255,.30));box-shadow:0 8px 24px rgba(31,44,35,.035)}.indicator-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#aaa}.indicator-card[data-tone="good-text"]:before{background:var(--green)}.indicator-card[data-tone="warn"]:before{background:var(--amber)}.indicator-card[data-tone="bad-text"]:before{background:var(--red)}.indicator-card[data-tone="extreme-text"]:before{background:linear-gradient(var(--red),var(--amber))}.indicator-title{display:flex;justify-content:space-between;gap:10px}.indicator-title b{font-size:11px}.indicator-title small{display:block;color:var(--muted);font-size:9px;margin-top:2px}.indicator-dot{width:8px;height:8px;border-radius:50%;background:#bbb}.indicator-value{display:block;font-size:26px;margin:10px 0 8px;letter-spacing:-.035em}.indicator-badges{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}.indicator-badges span{border:1px solid currentColor;border-radius:999px;padding:4px 7px;font-size:8px;font-weight:900;letter-spacing:.045em;background:rgba(255,255,255,.45)}.behavior-badge{color:#5d625b}.indicator-freshness{font-size:8px;font-weight:850;letter-spacing:.035em;color:#5c615a;margin-bottom:8px}.plain-explain{font-size:10px;line-height:1.5;margin:8px 0 10px;color:#3f443d}.plain-explain b{display:block;font-size:7px;letter-spacing:.1em;color:var(--muted);margin-bottom:2px}.behavior-copy{background:rgba(163,116,42,.055);padding:8px;border-radius:8px}.indicator-reference{font-size:9px;line-height:1.48;color:#50554e;padding:9px 10px;border-radius:9px;background:#f0eee8}.indicator-reference b{display:block;margin-bottom:2px;font-size:7px;letter-spacing:.12em;color:var(--muted)}.indicator-detail{font-size:9px;line-height:1.45;color:var(--muted);margin-top:6px}.engine-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.engine-meta span{font-size:9px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 8px;background:rgba(255,255,255,.45)}.extreme-text{color:#b75f34}.warn{color:var(--amber)}@media(max-width:900px){.indicator-grid{grid-template-columns:1fr 1fr}}@media(max-width:680px){.family-section,.indicator-grid{grid-template-columns:1fr}}
 `}</style>
 <section className="card section-card"><div className="section-heading"><div><span className="kicker">REVERSAL EVIDENCE</span><h2>What has actually turned?</h2></div></div><div className="family-section"><div className="family-panel"><h3>Fast reversal families · {u.fast_family_count??0}/4</h3>{fastRows.map(([name,on,off,explain])=><div className="family-row" key={name}><span>{name}</span><b className={on?"good-text":"muted"}>{on?"TURNED":off}</b><span className="family-copy">{explain}</span></div>)}</div><div className="family-panel"><h3>Context support · {u.context_support_count??0}/4</h3>{contextRows.map(([name,on,off,explain])=><div className="family-row" key={name}><span>{name}</span><b className={on?"good-text":"muted"}>{on?"CONFIRMED":off}</b><span className="family-copy">{explain}</span></div>)}</div></div><div className="engine-meta"><span>Oversold setup: {u.oversold_gate?"YES":"NO"}</span><span>Data quality: {u.data_quality_status||washout.data_quality?.status||"UNAVAILABLE"}</span><span>Snapshot: {snapshotTime}</span></div></section>
 <section className="card section-card"><div className="section-heading"><div><span className="kicker">INDICATOR DETAIL</span><h2>Current level vs. strategist range</h2></div></div><p className="section-intro">Each indicator shows today's reading, where it sits versus normal/extreme reference levels, the direction of travel, and what that specifically means for RE-ENTRY. Established technician anchors are separated from RE-ENTRY working ranges.</p><div className="indicator-grid">
 <MetricCard name="S&P 500 Stocks Above 20-Day Moving Average" symbol="$SPXA20R · S&P 500 breadth" value={`${plain(w.SPXA20R,1)}%`} benchmark="Established breadth landmarks: <10% extreme washout · <30% oversold · 50% majority/recovery line · >70% broad participation. Intermediate labels are RE-ENTRY interpretation, not vendor-defined canonical bands." state={spxaState(w.SPXA20R)} direction={fast.FAST_BREADTH_TURN?"IMPROVING":"NO BREADTH TURN"} behavior="CONTRARIAN SETUP" behaviorExplanation="Very low breadth is a contrarian setup because widespread weakness can become exhausted. It is not bullish by itself; the turn upward is the confirmation." freshness={fresh("INTRADAY SNAPSHOT",w.SPXA20R_TIMESTAMP_ET||snapshotTime)} interpretation={spxaMeaning(w.SPXA20R,fast.FAST_BREADTH_TURN)}/>
 <MetricCard name="U.S. Equity Breadth - Stocks Above 5-Day Moving Average" symbol="$MMFD · 5-day U.S. equity breadth" value={`${plain(w.MMFD,1)}%`} benchmark="RE-ENTRY short-term breadth framework: <15% extreme washout · 15-30% oversold · 30-50% weak/repairing · 50-70% healthy · 70-85% strong · >85% extreme breadth. 50% is the majority line." state={mmfdState(w.MMFD,w.MMFD_STATE)} direction={context.MMFD_IMPROVING?"IMPROVING":"NOT IMPROVING"} behavior="CONTRARIAN + CONFIRMING" behaviorExplanation="A very low level is contrarian; improvement from that low becomes confirming evidence that participation is recovering." freshness={fresh("INTRADAY SNAPSHOT",mmfd?.timestamp_et||snapshotTime)} detail={`Universe ${mmfd?.universe_size??"-"} · valid ${mmfd?.valid_5d_observations??"-"} · coverage ${finite(mmfd?.coverage_pct)?`${plain(mmfd?.coverage_pct,1)}%`:"UNAVAILABLE"}`} interpretation={mmfdMeaning(w.MMFD,context.MMFD_IMPROVING)}/>
 <MetricCard name="NYSE Breadth Momentum" symbol="$NYMO · McClellan Oscillator" value={signed(w.NYMO,1)} benchmark={historyBenchmark(hist.NYMO,"Established technician anchors: -100 oversold · 0 centerline · +100 overbought. More extreme magnitude should be interpreted with historical percentile/context rather than extra invented fixed bands.")} state={historyState(hist.NYMO,momentumState(w.NYMO))} direction={fast.MOMENTUM_TURN?"IMPROVING":"NO MOMENTUM TURN"} behavior="CONTRARIAN AT EXTREMES" behaviorExplanation="Deep negative readings can mark exhaustion, but the useful confirmation is momentum turning upward from the oversold/negative zone." freshness={fresh("DAILY CLOSE",hist.NYMO?.history_end_date||marketDate)} detail={historyDetail(hist.NYMO)} interpretation={momentumMeaning("NYSE breadth momentum",w.NYMO,fast.MOMENTUM_TURN)}/>
 <MetricCard name="Nasdaq Breadth Momentum" symbol="$NAMO · McClellan Oscillator" value={signed(w.NAMO,1)} benchmark={historyBenchmark(hist.NAMO,"Established technician anchors: -100 oversold · 0 centerline · +100 overbought. More extreme magnitude should be interpreted with historical percentile/context rather than extra invented fixed bands.")} state={historyState(hist.NAMO,momentumState(w.NAMO))} direction={fast.MOMENTUM_TURN?"IMPROVING":"NO MOMENTUM TURN"} behavior="CONTRARIAN AT EXTREMES" behaviorExplanation="Deeply negative Nasdaq breadth can be a contrarian setup. A turn higher is what converts that setup into recovery evidence." freshness={fresh("DAILY CLOSE",hist.NAMO?.history_end_date||marketDate)} detail={historyDetail(hist.NAMO)} interpretation={momentumMeaning("Nasdaq breadth momentum",w.NAMO,fast.MOMENTUM_TURN)}/>
 <MetricCard name="Nasdaq Breadth Momentum Strength" symbol="NASI+ RSI · derived from Nasdaq Summation Index" value={plain(w.NASI_RSI,1)} benchmark="RE-ENTRY momentum-strength framework: below 30 = oversold · below 20 = very oversold · below 10 = extreme · 30-70 = middle range · above 70 = overbought · above 90 = extreme. These are interpretation bands for the derived breadth-momentum reading, not official market thresholds." state={nasiState(w.NASI_RSI)} direction={w.NASI_DIRECTION} directionTone={w.NASI_DIRECTION==="FALLING"?"bad-text":w.NASI_DIRECTION==="RISING"?"good-text":undefined} behavior="CONTRARIAN + CONFIRMING" behaviorExplanation="Oversold is contrarian context; a rising breadth-momentum reading is confirmation that the broader Nasdaq recovery is becoming more durable." freshness={fresh("DAILY / PRIOR COMPLETED CLOSE",marketDate)} detail={finite(w.NASI_EMA10)?`Slow breadth trend ${plain(w.NASI_EMA10,1)}`:undefined} interpretation={nasiMeaning(w.NASI_RSI,w.NASI_DIRECTION)}/>
 <MetricCard name="NYSE Buying vs Selling Volume" symbol="$NYUD · advance/decline volume" value={signed(w.NYUD,1)} benchmark={historyBenchmark(hist.NYUD,"Defensible anchor: 0 is balance. Above 0 = advancing volume dominates; below 0 = declining volume dominates. Raw magnitude is feed-dependent, so extremes use empirical historical percentile once reliable - no fixed 250/1000/2500 bands.")} state={historyState(hist.NYUD,volumeBreadthState(w.NYUD))} direction={fast.NET_VOLUME_TURN?"IMPROVING":"NO VOLUME TURN"} behavior="CONFIRMING" behaviorExplanation="Positive/rising volume breadth supports the idea that the rebound has real participation behind it. Magnitude extremes are percentile-based, not hard-coded." freshness={fresh("INTRADAY",w.NYUD_TIMESTAMP_ET||snapshotTime)} detail={historyDetail(hist.NYUD)} interpretation={volumeMeaning("NYSE buying-versus-selling volume",w.NYUD,fast.NET_VOLUME_TURN)}/>
 <MetricCard name="Nasdaq Buying vs Selling Volume" symbol="$NAUD · advance/decline volume" value={signed(w.NAUD,1)} benchmark={historyBenchmark(hist.NAUD,"Defensible anchor: 0 is balance. Above 0 = advancing volume dominates; below 0 = declining volume dominates. Raw magnitude is feed-dependent, so extremes use empirical historical percentile once reliable - no fixed 250/1000/2500 bands.")} state={historyState(hist.NAUD,volumeBreadthState(w.NAUD))} direction={fast.NET_VOLUME_TURN?"IMPROVING":"NO VOLUME TURN"} behavior="CONFIRMING" behaviorExplanation="Positive/rising Nasdaq volume breadth supports a healthier recovery. Magnitude extremes are percentile-based, not hard-coded." freshness={fresh("INTRADAY",w.NAUD_TIMESTAMP_ET||snapshotTime)} detail={historyDetail(hist.NAUD)} interpretation={volumeMeaning("Nasdaq buying-versus-selling volume",w.NAUD,fast.NET_VOLUME_TURN)}/>
 <MetricCard name="NYSE Down/Up Volume Ratio" symbol="NYSE D/U" value={finite(w.nyse_down_up_ratio)?`${plain(w.nyse_down_up_ratio,2)}x`:"UNAVAILABLE"} benchmark={historyBenchmark(hist.nyse_down_up_ratio,"Classic breadth landmarks: 1.0x balance · 2x elevated selling · 4x heavy selling · 9x washout-style extreme; inverse ratios indicate buying dominance.")} state={historyState(hist.nyse_down_up_ratio,ratioState(w.nyse_down_up_ratio))} direction={fast.DOWN_UP_RATIO_RELIEF?"RELIEF":"NO RELIEF"} behavior="CONTRARIAN AT EXTREMES" behaviorExplanation="Very high selling ratios can mark panic/exhaustion. The confirmation is the ratio collapsing back toward 1 as selling pressure eases." freshness={fresh("INTRADAY",snapshotTime)} detail={historyDetail(hist.nyse_down_up_ratio)} interpretation={ratioMeaning("NYSE down/up volume",w.nyse_down_up_ratio,fast.DOWN_UP_RATIO_RELIEF)}/>
 <MetricCard name="Nasdaq Down/Up Volume Ratio" symbol="NASDAQ D/U" value={finite(w.nasdaq_down_up_ratio)?`${plain(w.nasdaq_down_up_ratio,2)}x`:"UNAVAILABLE"} benchmark={historyBenchmark(hist.nasdaq_down_up_ratio,"Classic breadth landmarks: 1.0x balance · 2x elevated selling · 4x heavy selling · 9x washout-style extreme; inverse ratios indicate buying dominance.")} state={historyState(hist.nasdaq_down_up_ratio,ratioState(w.nasdaq_down_up_ratio))} direction={fast.DOWN_UP_RATIO_RELIEF?"RELIEF":"NO RELIEF"} behavior="CONTRARIAN AT EXTREMES" behaviorExplanation="Panic-level selling can be contrarian, but the useful recovery evidence is relief: the selling ratio falls sharply as buyers return." freshness={fresh("INTRADAY",snapshotTime)} detail={historyDetail(hist.nasdaq_down_up_ratio)} interpretation={ratioMeaning("Nasdaq down/up volume",w.nasdaq_down_up_ratio,fast.DOWN_UP_RATIO_RELIEF)}/>
 <MetricCard name="Volatility of Market Volatility" symbol="$VVIX · volatility-of-volatility" value={plain(w.VVIX,1)} benchmark={`RE-ENTRY working absolute bands: <70 extreme complacency · 70-80 calm · 80-100 normal · 100-120 elevated stress · >120 extreme stress. Recent 2-month empirical context: ${percentile(vvixPct2m)}. Treat percentile as the stronger regime-relative reference.`} state={vvix?.state?.replaceAll("_"," ")||w.VVIX_STATE?.replaceAll("_"," ")||vvixState(w.VVIX)} direction={vvix?.direction_vs_prior_close||w.VVIX_DIRECTION} behavior="STRESS + RECOVERY CONTEXT" behaviorExplanation="The absolute band is a RE-ENTRY interpretation aid, while the recent percentile provides regime-relative context. A falling reading confirms stress is easing; a rising reading does not." freshness={fresh("INTRADAY",vvix?.timestamp_et||snapshotTime)} detail={`Prior close ${plain(vvix?.prior_close??w.VVIX_PRIOR_CLOSE,1)} · change ${signed(vvixChange,1)} pts · recent window ${vvix?.recent_percentile_sessions??vvix?.recent_context_sessions??40} sessions`} interpretation={vvixMeaning(w.VVIX,vvix?.direction_vs_prior_close||w.VVIX_DIRECTION,vvixPct2m)}/>
 <MetricCard name="Live S&P 500 Downside Protection Premium" symbol="25-delta put IV / call IV" value={finite(liveSkewRatio)?`${plain(liveSkewRatio,2)}x`:"UNAVAILABLE"} benchmark="RE-ENTRY proxy bands, not official Cboe thresholds: <0.95 upside skew · 0.95-1.05 balanced · 1.05-1.10 elevated downside protection · 1.10-1.20 stretched · >=1.20 extreme downside protection. Direction - narrowing vs widening - is more important for confirmation." state={liveSkewState(liveSkewRatio)} direction={liveSkewDirection} behavior="FEAR + RECOVERY CONTEXT" behaviorExplanation="The ratio compares downside put implied volatility with comparable call implied volatility. Extreme downside skew is contrarian fear context; narrowing is the confirmation that immediate crash fear is easing." freshness={fresh("INTRADAY",skew?.timestamp_et||snapshotTime)} detail={`Downside-protection premium spread ${finite(liveSkew)?`${plain(liveSkew,2)} volatility points`:"UNAVAILABLE"} · source ${liveSkewMode}`} interpretation={liveSkewMeaning(liveSkewRatio,liveSkewDirection)}/>
 <MetricCard name="Official Cboe Tail-Risk Index" symbol="$SKEW · Cboe tail-risk index" value={plain(officialSkew,1)} benchmark={`Cboe index with RE-ENTRY interpretation bands: ~100 baseline · 125-140 elevated · 140-150 high · >150 extreme. Two-year empirical context: ${percentile(officialSkewPct)}. Percentile and direction should carry more weight than the working cutoffs.`} state={officialSkewState(officialSkew,officialSkewPct)} direction={skew?.official_skew_direction} behavior="CONTRARIAN / CONTEXTUAL" behaviorExplanation="High tail-risk pricing can reflect fear, but the official tail-risk index is not a standalone buy signal. Easing from an extreme while breadth improves is more useful confirmation." freshness={fresh("DAILY CLOSE",officialDate)} detail={`Latest official date ${officialDate}`} interpretation={officialSkewMeaning(officialSkew,officialSkewPct,skew?.official_skew_direction)}/>
 </div></section></>;
}
