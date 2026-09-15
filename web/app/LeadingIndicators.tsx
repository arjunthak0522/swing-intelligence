type Indicator = {
  name?: string;
  state?: string;
  direction?: string;
  role?: string;
  status?: string;
  benchmark?: string;
  meaning?: string;
  freshness_type?: string;
  last_updated?: string | null;
  current_10d_ema?: number;
  current_raw_advance_share?: number;
  recent_10_session_low_ema?: number;
  session_count?: number;
  triggered?: boolean;
  current_namo?: number;
  change_1_session?: number;
  change_3_sessions?: number;
  velocity_percentile?: number | null;
  sample_velocity_percentile?: number | null;
  history_sessions?: number;
  above_5dma_pct?: number;
  above_10dma_pct?: number;
  change_5dma_points?: number | null;
  change_10dma_points?: number | null;
  coverage_5dma_pct?: number;
  coverage_10dma_pct?: number;
  hyg_lqd_ratio?: number;
  change_1d?: number | null;
  change_5d?: number | null;
  double_counted_in_secondary_score?: boolean;
};

type LeadingBlock = {
  version?: string;
  decision_input?: boolean;
  changes_deploy_trigger?: boolean;
  changes_recovery_stage?: boolean;
  creates_new_score?: boolean;
  purpose?: string;
  indicators?: Record<string, Indicator>;
};

const finite=(v?:number|null)=>typeof v==="number"&&Number.isFinite(v);
const num=(v?:number|null,d=2)=>finite(v)?Number(v).toFixed(d):"UNAVAILABLE";
const pct=(v?:number|null,d=1)=>finite(v)?`${Number(v).toFixed(d)}%`:"UNAVAILABLE";
const ratioPct=(v?:number|null,d=1)=>finite(v)?`${(Number(v)*100).toFixed(d)}%`:"UNAVAILABLE";
const signedPct=(v?:number|null,d=2)=>finite(v)?`${Number(v)>=0?"+":""}${(Number(v)*100).toFixed(d)}%`:"UNAVAILABLE";
const signedPts=(v?:number|null,d=1)=>finite(v)?`${Number(v)>=0?"+":""}${Number(v).toFixed(d)} pts`:"UNAVAILABLE";

function tone(indicator:Indicator){
  const s=(indicator.state||"").toUpperCase();
  const d=(indicator.direction||"").toUpperCase();
  if(s.includes("THRUST_TRIGGERED")||s.includes("BROAD_REPAIR")||s.includes("IMPROVING")||s.includes("TURNING_UP")||d==="RISING")return"lead-good";
  if(s.includes("WASHED_OUT")||s.includes("EARLY_TURN")||s.includes("BUILDING"))return"lead-warn";
  if(s.includes("DETERIORATING")||s.includes("TURNING_DOWN")||d==="FALLING")return"lead-bad";
  return"lead-neutral";
}

function readout(key:string,i:Indicator){
  if(key==="zweig_breadth_thrust")return `${ratioPct(i.current_10d_ema)} 10-day EMA · raw ${ratioPct(i.current_raw_advance_share)}`;
  if(key==="mcclellan_velocity")return `NAMO ${num(i.current_namo,1)} · 1-session ${finite(i.change_1_session)?`${Number(i.change_1_session)>=0?"+":""}${Number(i.change_1_session).toFixed(1)}`:"UNAVAILABLE"}`;
  if(key==="nasdaq_short_breadth")return `Above 5D ${pct(i.above_5dma_pct)} · above 10D ${pct(i.above_10dma_pct)}`;
  if(key==="credit_risk_turn")return `HYG/LQD ${num(i.hyg_lqd_ratio,4)} · 1D ${signedPct(i.change_1d)} · 5D ${signedPct(i.change_5d)}`;
  return"Current reading unavailable";
}

function rangeMap(key:string,i:Indicator){
  if(key==="zweig_breadth_thrust")return "<40% WASHED OUT / setup · 40-50% WEAK · 50-61.5% REPAIRING · >61.5% THRUST LEVEL. Classic Zweig signal requires a move from <40% to >61.5% within 10 sessions.";
  if(key==="mcclellan_velocity")return "NAMO level: <-100 OVERSOLD · -100 to 0 NEGATIVE · 0 to +100 POSITIVE · >+100 OVERBOUGHT. Velocity is judged by historical percentile when enough history exists: <25th weak · 25-75th normal · 75-90th strong acceleration · >90th extreme acceleration.";
  if(key==="nasdaq_short_breadth")return "RE-ENTRY short-breadth bands: <20% EXTREME WASHOUT · 20-30% OVERSOLD · 30-50% WEAK · 50-70% HEALTHY · 70-80% STRONG · >80% EXTREME. 50% is the key majority line.";
  if(key==="credit_risk_turn")return "5-day HYG/LQD relative momentum: <0 DEFENSIVE · ~0 NEUTRAL · >0 SUPPORTIVE. There is no reliable universal raw-ratio extreme, so EXTREME labels must come from historical percentiles rather than an invented fixed number.";
  return i.benchmark||"Range map unavailable";
}

