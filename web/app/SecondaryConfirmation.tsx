type Family = {
  name?: string;
  state?: string;
  supportive?: boolean;
  benchmark?: string;
  source?: string;
  validation_status?: string;
  validation_note?: string;
  retail_explanation?: string;
  signal_behavior?: "CONTRARIAN" | "CONFIRMING" | "CONTEXTUAL" | string;
  behavior_explanation?: string;
  freshness_type?: "INTRADAY_SNAPSHOT" | "DAILY_CLOSE" | "UNAVAILABLE" | string;
  last_updated?: string | null;
  current_ratio?: number;
  prior_ratio?: number;
  nasdaq_advance_share?: number;
  supportive_components?: number;
  equity_put_call?: number;
  index_put_call?: number;
  total_put_call?: number;
};

type T2108Context = {
  name?: string;
  symbol?: string;
  value?: number;
  prior_value?: number;
  change_points?: number;
  state?: string;
  direction?: string;
  decision_input?: boolean;
  benchmark?: string;
  retail_explanation?: string;
  behavior_explanation?: string;
  freshness_type?: "DAILY_CLOSE" | "UNAVAILABLE" | string;
  last_updated?: string | null;
  source?: string;
  validation_status?: string;
  validation_note?: string;
  universe_size?: number;
  valid_count?: number;
  coverage_pct?: number;
};

type Overlay = {
  version?: string;
  decision_input?: boolean;
  changes_deploy_trigger?: boolean;
  changes_recovery_stage?: boolean;
  supportive_family_count?: number;
  family_count?: number;
  interpretation?: string;
  families?: Record<string, Family>;
  breadth_context?: { t2108?: T2108Context };
};

const finite=(v?:number)=>typeof v==="number"&&Number.isFinite(v);
const pct=(v?:number)=>finite(v)?`${(Number(v)*100).toFixed(1)}%`:"UNAVAILABLE";
const percentPoints=(v?:number)=>finite(v)?`${Number(v).toFixed(1)}%`:"UNAVAILABLE";
const num=(v?:number,d=2)=>finite(v)?Number(v).toFixed(d):"UNAVAILABLE";
const freshnessLabel=(family:Family|T2108Context)=>{
  const kind=(family.freshness_type||"UNAVAILABLE").replaceAll("_"," ");
  return family.last_updated?`${kind} · updated ${family.last_updated}`:kind;
};

function readout(key:string,family:Family){
  if(key==="vol_structure")return `VIX/VIX3M ${num(family.current_ratio)} · prior ${num(family.prior_ratio)}`;
  if(key==="breadth_thrust")return `Nasdaq advancing share ${pct(family.nasdaq_advance_share)}`;
  if(key==="risk_appetite")return `${family.supportive_components??0}/3 risk-on relationships confirming`;
  if(key==="options_sentiment")return `Equity P/C ${num(family.equity_put_call)} · Index P/C ${num(family.index_put_call)} · Total P/C ${num(family.total_put_call)}`;
  return"Current readout unavailable";
}

function rangeMap(key:string,family:Family){
  if(key==="vol_structure")return "Established anchor: 1.00 separates contango from backwardation. RE-ENTRY context bands: <0.90 calm contango · 0.90-0.99 normal contango · 1.00-1.05 stress/backwardation · >1.05 acute stress. The key recovery event is normalization back below 1.00.";
  if(key==="breadth_thrust")return "Established anchor: 50% is the majority line. RE-ENTRY participation bands: <40% defensive · 40-50% weak/mixed · 50-55% positive · >55% broad participation. This is not the classic Zweig 10-day thrust.";
  if(key==="risk_appetite")return "RE-ENTRY composite framework: 0/3 defensive · 1/3 mixed · 2/3 broadening · 3/3 broad risk-on. Components are RSP/SPY, IWM/SPY and HYG/LQD 5-day relative momentum. This is a product composite, not an industry-standard index.";
  if(key==="options_sentiment")return "Cboe provides the raw put/call data. RE-ENTRY interpretation bands for equity P/C: <0.50 complacent · 0.50-0.70 normal · 0.70-0.90 fear · >=0.90 high fear. Around 0.70 is a useful historical normal anchor; the detailed buckets are RE-ENTRY context, not official Cboe thresholds.";
  return family.benchmark||"Range map unavailable";
}