function currentContext(key:string,i:Indicator){
  if(key==="zweig_breadth_thrust"){
    if(!finite(i.current_10d_ema))return "Current level unavailable.";
    const x=Number(i.current_10d_ema)*100;
    const zone=x<40?"WASHED OUT":x<50?"WEAK":x<61.5?"REPAIRING":"THRUST LEVEL";
    const implication=x<40?"Breadth is still deeply compressed. That is a contrarian setup, not confirmation. We want a fast surge out of this zone.":x<61.5?"Breadth is repairing, but the classic thrust threshold has not been reached.":"Breadth participation is exceptionally strong. If this followed a sub-40 reading within 10 sessions, the classic Zweig thrust condition is satisfied.";
    return `${x.toFixed(1)}% puts this reading in the ${zone} zone. ${implication}`;
  }
  if(key==="mcclellan_velocity"){
    if(!finite(i.current_namo))return "Current level unavailable.";
    const x=Number(i.current_namo),chg=finite(i.change_1_session)?Number(i.change_1_session):null;
    const zone=x<-100?"OVERSOLD":x<0?"NEGATIVE":x<=100?"POSITIVE":"OVERBOUGHT";
    const accel=chg==null?"Velocity is unavailable.":chg>15?"The one-session change is a strong upward acceleration.":chg>0?"Momentum is improving, but only modestly.":chg< -15?"Breadth momentum is deteriorating quickly.":"Momentum is slipping rather than accelerating.";
    return `NAMO ${x.toFixed(1)} is in the ${zone} zone. ${accel} For RE-ENTRY, acceleration out of a negative/oversold zone is more useful than waiting for the oscillator to become fully positive.`;
  }
  if(key==="nasdaq_short_breadth"){
    if(!finite(i.above_5dma_pct)||!finite(i.above_10dma_pct))return "Current breadth level unavailable.";
    const x=Number(i.above_5dma_pct),y=Number(i.above_10dma_pct);
    const zone=(v:number)=>v<20?"EXTREME WASHOUT":v<30?"OVERSOLD":v<50?"WEAK":v<70?"HEALTHY":v<80?"STRONG":"EXTREME";
    const dir=(finite(i.change_5dma_points)&&Number(i.change_5dma_points)>0)||(finite(i.change_10dma_points)&&Number(i.change_10dma_points)>0)?"Breadth is expanding from the prior session.":"Breadth is not showing a clear expansion from the prior session.";
    return `5-day breadth is ${x.toFixed(1)}% (${zone(x)}); 10-day breadth is ${y.toFixed(1)}% (${zone(y)}). ${dir} For RE-ENTRY, a fast move from sub-30% toward/through 50% is the constructive pattern.`;
  }
  if(key==="credit_risk_turn"){
    const d5=i.change_5d;
    if(!finite(d5))return "Credit relative-momentum history is unavailable.";
    const v=Number(d5);
    const zone=v>0.0025?"SUPPORTIVE":v<-0.0025?"DEFENSIVE":"NEAR NEUTRAL";
    return `HYG/LQD 5-day relative momentum is ${signedPct(v)} - ${zone}. ${v>0?"High-yield credit is outperforming higher-quality bonds, so credit markets are not confirming a worsening risk-off move.":"High-yield credit is lagging, which is a caution flag for equity re-entry."} This remains context only.`;
  }
  return i.meaning||"Context unavailable.";
}

function detail(key:string,i:Indicator){
  if(key==="zweig_breadth_thrust"){
    if(i.status==="BUILDING_HISTORY")return `Captured history is still building (${i.session_count??0}/10 sessions needed). No thrust trigger is asserted until the history gate is met.`;
    return i.triggered?"Classic rapid breadth-thrust condition is active.":`Recent 10-session EMA low ${ratioPct(i.recent_10_session_low_ema)}. No classic thrust trigger is active.`;
  }
  if(key==="mcclellan_velocity"){
    const p=finite(i.velocity_percentile)?`${Number(i.velocity_percentile).toFixed(0)}th percentile`:`history building (${i.history_sessions??0} sessions)`;
    return `Breadth-momentum velocity is ${p}. This tests acceleration in the turn rather than waiting for slower trend confirmation.`;
  }
  if(key==="nasdaq_short_breadth")return `5D change ${signedPts(i.change_5dma_points)} · 10D change ${signedPts(i.change_10dma_points)} · coverage ${pct(i.coverage_5dma_pct)} / ${pct(i.coverage_10dma_pct)}.`;
  if(key==="credit_risk_turn")return "Shown separately as an early risk-appetite clue, but it is not double-counted in the existing secondary-confirmation score.";
  return"";
}