function currentContext(key:string,family:Family){
  if(key==="vol_structure"){
    if(!finite(family.current_ratio))return"Current term-structure ratio unavailable.";
    const x=Number(family.current_ratio);
    const zone=x<.90?"CALM CONTANGO":x<1?"NORMAL CONTANGO":x<=1.05?"STRESS / BACKWARDATION":"ACUTE STRESS";
    const move=finite(family.prior_ratio)?x<Number(family.prior_ratio)?"The ratio is falling, so near-term volatility stress is easing.":x>Number(family.prior_ratio)?"The ratio is rising, so near-term stress is worsening.":"The ratio is roughly unchanged.":"Prior comparison is unavailable.";
    return `${x.toFixed(2)} places the curve in ${zone}. ${move} For RE-ENTRY, the important confirmation is repair toward and below the established 1.00 contango/backwardation boundary.`;
  }
  if(key==="breadth_thrust"){
    if(!finite(family.nasdaq_advance_share))return"Current advancing-share reading unavailable.";
    const x=Number(family.nasdaq_advance_share)*100;
    const zone=x<40?"DEFENSIVE":x<50?"WEAK / MIXED":x<55?"POSITIVE":"BROAD PARTICIPATION";
    return `${x.toFixed(1)}% of Nasdaq issues advanced - ${zone}. ${x>=55?"Participation is broad enough to support the rebound.":x>=50?"A majority of stocks advanced, but participation is not yet a strong thrust.":"Fewer than half of Nasdaq issues advanced, so the rebound remains narrow."} This is context only and cannot delay DEPLOY.`;
  }
  if(key==="risk_appetite"){
    const n=family.supportive_components??0;
    const zone=n===0?"DEFENSIVE":n===1?"MIXED":n===2?"BROADENING":"BROAD RISK-ON";
    return `${n}/3 relationships are confirming - ${zone}. ${n>=2?"Risk-taking is spreading beyond mega-cap leadership into equal-weight stocks, small caps and/or credit, which strengthens recovery confirmation.":"Risk-taking is still uneven, so the market has not yet shown broad appetite beyond the strongest leadership."}`;
  }
  if(key==="options_sentiment"){
    if(!finite(family.equity_put_call))return"Current equity put/call ratio unavailable.";
    const x=Number(family.equity_put_call);
    const zone=x<.50?"COMPLACENT":x<.70?"NORMAL":x<.90?"FEAR":"HIGH FEAR";
    return `Equity put/call is ${x.toFixed(2)} - ${zone} under the RE-ENTRY sentiment framework. ${x>=.90?"Protection demand is unusually heavy, creating a strong contrarian backdrop. The useful confirmation would be fear easing while breadth improves.":x>=.70?"Fear is elevated enough to support a contrarian setup, but it is not extreme and does not confirm recovery by itself.":x<.50?"Options traders are complacent, so sentiment is not providing a contrarian re-entry tailwind.":"Sentiment is near its normal anchor and is not a major driver of the re-entry call."}`;
  }
  return family.retail_explanation||"Context unavailable.";
}

function tone(state?:string,supportive?:boolean){
  const s=(state||"").toUpperCase();
  if(s.includes("ACUTE")||s.includes("DEFENSIVE"))return"secondary-bad";
  if(supportive||s.includes("NORMALIZED")||s.includes("BROAD")||s.includes("THRUST"))return"secondary-good";
  if(s.includes("BUILDING")||s.includes("FEAR")||s.includes("BACKWARDATION")||s.includes("MIXED"))return"secondary-warn";
  return"secondary-neutral";
}

function t2108Tone(state?:string){
  const s=(state||"").toUpperCase();
  if(s.includes("EXTREME_OVERSOLD")||s==="OVERSOLD")return"secondary-warn";
  if(s==="STRONG"||s.includes("VERY_EXTENDED"))return"secondary-good";
  if(s==="WEAK")return"secondary-warn";
  return"secondary-neutral";
}