export default function LeadingIndicators({washout}:{washout:any}){
  const block:LeadingBlock|undefined=washout?.unified_engine?.leading_indicators||washout?.leading_indicators;
  if(!block?.indicators)return null;
  const order=["zweig_breadth_thrust","mcclellan_velocity","nasdaq_short_breadth","credit_risk_turn"];
  const entries=order.map(key=>[key,block.indicators?.[key]] as const).filter(([,value])=>Boolean(value)) as Array<readonly[string,Indicator]>;
  if(!entries.length)return null;
  return <section className="card section-card leading-indicators">
    <style>{`
      .leading-indicators{background:linear-gradient(145deg,#fbfbf8 0%,#f7faf8 100%)}
      .leading-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:14px}.leading-head p{max-width:720px;margin:6px 0 0;font-size:10px;line-height:1.5;color:var(--muted)}.leading-badge{font-size:8px;font-weight:900;letter-spacing:.08em;border:1px solid var(--line);border-radius:999px;padding:7px 9px;white-space:nowrap;background:rgba(255,255,255,.62)}
      .leading-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.leading-card{position:relative;border:1px solid var(--line);border-radius:15px;padding:14px;background:rgba(255,255,255,.62);overflow:hidden}.leading-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#a8aaa4}.leading-card.lead-good:before{background:var(--green)}.leading-card.lead-warn:before{background:var(--amber)}.leading-card.lead-bad:before{background:var(--red)}
      .leading-card h3{font-size:11px;margin:0 0 7px;line-height:1.3}.leading-state{display:inline-block;font-size:8px;font-weight:900;letter-spacing:.045em;border:1px solid currentColor;border-radius:999px;padding:4px 6px;margin-bottom:8px}.lead-good .leading-state{color:var(--green)}.lead-warn .leading-state{color:var(--amber)}.lead-bad .leading-state{color:var(--red)}
      .leading-readout{font-size:13px;font-weight:850;line-height:1.4}.leading-context{font-size:10px;line-height:1.52;color:#343a34;margin:9px 0 0}.leading-context b,.leading-range b{display:block;font-size:7px;letter-spacing:.1em;color:var(--muted);margin-bottom:3px}.leading-detail{font-size:9px;line-height:1.48;color:#454a43;margin:8px 0 0}.leading-range{font-size:9px;line-height:1.5;color:#4d534c;background:#f0eee8;padding:9px;border-radius:9px;margin-top:9px}.leading-freshness{font-size:8px;font-weight:800;letter-spacing:.035em;color:var(--muted);margin-top:8px}.leading-foot{margin:12px 0 0;font-size:9px;line-height:1.5;color:var(--muted)}
      @media(max-width:760px){.leading-grid{grid-template-columns:1fr}.leading-head{display:block}.leading-badge{display:inline-block;margin-top:9px}}
    `}</style>
    <div className="leading-head"><div><span className="kicker">LEADING INDICATORS</span><h2 style={{margin:"4px 0 0",fontSize:24,letterSpacing:"-.035em"}}>Are market internals starting to turn early?</h2><p>{block.purpose||"Early-turn context only. These indicators do not change the RE-ENTRY decision."} Every card now shows the current zone, the full range map, and the re-entry implication.</p></div><div className="leading-badge">CONTEXT ONLY · NO NEW SCORE</div></div>
    <div className="leading-grid">{entries.map(([key,i])=><div key={key} className={`leading-card ${tone(i)}`}><h3>{i.name||key.replaceAll("_"," ")}</h3><span className="leading-state">{(i.state||"UNAVAILABLE").replaceAll("_"," ")}</span><div className="leading-readout">{readout(key,i)}</div><p className="leading-context"><b>CURRENT READ + RE-ENTRY CONTEXT</b>{currentContext(key,i)}</p><div className="leading-range"><b>LEVELS / NORMAL / EXTREMES</b>{rangeMap(key,i)}</div><p className="leading-detail">{detail(key,i)}</p><div className="leading-freshness">{(i.freshness_type||"UNAVAILABLE").replaceAll("_"," ")}{i.last_updated?` · ${i.last_updated}`:""}</div></div>)}</div>
    <p className="leading-foot">Range framework is grounded in established breadth practice: Martin Zweig / StockCharts for the 40%→61.5% Breadth Thrust, John Murphy / StockCharts for McClellan ±100 extremes, and StockCharts breadth methodology around the 50% majority line. Where no defensible universal fixed extreme exists - such as HYG/LQD - RE-ENTRY uses direction now and will use empirical percentiles rather than inventing a threshold. These readings cannot create, block, delay, or revoke DEPLOY.</p>
  </section>;
}