function t2108Range(){return "TC2000 defines T2108 as NYSE stocks above the 40-day moving average. Established anchor: 50% is the majority line. RE-ENTRY context bands: <20% extreme washout · 20-40% weak/oversold · 40-60% mixed · 60-80% strong · >80% very broad/extended. These bucket labels are RE-ENTRY interpretation, not TC2000-published trading thresholds.";}
function t2108Context(t:T2108Context){
  if(!finite(t.value))return"Intermediate breadth is unavailable.";
  const x=Number(t.value),d=(t.direction||"").toUpperCase();
  const zone=x<20?"EXTREME WASHOUT":x<40?"WEAK / OVERSOLD":x<60?"MIXED":x<80?"STRONG":"VERY BROAD / EXTENDED";
  const move=d==="RISING"?"It is rising, so intermediate breadth is repairing.":d==="FALLING"?"It is falling, so intermediate breadth is still deteriorating.":"It is roughly flat, so there is no clear intermediate-breadth confirmation.";
  return `${x.toFixed(1)}% of NYSE stocks are above their 40-day average - ${zone}. ${x<50?"Less than half the universe is above trend, so intermediate breadth remains damaged.":"A majority of the universe is above trend."} ${move} This is context only and must not delay DEPLOY.`;
}

function recoveryHeadline(stage?:string){
  const s=(stage||"NOT_APPLICABLE").toUpperCase();
  if(s==="BROAD_CONFIRMATION")return"Broad confirmation - the rebound is being supported by a wider set of market evidence.";
  if(s==="DEVELOPING")return"Developing recovery - confirmation is building, but the market is not fully broad yet.";
  if(s==="EARLY")return"Early recovery - there is enough evidence to stop waiting, but confirmation is still incomplete.";
  return"No active recovery stage - secondary signals are context only until a DEPLOY setup exists.";
}

function recoveryItems(families:Record<string,Family>,t2108?:T2108Context){
  const vol=families.vol_structure||{};
  const breadth=families.breadth_thrust||{};
  const risk=families.risk_appetite||{};
  const options=families.options_sentiment||{};
  const items=[
    {label:"Volatility stress",state:(vol.state||"UNAVAILABLE").replaceAll("_"," "),tone:tone(vol.state,vol.supportive),text:currentContext("vol_structure",vol)},
    {label:"Participation",state:(breadth.state||"UNAVAILABLE").replaceAll("_"," "),tone:tone(breadth.state,breadth.supportive),text:currentContext("breadth_thrust",breadth)},
    {label:"Risk appetite",state:(risk.state||"UNAVAILABLE").replaceAll("_"," "),tone:tone(risk.state,risk.supportive),text:currentContext("risk_appetite",risk)},
    {label:"Options sentiment",state:(options.state||"UNAVAILABLE").replaceAll("_"," "),tone:tone(options.state,options.supportive),text:currentContext("options_sentiment",options)}
  ];
  if(t2108)items.push({label:"Intermediate breadth",state:`${(t2108.state||"UNAVAILABLE").replaceAll("_"," ")} · ${(t2108.direction||"UNAVAILABLE").replaceAll("_"," ")}`,tone:t2108Tone(t2108.state),text:t2108Context(t2108)});
  return items;
}

export default function SecondaryConfirmation({washout}:{washout:any}){
  const overlay:Overlay|undefined=washout?.unified_engine?.secondary_confirmation||washout?.secondary_confirmation;
  if(!overlay?.families)return null;
  const entries=Object.entries(overlay.families);
  const t2108=overlay.breadth_context?.t2108||washout?.t2108_context;
  const stage=washout?.unified_engine?.recovery_stage;
  const readItems=recoveryItems(overlay.families,t2108);
  return <section className="card section-card secondary-confirmation">
    <style>{`
      .secondary-confirmation{background:linear-gradient(145deg,#fbfaf7 0%,#f7faf8 52%,#f3f7f4 100%)}
      .secondary-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:16px}.secondary-score{font-size:11px;font-weight:900;border:1px solid rgba(47,118,80,.22);background:rgba(47,118,80,.07);padding:8px 10px;border-radius:999px;white-space:nowrap}
      .recovery-read{margin:0 0 16px;border:1px solid rgba(47,118,80,.20);border-radius:16px;padding:16px;background:linear-gradient(100deg,rgba(47,118,80,.07),rgba(255,255,255,.55))}.recovery-read-kicker{font-size:8px;font-weight:900;letter-spacing:.11em;color:var(--muted)}.recovery-read h3{margin:5px 0 12px;font-size:18px;line-height:1.3;letter-spacing:-.025em}.recovery-read-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.recovery-read-item{border:1px solid var(--line);border-radius:11px;padding:10px;background:rgba(255,255,255,.58)}.recovery-read-item span{display:block;font-size:8px;font-weight:900;letter-spacing:.07em;color:var(--muted)}.recovery-read-item b{display:block;margin:4px 0 5px;font-size:10px}.recovery-read-item p{margin:0;font-size:9px;line-height:1.45;color:#454a43}.recovery-read-note{margin:10px 0 0;font-size:9px;line-height:1.45;color:var(--muted)}
      .secondary-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.secondary-card{position:relative;border:1px solid var(--line);border-radius:15px;padding:14px;background:rgba(255,255,255,.58);overflow:hidden}.secondary-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#a8aaa4}.secondary-card.secondary-good:before{background:var(--green)}.secondary-card.secondary-warn:before{background:var(--amber)}.secondary-card.secondary-bad:before{background:var(--red)}
      .secondary-title{font-size:10px;font-weight:850}.secondary-symbol{display:block;margin-top:2px;color:var(--muted);font-size:8px;font-weight:800;letter-spacing:.05em}.secondary-meta{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 9px}.secondary-state{display:inline-block;padding:4px 7px;border-radius:999px;border:1px solid currentColor;font-size:8px;font-weight:900;letter-spacing:.045em}.secondary-good .secondary-state{color:var(--green)}.secondary-warn .secondary-state{color:var(--amber)}.secondary-bad .secondary-state{color:var(--red)}
      .secondary-readout{font-size:12px;font-weight:800;line-height:1.35}.secondary-plain,.secondary-behavior-copy{margin:9px 0 0;font-size:10px;line-height:1.5;color:#3f443d}.secondary-plain b,.secondary-behavior-copy b{display:block;font-size:8px;letter-spacing:.08em;color:var(--muted);margin-bottom:2px}.secondary-freshness{margin-top:8px;font-size:8px;font-weight:850;letter-spacing:.04em;color:#565b54}.secondary-benchmark{margin-top:9px;padding:9px;border-radius:9px;background:#f0eee8;font-size:9px;line-height:1.5;color:#53574f}.secondary-benchmark b{display:block;font-size:7px;letter-spacing:.1em;color:var(--muted);margin-bottom:3px}.secondary-validation{margin-top:8px;font-size:8px;font-weight:850;letter-spacing:.04em;color:var(--muted)}.secondary-note{margin:6px 0 0;font-size:9px;line-height:1.42;color:var(--muted)}
      .secondary-foot{margin:13px 0 0;font-size:10px;line-height:1.5;color:var(--muted)}
      .breadth-context-wrap{margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}.breadth-context-label{font-size:8px;font-weight:900;letter-spacing:.1em;color:var(--muted);margin-bottom:8px}.breadth-context-card{display:grid;grid-template-columns:minmax(150px,.8fr) minmax(160px,.8fr) minmax(0,2fr);gap:14px;align-items:start}.breadth-context-card .secondary-card{height:100%}.breadth-context-summary{border:1px solid var(--line);border-radius:15px;padding:14px;background:rgba(255,255,255,.52)}.breadth-context-summary strong{display:block;font-size:28px;letter-spacing:-.04em;margin:5px 0}.breadth-context-summary small{display:block;color:var(--muted);font-size:8px;line-height:1.5}.breadth-context-copy{border:1px solid var(--line);border-radius:15px;padding:14px;background:linear-gradient(90deg,rgba(163,116,42,.055),rgba(255,255,255,.25));font-size:10px;line-height:1.55;color:#3f443d}.breadth-context-copy b{display:block;font-size:8px;letter-spacing:.08em;color:var(--muted);margin-bottom:3px}
      @media(max-width:1050px){.recovery-read-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:900px){.secondary-grid{grid-template-columns:1fr}.breadth-context-card{grid-template-columns:1fr 1fr}.breadth-context-copy{grid-column:1/-1}}@media(max-width:620px){.recovery-read-grid{grid-template-columns:1fr}.secondary-head{display:block}.secondary-score{display:inline-block;margin-top:10px}.breadth-context-card{grid-template-columns:1fr}.breadth-context-copy{grid-column:auto}}
    `}</style>
    <div className="secondary-head"><div><span className="kicker">SECONDARY CONFIRMATION</span><h2 style={{margin:"4px 0 0",fontSize:25,letterSpacing:"-.035em"}}>Is the recovery broadening?</h2></div><div className="secondary-score">{overlay.supportive_family_count??0}/{overlay.family_count??entries.length} supportive</div></div>
    <div className="recovery-read"><div className="recovery-read-kicker">RECOVERY READ</div><h3>{recoveryHeadline(stage)}</h3><div className="recovery-read-grid">{readItems.map(item=><div key={item.label} className="recovery-read-item"><span>{item.label.toUpperCase()}</span><b className={item.tone.replace("secondary-","")}>{item.state}</b><p>{item.text}</p></div>)}</div><p className="recovery-read-note">Each read states where today's value sits versus normal/extreme reference levels and what it means for RE-ENTRY. Established anchors are explicitly separated from RE-ENTRY working ranges. This remains descriptive only and does not alter DEPLOY.</p></div>
    <div className="secondary-grid">{entries.map(([key,family])=><div key={key} className={`secondary-card ${tone(family.state,family.supportive)}`}>
      <div className="secondary-title">{family.name||key.replaceAll("_"," ").toUpperCase()}</div>
      <div className="secondary-meta"><span className="secondary-state">{(family.state||"UNAVAILABLE").replaceAll("_"," ")}</span></div>
      <div className="secondary-readout">{readout(key,family)}</div>
      <div className="secondary-freshness">{freshnessLabel(family)}</div>
      <p className="secondary-plain"><b>CURRENT READ + RE-ENTRY CONTEXT</b>{currentContext(key,family)}</p>
      <div className="secondary-benchmark"><b>LEVELS / NORMAL / EXTREMES</b>{rangeMap(key,family)}</div>
      <p className="secondary-behavior-copy"><b>WHY IT MATTERS FOR RE-ENTRY</b>{family.behavior_explanation||"Signal interpretation unavailable."}</p>
      <div className="secondary-validation">{(family.validation_status||"RESEARCH PENDING").replaceAll("_"," ")}</div>
      <p className="secondary-note">{family.validation_note}</p>
    </div>)}</div>
    {t2108?<div className="breadth-context-wrap"><div className="breadth-context-label">ADDITIONAL BREADTH CONTEXT · DOES NOT CHANGE THE 4-FAMILY SCORE</div><div className="breadth-context-card">
      <div className={`secondary-card ${t2108Tone(t2108.state)}`}><div className="secondary-title">NYSE Stocks Above 40-Day Moving Average<span className="secondary-symbol">T2108 reference · reconstructed breadth</span></div><div className="secondary-meta"><span className="secondary-state">{(t2108.state||"UNAVAILABLE").replaceAll("_"," ")}</span><span className="secondary-state">{(t2108.direction||"UNAVAILABLE").replaceAll("_"," ")}</span></div><div className="secondary-readout">{percentPoints(t2108.value)} above 40D SMA · prior {percentPoints(t2108.prior_value)}</div><div className="secondary-freshness">{freshnessLabel(t2108)}</div><div className="secondary-benchmark"><b>LEVELS / NORMAL / EXTREMES</b>{t2108Range()}</div></div>
      <div className="breadth-context-summary"><span className="secondary-title">Breadth coverage</span><strong>{finite(t2108.coverage_pct)?`${Number(t2108.coverage_pct).toFixed(1)}%`:"UNAVAILABLE"}</strong><small>{t2108.valid_count??"-"} valid NYSE stocks of {t2108.universe_size??"-"} tracked</small><small>{t2108.source||"Source unavailable"}</small></div>
      <div className="breadth-context-copy"><b>CURRENT READ + RE-ENTRY CONTEXT</b>{t2108Context(t2108)}<br/><br/><b>WHY IT MATTERS FOR RE-ENTRY</b>{t2108.behavior_explanation||"Interpretation unavailable."}<br/><br/><b>STATUS</b>{(t2108.validation_status||"RESEARCH_PENDING").replaceAll("_"," ")} · NON-DECISION CONTEXT</div>
    </div></div>:null}
    <p className="secondary-foot">Range provenance is explicit: Cboe supplies options data; 1.00 is the established VIX/VIX3M contango/backwardation anchor; 50% is the breadth majority line; TC2000 defines T2108. Other bucket labels are RE-ENTRY interpretation frameworks unless validated empirical percentiles are available. {overlay.interpretation}</p>
  </section>;
}
